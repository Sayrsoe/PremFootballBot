"""Isolated offline fit of one approved archive, RETROSPECTIVE_DESCRIPTIVE_ONLY.

No forecasting, synthetic conversion, historical-availability inference or I/O.
Positive defense parameters mean greater vulnerability, not stronger defense.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import date, datetime
import hashlib
import json
import math
import sys

from .openfootball_exploratory import (
    ExploratoryImport, OpenFootballError, OpenFootballSource,
    parse_openfootball_epl, exploratory_json,
)

VERSION = "phase3ca-ridge-poisson-v1"
STATUS = "RETROSPECTIVE_DESCRIPTIVE_ONLY"
APPROVED_COMMIT = "9ee7a0c351805c99cc334478a9bf04b7d0432fec"
APPROVED_PATH = "2023-24/1-premierleague.txt"
APPROVED_BLOB = "23cdd8a340b72f6f30c514fbf609d5cf252723aa"
APPROVED_SHA256 = "0bfb4a7fffe0b1bf7318955686eafeb28fc9676346ae433259e7409d69551450"
LICENSE_SHA256 = "36ffd9dc085d529a7e60e1276d73ae5a030b020313e6c5408593a6ae2af39673"
SEMANTIC_SHA256 = "ac1a691aa44cfb154d6c396934932c96c3eba2d87b1b104a28c7364cdbbb9700"
_REPO = "https://github.com/openfootball/england"
_LICENSE_BLOB = "670154e3538863b2d9891fd5483160fbdfc89164"


class RealTrainingError(ValueError):
    """Atomic failure; no partial artifact is returned."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise RealTrainingError(code, message)


@dataclass(frozen=True, slots=True)
class RealFitConfig:
    ridge: float = 4.0
    max_iterations: int = 100
    gradient_tolerance: float = 1e-7

    def __post_init__(self):
        # Bounds also limit ill-conditioning and unbounded work, not data tuning.
        for name, lower, upper in (("ridge", 0.01, 10000),
                                   ("gradient_tolerance", 1e-10, 1e-5)):
            value = getattr(self, name)
            _require(type(value) in (int, float) and lower <= value <= upper,
                     "BAD_CONFIG", f"{name} must be finite in [{lower},{upper}]")
        _require(type(self.max_iterations) is int and 1 <= self.max_iterations <= 200,
                 "BAD_CONFIG", "max_iterations must be an integer in [1,200]")


@dataclass(frozen=True, slots=True)
class TeamEffect:
    team: str
    attack: float
    defense_vulnerability: float
    home_matches: int
    away_matches: int


@dataclass(frozen=True, slots=True)
class FitDiagnostics:
    iterations: int
    objective_trace: tuple[float, ...]
    objective: float
    negative_log_likelihood: float
    penalty: float
    gradient_inf_norm: float
    in_sample_poisson_deviance: float
    observed_home_goals: int
    observed_away_goals: int
    fitted_home_goals: float
    fitted_away_goals: float
    backtracks: int


@dataclass(frozen=True, slots=True)
class RetrospectiveFit:
    source_import: ExploratoryImport
    config: RealFitConfig
    intercept: float
    home_advantage: float
    teams: tuple[TeamEffect, ...]
    diagnostics: FitDiagnostics
    training_matches: int
    training_goal_observations: int
    exclusions: tuple[tuple[str, int], ...]
    license_sha256: str
    runtime: str
    version: str = VERSION
    status: str = STATUS
    record_kind: str = "NON_SYNTHETIC_REAL_ARCHIVE"
    strict_point_in_time_eligible: bool = False
    historical_available_at: None = None
    prediction_api_available: bool = False
    warnings: tuple[str, ...] = (
        "Full-season retrospective fit; in-sample diagnostics are not predictive evaluation.",
        "Historical availability and kickoff UTC are unknown; retrieval is acquisition only.",
        "Ridge=4 default is an engineering choice, not a validated or tuned hyperparameter.",
        "Independent Poisson and constant season strengths are unvalidated assumptions.",
        "No accuracy, ROI, profitability or Asian Handicap value claim.",
    )
    sha256: str = ""


def _plain(value):
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


def _json(value) -> bytes:
    return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf8")


def _digest(value: RetrospectiveFit) -> str:
    fields = asdict(value)
    fields.pop("sha256")
    return hashlib.sha256(_json(fields)).hexdigest()


def retrospective_json(model: RetrospectiveFit) -> bytes:
    """Canonical JSON, checking the seal. A checksum is not a digital signature.

Use verify_retrospective_fit for source-backed recomputation at a trust boundary.
There is deliberately no deserializer that treats supplied JSON as a trusted fit.
"""
    _require(type(model) is RetrospectiveFit, "INPUT_TYPE", "Expected RetrospectiveFit")
    _require(model.status == STATUS and model.version == VERSION
             and model.record_kind == "NON_SYNTHETIC_REAL_ARCHIVE"
             and model.strict_point_in_time_eligible is False
             and model.historical_available_at is None and model.prediction_api_available is False,
             "ARTIFACT_TAMPERED", "Required retrospective restrictions changed")
    try:
        valid = model.sha256 == _digest(model)
    except (TypeError, ValueError, OverflowError):
        valid = False
    _require(valid, "ARTIFACT_TAMPERED", "Artifact checksum mismatch or invalid payload")
    return _json(model)


def _approved_import(raw_bytes: bytes, source: OpenFootballSource,
                     license_bytes: bytes) -> ExploratoryImport:
    _require(type(source) is OpenFootballSource, "INPUT_TYPE", "Supply OpenFootballSource")
    _require(type(raw_bytes) is bytes and type(license_bytes) is bytes,
             "INPUT_TYPE", "Supply original archive and license bytes")
    _require(source.repository_url == _REPO and source.repository_commit_sha == APPROVED_COMMIT
             and source.path == APPROVED_PATH and source.expected_git_blob_sha == APPROVED_BLOB
             and source.expected_sha256 == APPROVED_SHA256,
             "UNAPPROVED_SOURCE", "Only the approved exact 2023-24 source is authorized")
    _require(source.licence_id == "CC0-1.0" and source.licence_blob_sha == _LICENSE_BLOB
             and source.licence_evidence_url == f"{_REPO}/blob/{APPROVED_COMMIT}/LICENSE.md",
             "LICENCE", "Require the independently inspected CC0 evidence")
    _require(0 < len(license_bytes) <= 20000
             and hashlib.sha256(license_bytes).hexdigest() == LICENSE_SHA256,
             "LICENCE", "Exact inspected license bytes required")
    blob = hashlib.sha1(b"blob " + str(len(license_bytes)).encode("ascii")
                        + b"\0" + license_bytes).hexdigest()
    _require(blob == _LICENSE_BLOB, "LICENCE", "License blob mismatch")
    try:
        imported = parse_openfootball_epl(raw_bytes, source=source)
    except OpenFootballError as error:
        raise RealTrainingError("SOURCE_" + error.code, str(error)) from error
    _validate_training(imported)
    return imported


def _validate_training(imported: ExploratoryImport) -> None:
    # Do not drop quarantines, manufacture missing scores or merge team aliases.
    exploratory_json(imported)
    _require(imported.season_start_year == 2023 and not imported.quarantined
             and not imported.header_issues and len(imported.rows) == 380
             and imported.total_match_like_lines == 380
             and imported.semantic_sha256 == SEMANTIC_SHA256,
             "TRAINING_COVERAGE", "Require complete approved facts and zero quarantines")
    rows = imported.rows
    teams = {r.home_team_raw for r in rows} | {r.away_team_raw for r in rows}
    pairs = Counter((r.home_team_raw, r.away_team_raw) for r in rows)
    _require(len(teams) == 20 and set(pairs) == {(h, a) for h in teams for a in teams if h != a}
             and all(n == 1 for n in pairs.values()),
             "TRAINING_COVERAGE", "Require one match per ordered pair")
    _require(all(r.record_kind == "NON_SYNTHETIC_REAL_ARCHIVE"
                 and r.evidence_status == "EXPLORATORY_DATE_LEVEL_RECONSTRUCTION"
                 and r.strict_point_in_time_eligible is False and r.kickoff_utc is None
                 and r.historical_available_at is None for r in rows),
             "TRAINING_METADATA", "Real archive restrictions must remain explicit")


def _design(rows):
    teams = tuple(sorted({r.home_team_raw for r in rows} | {r.away_team_raw for r in rows}))
    indices = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    # Sparse binary log-link design. Each goal observation has 3 or 4 active terms.
    data = []
    for row in sorted(rows, key=lambda r: (r.match_date, r.fixture_id)):
        h, a = indices[row.home_team_raw], indices[row.away_team_raw]
        data.append(((0, 1, 2 + h, 2 + n + a), row.home_goals_ft90))
        data.append(((0, 2 + a, 2 + n + h), row.away_goals_ft90))
    return teams, tuple(data)


def _objective(theta, data, ridge):
    terms = []
    for active, goals in data:
        eta = math.fsum(theta[j] for j in active)
        # Safely reject extreme line-search trials, never clip fitted rates.
        if not math.isfinite(eta) or not -700 < eta < 700:
            return math.inf
        terms.append(math.exp(eta) - goals * eta + math.lgamma(goals + 1))
    return math.fsum(terms) + ridge / 2 * math.fsum(t * t for t in theta[2:])


def _derivatives(theta, data, ridge):
    size = len(theta)
    gradient = [0.0, 0.0] + [ridge * t for t in theta[2:]]
    hessian = [[0.0] * size for _ in theta]
    for j in range(2, size):
        hessian[j][j] = ridge
    for active, goals in data:
        rate = math.exp(math.fsum(theta[j] for j in active))
        for j in active:
            gradient[j] += rate - goals
            for k in active:
                hessian[j][k] += rate
    return gradient, hessian


def _solve(matrix, rhs):
    """Independent textbook Cholesky factorization and triangular solves."""
    size = len(rhs)
    lower = [[0.0] * size for _ in rhs]
    for i in range(size):
        for j in range(i + 1):
            value = matrix[i][j] - math.fsum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                _require(math.isfinite(value) and value > 0, "NUMERIC_ERROR", "Nonpositive Cholesky pivot")
                lower[i][j] = math.sqrt(value)
            else:
                lower[i][j] = value / lower[j][j]
    intermediate = []
    for i in range(size):
        intermediate.append((rhs[i] - math.fsum(lower[i][k] * intermediate[k]
                                               for k in range(i))) / lower[i][i])
    solution = [0.0] * size
    for i in reversed(range(size)):
        solution[i] = (intermediate[i] - math.fsum(lower[k][i] * solution[k]
                                                  for k in range(i + 1, size))) / lower[i][i]
    return solution


def _fit_rows(rows, config):
    teams, data = _design(rows)
    home_total = sum(r.home_goals_ft90 for r in rows)
    away_total = sum(r.away_goals_ft90 for r in rows)
    _require(rows and home_total > 0 and away_total > 0,
             "DEGENERATE_TRAINING", "Both venue goal totals must be positive")
    theta = [math.log(away_total / len(rows)), math.log(home_total / away_total)] + [0.0] * (2 * len(teams))
    trace = [_objective(theta, data, config.ridge)]
    backtracks = 0
    for iteration in range(config.max_iterations + 1):
        gradient, hessian = _derivatives(theta, data, config.ridge)
        norm = max(abs(g) for g in gradient)
        _require(math.isfinite(norm), "NUMERIC_ERROR", "Nonfinite gradient")
        if norm <= config.gradient_tolerance:
            break
        _require(iteration < config.max_iterations, "NOT_CONVERGED", "Iteration budget exhausted")
        step = _solve(hessian, gradient)
        descent = math.fsum(g * s for g, s in zip(gradient, step))
        _require(math.isfinite(descent) and descent > 0, "NUMERIC_ERROR", "Invalid Newton direction")
        scale = 1.0
        for attempt in range(50):
            trial = [t - scale * s for t, s in zip(theta, step)]
            objective = _objective(trial, data, config.ridge)
            if math.isfinite(objective) and objective <= trace[-1] - 1e-4 * scale * descent:
                break
            scale *= 0.5
            backtracks += 1
        else:
            raise RealTrainingError("NOT_CONVERGED", "Line search exhausted")
        theta = trial
        trace.append(objective)
    rates = [math.exp(math.fsum(theta[j] for j in active)) for active, _ in data]
    nll = math.fsum(rate - goals * math.log(rate) + math.lgamma(goals + 1)
                    for rate, (_, goals) in zip(rates, data))
    deviance = 2 * math.fsum((goals * math.log(goals / rate) if goals else 0.0) - goals + rate
                            for rate, (_, goals) in zip(rates, data))
    penalty = config.ridge / 2 * math.fsum(t * t for t in theta[2:])
    diagnostics = FitDiagnostics(iteration, tuple(trace), trace[-1], nll, penalty, norm,
                                 deviance, home_total, away_total,
                                 math.fsum(rates[::2]), math.fsum(rates[1::2]), backtracks)
    home_counts = Counter(r.home_team_raw for r in rows)
    away_counts = Counter(r.away_team_raw for r in rows)
    effects = tuple(TeamEffect(team, theta[2 + i], theta[2 + len(teams) + i],
                               home_counts[team], away_counts[team]) for i, team in enumerate(teams))
    return theta[0], theta[1], effects, diagnostics


def fit_real_epl(raw_bytes: bytes, *, source: OpenFootballSource, license_bytes: bytes,
                 config: RealFitConfig = RealFitConfig()) -> RetrospectiveFit:
    """Fit only the pinned complete 2023-24 archive; no cutoff or target argument.

Reparse raw bytes at this boundary, never trust caller-constructed normalized rows.
All diagnostics describe the same season used to estimate the parameters.
"""
    _require(type(config) is RealFitConfig, "BAD_CONFIG", "Expected RealFitConfig")
    config.__post_init__()
    # Normalize integer-valued numeric config to one canonical representation.
    config = RealFitConfig(float(config.ridge), config.max_iterations, float(config.gradient_tolerance))
    imported = _approved_import(raw_bytes, source, license_bytes)
    mu, home, teams, diagnostics = _fit_rows(imported.rows, config)
    model = RetrospectiveFit(imported, config, mu, home, teams, diagnostics,
                             len(imported.rows), 2 * len(imported.rows),
                             (("quarantined", 0), ("header_issues", 0), ("filtered", 0)),
                             LICENSE_SHA256,
                             f"{sys.implementation.name} {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return replace(model, sha256=_digest(model))


def verify_retrospective_fit(model: RetrospectiveFit, raw_bytes: bytes, *, license_bytes: bytes) -> bool:
    """Recompute using pinned inputs; rejects even a maliciously re-sealed alteration.

Exact equality is promised only in the same Python/math runtime. Other platforms
should independently review numerical tolerances, not weaken this verifier.
"""
    original = retrospective_json(model)
    replay = fit_real_epl(raw_bytes, source=model.source_import.source,
                          license_bytes=license_bytes, config=model.config)
    _require(original == retrospective_json(replay), "REPLAY_MISMATCH", "Artifact differs from recomputed fit")
    return True
