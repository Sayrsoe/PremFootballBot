"""Offline synthetic walk-forward forecasts and separate later evaluation.

SYNTHETIC DEMONSTRATION ONLY — NO REAL EPL ACCURACY OR BETTING PROFIT CLAIMS.
No network, provider, tuning, normalization, clipping or current-clock access.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from numbers import Real
import re

from .expected_goals import (
    ExpectedGoalsError, FittedModel, ModelConfig, fit_expected_goals, fit_rate_ratio,
    predict_expected_goals, prediction_identifiability,
)
from .match_data import ImportResult, MatchDataError, Observation, parse_synthetic_json, select_as_of
from .poisson import GoalCapError, poisson_distribution

BANNER = "SYNTHETIC DEMONSTRATION ONLY — NO REAL EPL ACCURACY OR BETTING PROFIT CLAIMS"
METHODS = ("ridge", "rate_ratio", "league")
VERSION = "phase3a-v1"
LABEL_POLICY = "latest_strict_before_snapshot;unknown_higher_quarantine;no_fallback;exact_identity_and_kickoff"
MASS_POLICY = "raw_retained_controlled_approximation;no_renormalization;no_clipping"
_ROUNDOFF = 5e-12

def _method_version(method: str) -> str:
    return "phase3a-league-v1" if method == "league" else "phase2b-v1"

class BacktestError(ValueError):
    """Explicit input/protocol/scoring failure, with a stable reason code."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")

def _need(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise BacktestError(code, message)

def _finite_number(value) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        converted = float(value)
        return math.isfinite(converted) and (converted != 0 or value == 0)
    except (OverflowError, ValueError, TypeError):
        return False

def _plain(value):
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, Real) and not isinstance(value, (bool, int)):
        number = float(value)
        _need(math.isfinite(number), "NONFINITE", "JSON numbers must be finite")
        return number
    return value

def _json(value) -> bytes:
    try:
        return json.dumps(_plain(value), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf8")
    except (TypeError, ValueError, OverflowError, UnicodeError) as error:
        if isinstance(error, BacktestError):
            raise
        raise BacktestError("SERIALIZATION", "Cannot encode canonical finite JSON") from error

def _digest(value) -> str:
    data = asdict(value)
    data.pop("sha256", None)
    return hashlib.sha256(_json(data)).hexdigest()

def _seal(value):
    return replace(value, sha256=_digest(value))

def _verify(value, cls) -> None:
    _need(isinstance(value, cls), "INPUT_TYPE", "Unexpected snapshot type")
    _need(value.sha256 == _digest(value), "SNAPSHOT_TAMPERED", "Snapshot digest does not match content")

def snapshot_json(snapshot) -> bytes:
    """Verify and serialize an immutable manifest/forecast/label/report snapshot."""
    _need(is_dataclass(snapshot) and hasattr(snapshot, "sha256"), "INPUT_TYPE", "Expected a sealed snapshot")
    _need(snapshot.sha256 == _digest(snapshot), "SNAPSHOT_TAMPERED", "Digest mismatch")
    return _json(snapshot)

def _utc(value, field: str) -> datetime:
    _need(isinstance(value, datetime) and value.tzinfo is not None
          and value.utcoffset() is not None, "TIMESTAMP", field + " must be aware")
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise BacktestError("TIMESTAMP", field + " outside UTC range") from error

def _stamp(value, field: str) -> datetime:
    pattern = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})"
    _need(isinstance(value, str) and re.fullmatch(pattern, value) is not None
          and not value.endswith("-00:00"), "TIMESTAMP", field + " must be exact with known offset")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), field)
    except ValueError as error:
        if isinstance(error, BacktestError):
            raise
        raise BacktestError("TIMESTAMP", "Invalid " + field) from error

def _integer(value, field: str, lower: int, upper: int) -> int:
    _need(type(value) is int and lower <= value <= upper, "INPUT_VALUE", "Invalid integer " + field)
    return value

def _shape(value, keys: set[str], field: str) -> None:
    _need(isinstance(value, dict) and set(value) == keys, "MANIFEST_INVALID",
          field + " requires exactly the documented fields")

def _identifier(value, ns: str, kind: str) -> str:
    _need(isinstance(value, str) and re.fullmatch(re.escape(ns) + ":" + kind + r":[a-z][a-z0-9_-]*", value) is not None,
          "IDENTITY", "Expected canonical synthetic " + kind + " ID")
    return value

def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "MANIFEST_INVALID", "Duplicate JSON key")
        result[key] = value
    return result

def _constant(value):
    raise BacktestError("NONFINITE", "Nonfinite JSON number")

@dataclass(frozen=True, slots=True)
class TargetFixture:
    fixture_id: str
    competition_code: str
    season_start_year: int
    home_team_id: str
    away_team_id: str
    intended_kickoff_utc: datetime
    prediction_cutoff_utc: datetime
    declared_at_utc: datetime

@dataclass(frozen=True, slots=True)
class TargetManifest:
    namespace: str
    team_ids: tuple[str, ...]
    targets: tuple[TargetFixture, ...]
    schema_version: int = 1
    is_synthetic: bool = True
    banner: str = BANNER
    sha256: str = ""

def parse_target_manifest(data: bytes) -> TargetManifest:
    """Strict invented ex-ante JSON; never derive target metadata from results."""
    _need(isinstance(data, bytes), "INPUT_TYPE", "Manifest must be UTF8 bytes")
    _need(len(data) <= 4*1024*1024, "INPUT_SIZE", "Manifest exceeds 4 MiB")
    try:
        raw = json.loads(data.decode("utf8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, BacktestError):
            raise
        raise BacktestError("MANIFEST_INVALID", "Invalid UTF8/strict JSON") from error
    _shape(raw, {"schema_version", "namespace", "is_synthetic", "team_ids", "targets"}, "manifest")
    _need(type(raw["schema_version"]) is int and raw["schema_version"] == 1
          and raw["is_synthetic"] is True, "MANIFEST_INVALID", "Only synthetic version1 supported")
    ns = raw["namespace"]
    _need(isinstance(ns, str) and re.fullmatch(r"synthetic:[a-z][a-z0-9_-]*", ns) is not None,
          "IDENTITY", "Expected synthetic namespace")
    _need(isinstance(raw["team_ids"], list) and isinstance(raw["targets"], list),
          "MANIFEST_INVALID", "Registry and targets must be lists")
    teams = tuple(sorted(_identifier(t, ns, "team") for t in raw["team_ids"]))
    _need(len(teams) == len(set(teams)), "IDENTITY", "Duplicate registered team")
    _need(0 < len(raw["targets"]) <= 1000, "INPUT_SIZE", "Need 1..1000 targets")
    targets, seen = [], set()
    for item in raw["targets"]:
        _shape(item, set(TargetFixture.__dataclass_fields__), "target")
        row = dict(item)
        fixture = _identifier(row["fixture_id"], ns, "fixture")
        _need(fixture not in seen, "DUPLICATE_TARGET", "Duplicate target fixture ID")
        seen.add(fixture)
        for side in ("home", "away"):
            _identifier(row[side + "_team_id"], ns, "team")
            _need(row[side + "_team_id"] in teams, "IDENTITY", "Unregistered target team")
        _need(row["home_team_id"] != row["away_team_id"], "IDENTITY", "Self-match forbidden")
        _need(row["competition_code"] == "EPL", "IDENTITY", "Only EPL supported")
        _integer(row["season_start_year"], "season", 1992, 9998)
        for field in ("intended_kickoff_utc", "prediction_cutoff_utc", "declared_at_utc"):
            row[field] = _stamp(row[field], field)
        try:
            row["intended_kickoff_utc"] + timedelta(minutes=90)
        except OverflowError:
            raise BacktestError("TIMESTAMP", "Intended kickoff exceeds supported FT90 datetime range") from None
        _need(row["declared_at_utc"] < row["prediction_cutoff_utc"] < row["intended_kickoff_utc"],
              "NOT_EX_ANTE", "Require declared_at < prediction cutoff < intended kickoff")
        targets.append(TargetFixture(**row))
    targets.sort(key=lambda t: (t.prediction_cutoff_utc, t.fixture_id))
    return _seal(TargetManifest(ns, teams, tuple(targets)))

@dataclass(frozen=True, slots=True)
class BacktestConfig:
    model: ModelConfig = ModelConfig()
    tail_tolerance: float = 1e-10
    max_goals: int = 512
    calibration_bins: int = 5
    min_evidence: int = 20

    def __post_init__(self):
        _need(isinstance(self.model, ModelConfig), "BAD_CONFIG", "Expected frozen ModelConfig")
        _need(_finite_number(self.tail_tolerance) and 0 < self.tail_tolerance <= 1e-10,
              "BAD_CONFIG", "Tail tolerance must be finite, positive and <=1e-10")
        _integer(self.max_goals, "max_goals", 0, 512)
        _integer(self.calibration_bins, "calibration_bins", 2, 20)
        _integer(self.min_evidence, "min_evidence", 1, 1000000)

@dataclass(frozen=True, slots=True)
class ProbabilityMass:
    home: float
    draw: float
    away: float
    retained_mass: float = 1.0
    omitted_mass: float = 0.0
    omitted_bound: float = 0.0

@dataclass(frozen=True, slots=True)
class Scores:
    log_loss: float
    brier: float
    rps: float
    log_loss_truncation_bound: float
    banner: str = BANNER

def _probability_guard(p: ProbabilityMass, tolerance: float) -> None:
    _need(isinstance(p, ProbabilityMass), "PROBABILITY_INVALID", "Expected ProbabilityMass")
    values = (p.home, p.draw, p.away, p.retained_mass, p.omitted_mass, p.omitted_bound)
    _need(all(_finite_number(v) and 0 <= v <= 1 for v in values),
          "PROBABILITY_INVALID", "Probabilities/masses must be finite in [0,1]")
    _need(abs(math.fsum((p.home, p.draw, p.away))-p.retained_mass) <= _ROUNDOFF
          and abs(math.fsum((p.retained_mass, p.omitted_mass))-1) <= _ROUNDOFF
          and p.omitted_mass <= p.omitted_bound,
          "MASS_INVALID", "Raw probability accounting is inconsistent")
    _need(p.omitted_bound <= tolerance, "TAIL_GUARD", "Omitted mass exceeds controlled approximation target")

def score_1x2(probabilities: ProbabilityMass, actual: str, *,
              tail_tolerance: float = 1e-10) -> Scores:
    """Raw retained categorical scores, H/D/A; RPS order A<D<H, no division.

    Truncation-only log-loss bound is log1p(B/p_observed). This does not include
    floating-point error or imply calibrated forecast confidence.
    """
    _need(_finite_number(tail_tolerance) and 0 < tail_tolerance <= 1e-10,
          "BAD_CONFIG", "Invalid scoring tail tolerance")
    _probability_guard(probabilities, tail_tolerance)
    _need(isinstance(actual, str) and actual in ("H", "D", "A"), "LABEL_INVALID", "Expected H/D/A")
    p = (probabilities.home, probabilities.draw, probabilities.away)
    observed = ("H", "D", "A").index(actual)
    _need(p[observed] > 0, "ZERO_OBSERVED_MASS", "No clipping of zero observed probability")
    brier = math.fsum((v-(i == observed))**2 for i, v in enumerate(p))
    rps = math.fsum(((p[2]-(actual == "A"))**2,
                    (p[2]+p[1]-(actual in ("A", "D")))**2))
    ratio = probabilities.omitted_bound / p[observed]
    bound = (math.log1p(ratio) if _finite_number(ratio) or ratio == 0
             else math.log(probabilities.omitted_bound+p[observed])-math.log(p[observed]))
    return Scores(-math.log(p[observed]), brier, rps, bound)

@dataclass(frozen=True, slots=True)
class MethodForecast:
    target_id: str
    method: str
    status: str
    reason: str | None
    lambda_home: float | None
    lambda_away: float | None
    probabilities: ProbabilityMass | None
    origin_batch_hash: str
    training_row_hash: str
    training_refs: tuple[tuple[str, int], ...]
    training_exclusions: tuple[tuple[str, int], ...]
    warnings: tuple[str, ...]
    model_rank: int | None = None
    model_identified: bool | None = None
    home_identified: bool | None = None
    away_identified: bool | None = None
    iterations: int | None = None
    gradient_inf: float | None = None
    model_version: str = "phase2b-v1"

@dataclass(frozen=True, slots=True)
class ForecastSnapshot:
    manifest: TargetManifest
    config: BacktestConfig
    records: tuple[MethodForecast, ...]
    version: str = VERSION
    mass_policy: str = MASS_POLICY
    banner: str = BANNER
    sha256: str = ""

def _manifest_checked(manifest: TargetManifest) -> TargetManifest:
    _verify(manifest, TargetManifest)
    raw = {"schema_version": manifest.schema_version, "namespace": manifest.namespace,
           "is_synthetic": manifest.is_synthetic, "team_ids": manifest.team_ids,
           "targets": manifest.targets}
    checked = parse_target_manifest(_json(raw))
    _need(checked.sha256 == manifest.sha256, "MANIFEST_INVALID", "Noncanonical manifest")
    return checked

def _batch_checked(batch: ImportResult) -> ImportResult:
    _need(isinstance(batch, ImportResult), "BATCH_INVALID", "Expected Phase2A ImportResult")
    try:
        batch.require_valid()
        payload = {"schema_version": 1, "namespace": batch.namespace,
                   "teams": batch.teams, "source_documents": batch.source_documents,
                   "records": batch.observations}
        checked = parse_synthetic_json(_json(payload)).require_valid()
        _need(checked.content_sha256 == batch.content_sha256, "BATCH_INVALID", "Input content hash mismatch")
        return checked
    except (MatchDataError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, BacktestError):
            raise
        raise BacktestError("BATCH_INVALID", "Phase2A validation failed") from error

def _rows_hash(rows) -> str:
    values = []
    for row in sorted(rows, key=lambda r: (r.kickoff_utc, r.fixture_id, r.revision)):
        data = asdict(row)
        del data["retrieved_at_utc"]
        values.append(data)
    return hashlib.sha256(_json(values)).hexdigest()

def _same_identity(row: Observation, target: TargetFixture) -> bool:
    return (row.fixture_id, row.competition_code, row.season_start_year,
            row.home_team_id, row.away_team_id) == (
                target.fixture_id, target.competition_code, target.season_start_year,
                target.home_team_id, target.away_team_id)

def _target_guard(batch: ImportResult, target: TargetFixture) -> str | None:
    versions = [r for r in batch.observations if r.fixture_id == target.fixture_id]
    known = [r for r in versions if r.available_at_utc is not None
             and r.available_at_utc < target.prediction_cutoff_utc]
    latest = max(known, key=lambda r: r.revision, default=None)
    if any(r.available_at_utc is None and (latest is None or r.revision > latest.revision) for r in versions):
        return "TARGET_HISTORY_UNCERTAIN"
    if any(r.record_type == "result" for r in known):
        return "TARGET_RESULT_BEFORE_CUTOFF"
    if latest is not None:
        if latest.status not in ("SCHEDULED", "TIMED"):
            return "TARGET_NOT_SCHEDULED"
        if latest.kickoff_precision != "exact" or latest.kickoff_utc is None:
            return "TARGET_HISTORY_UNCERTAIN"
        if not _same_identity(latest, target) or latest.kickoff_utc != target.intended_kickoff_utc:
            return "TARGET_METADATA_MISMATCH"
    return None

def _project(batch: ImportResult, manifest: TargetManifest, target: TargetFixture):
    cutoff = target.prediction_cutoff_utc
    selection = select_as_of(batch, cutoff, include_synthetic=True)
    rows = tuple(sorted(selection.observations, key=lambda r: (r.kickoff_utc, r.fixture_id, r.revision)))
    declarations = {t.fixture_id: t for t in manifest.targets}
    for row in rows:
        _need(row.fixture_id != target.fixture_id, "LEAKAGE_DETECTED", "Target in historical selection")
        _need(row.is_synthetic is True and row.licence_status == "CLEARED"
              and row.record_type == "result" and row.status == "FINISHED" and row.result_basis == "FT90"
              and row.kickoff_precision == "exact" and row.available_at_utc is not None,
              "LEAKAGE_DETECTED", "Selection violated synthetic FT90 policy")
        try:
            earliest = row.kickoff_utc + timedelta(minutes=90)
        except OverflowError:
            raise BacktestError("LEAKAGE_DETECTED", "Selected kickoff exceeds FT90 datetime range") from None
        _need(earliest <= row.available_at_utc < cutoff,
              "LEAKAGE_DETECTED", "Future result in historical selection")
        if row.fixture_id in declarations:
            declared = declarations[row.fixture_id]
            _need(_same_identity(row, declared)
                  and row.available_at_utc >= declared.intended_kickoff_utc + timedelta(minutes=90),
                  "LEAKAGE_DETECTED", "Historical result contradicts predeclared target schedule")
    # Keep complete historical prefixes, not relabelled/reindexed latest rows.
    latest = {r.fixture_id: r.revision for r in rows}
    prefix = tuple(r for r in batch.observations
                   if r.fixture_id in latest and r.revision <= latest[r.fixture_id])
    team_ids = {r.home_team_id for r in prefix} | {r.away_team_id for r in prefix}
    doc_ids = {(r.source_id, r.source_document_id) for r in prefix}
    payload = {"schema_version": 1, "namespace": batch.namespace,
               "teams": tuple(t for t in batch.teams if t.team_id in team_ids),
               "source_documents": tuple(s for s in batch.source_documents
                                         if (s.source_id, s.source_document_id) in doc_ids),
               "records": prefix}
    projected = parse_synthetic_json(_json(payload)).require_valid()
    check = select_as_of(projected, cutoff, include_synthetic=True)
    _need(set(check.observations) == set(rows), "LEAKAGE_DETECTED", "Projection changed selected history")
    counts: dict[str, int] = {}
    for exclusion in selection.exclusions:
        # Future row count/values are deliberately absent from forecast hashes.
        if exclusion.reason != "NOT_YET_AVAILABLE":
            counts[exclusion.reason] = counts.get(exclusion.reason, 0) + 1
    return projected, rows, tuple(sorted(counts.items()))

def _model_history_guard(model, batch, rows, target, config):
    training = model.training
    _need(training.rows == rows and training.row_hash == _rows_hash(rows)
          and training.batch_hash == batch.content_sha256
          and training.cutoff_utc == target.prediction_cutoff_utc
          and model.config == config.model,
          "LEAKAGE_DETECTED", "Estimator input/history/config differs from frozen replay")

def _league_rates(model, target):
    flags = prediction_identifiability(model, target.home_team_id, target.away_team_id)
    if flags.unknown_teams:
        raise BacktestError("NO_HISTORY", "Baseline has no supported team history")
    if flags.cross_component:
        raise BacktestError("CROSS_COMPONENT", "Baseline pair spans components")
    _need(flags.home_identified and flags.away_identified,
          "PREDICTION_NOT_IDENTIFIED", "Baseline uses same strict pair support policy")
    training = model.training
    home = training.home_goals / len(training.rows)
    away = training.away_goals / len(training.rows)
    _need(all(math.isfinite(v) and 0 < v <= 100 for v in (home, away)),
          "RATE_OUT_OF_RANGE", "Prior league rates outside Phase1B bounds")
    warnings = [*training.warnings, "TARGET_METADATA_UNVERIFIED", "LEAGUE_PRIOR_AVERAGES"]
    warnings.extend("RATE_PLAUSIBILITY:" + name for name, value in (("home", home), ("away", away))
                    if not .05 <= value <= 8)
    return home, away, flags, tuple(warnings)

def generate_forecasts(batch: ImportResult, manifest: TargetManifest, *,
                       config: BacktestConfig = BacktestConfig()) -> ForecastSnapshot:
    """Stage1: zero target ground truth in returned snapshots or fitter inputs.

    Each fitter receives only a valid historical-prefix projection. Later labels
    are never accepted by this API. Manifest provenance remains self-declared
    synthetic evidence, not authenticated real pre-match knowledge.
    """
    manifest = _manifest_checked(manifest)
    batch = _batch_checked(batch)
    _need(isinstance(config, BacktestConfig), "BAD_CONFIG", "Expected frozen BacktestConfig")
    _need(batch.namespace == manifest.namespace, "IDENTITY", "Batch/manifest namespace mismatch")
    records = []
    for target in manifest.targets:
        guard = _target_guard(batch, target)
        if guard:
            origin_hash = hashlib.sha256(_json((manifest.namespace, target.fixture_id,
                                                target.prediction_cutoff_utc, guard))).hexdigest()
            for method in METHODS:
                records.append(MethodForecast(target.fixture_id, method, "abstained", guard,
                    None, None, None, origin_hash, _rows_hash(()), (), (), ("EX_ANTE_REJECTED",),
                    model_version=_method_version(method)))
            continue
        projected, rows, excluded = _project(batch, manifest, target)
        common = dict(target_id=target.fixture_id, origin_batch_hash=projected.content_sha256,
                      training_row_hash=_rows_hash(rows),
                      training_refs=tuple((r.fixture_id, r.revision) for r in rows),
                      training_exclusions=excluded)
        for method in METHODS:
            diagnostic = {}
            warnings = ("SYNTHETIC_ONLY", "TARGET_METADATA_UNVERIFIED")
            try:
                # Independent fit calls; league uses only the validated prior
                # counts/support diagnostics, never rate-ratio multipliers.
                fitter = fit_expected_goals if method == "ridge" else fit_rate_ratio
                model = fitter(projected, target.prediction_cutoff_utc, config=config.model)
                _model_history_guard(model, projected, rows, target, config)
                diagnostic = dict(model_rank=model.training.rank.rank,
                                  model_identified=model.training.rank.model_identified)
                if isinstance(model, FittedModel):
                    diagnostic.update(iterations=model.diagnostics.iterations,
                                      gradient_inf=model.diagnostics.gradient_inf)
                if method == "league":
                    home, away, flags, warnings = _league_rates(model, target)
                else:
                    forecast = predict_expected_goals(
                        model, target_fixture_id=target.fixture_id, home_team_id=target.home_team_id,
                        away_team_id=target.away_team_id, target_kickoff_utc=target.intended_kickoff_utc,
                        cutoff_utc=target.prediction_cutoff_utc)
                    _need(not forecast.prior_driven and forecast.training_row_hash == common["training_row_hash"]
                          and forecast.batch_hash == common["origin_batch_hash"]
                          and forecast.cutoff_utc == target.prediction_cutoff_utc
                          and forecast.target_fixture_id == target.fixture_id,
                          "LEAKAGE_DETECTED", "Forecast provenance/fallback differs")
                    home, away, flags, warnings = (forecast.lambda_home, forecast.lambda_away,
                                                   forecast.contrasts, forecast.warnings)
                _need(flags.home_identified and flags.away_identified,
                      "LEAKAGE_DETECTED", "Unidentified forecast returned without abstaining")
                diagnostic.update(home_identified=flags.home_identified, away_identified=flags.away_identified)
                distribution = poisson_distribution(home, away, tolerance=config.tail_tolerance,
                                                     max_goals=config.max_goals)
                result = distribution.one_x_two()
                mass = ProbabilityMass(result.home_win, result.draw, result.away_win,
                                       result.mass.retained_mass, result.mass.omitted_mass,
                                       result.mass.omitted_mass_bound)
                _probability_guard(mass, config.tail_tolerance)
                records.append(MethodForecast(**common, method=method, status="predicted", reason=None,
                    lambda_home=home, lambda_away=away, probabilities=mass, warnings=tuple(warnings),
                    model_version=_method_version(method),
                    **diagnostic))
            except (ExpectedGoalsError, GoalCapError, BacktestError) as error:
                if isinstance(error, BacktestError) and error.code == "LEAKAGE_DETECTED":
                    raise
                reason = ("TAIL_GUARD" if isinstance(error, GoalCapError) else
                          error.code.value if isinstance(error, ExpectedGoalsError) else error.code)
                records.append(MethodForecast(**common, method=method, status="abstained", reason=reason,
                    lambda_home=None, lambda_away=None, probabilities=None, warnings=tuple(warnings),
                    model_version=_method_version(method),
                    **diagnostic))
    return _seal(ForecastSnapshot(manifest, config, tuple(records)))

def _forecasts_checked(snapshot: ForecastSnapshot) -> None:
    _verify(snapshot, ForecastSnapshot)
    _need(snapshot.version == VERSION and snapshot.mass_policy == MASS_POLICY
          and snapshot.banner == BANNER and isinstance(snapshot.config, BacktestConfig),
          "SNAPSHOT_INVALID", "Forecast protocol mismatch")
    _manifest_checked(snapshot.manifest)
    expected = {(t.fixture_id, m) for t in snapshot.manifest.targets for m in METHODS}
    actual = [(r.target_id, r.method) for r in snapshot.records]
    _need(len(actual) == len(expected) and set(actual) == expected,
          "SNAPSHOT_INVALID", "Need exactly one record per target/method")
    for row in snapshot.records:
        _need(row.model_version == _method_version(row.method), "SNAPSHOT_INVALID", "Model version mismatch")
        _need(row.status in ("predicted", "abstained"), "SNAPSHOT_INVALID", "Invalid status")
        if row.status == "predicted":
            _probability_guard(row.probabilities, snapshot.config.tail_tolerance)
            _need(row.reason is None and row.home_identified is True and row.away_identified is True
                  and all(_finite_number(v) and 0 < v <= 100 for v in (row.lambda_home, row.lambda_away)),
                  "SNAPSHOT_INVALID", "Invalid forecast support/rates")
        else:
            _need(row.reason is not None and row.probabilities is None
                  and row.lambda_home is None and row.lambda_away is None,
                  "SNAPSHOT_INVALID", "Abstention cannot contain partial probabilities")

@dataclass(frozen=True, slots=True)
class EvaluationLabel:
    target_id: str
    status: str
    reason: str | None
    revision: int | None
    home_goals_90: int | None
    away_goals_90: int | None
    actual: str | None
    available_at_utc: datetime | None

@dataclass(frozen=True, slots=True)
class LabelSnapshot:
    forecast_hash: str
    evaluation_cutoff_utc: datetime
    evaluation_batch_hash: str
    labels: tuple[EvaluationLabel, ...]
    policy: str = LABEL_POLICY
    banner: str = BANNER
    sha256: str = ""

def select_labels(batch: ImportResult, forecasts: ForecastSnapshot, *,
                  evaluation_cutoff_utc: datetime) -> LabelSnapshot:
    """Stage2: frozen later strict-as-of labels, exact fixture join, no fallback."""
    _forecasts_checked(forecasts)
    batch = _batch_checked(batch)
    _need(batch.namespace == forecasts.manifest.namespace, "IDENTITY", "Evaluation namespace mismatch")
    cutoff = _utc(evaluation_cutoff_utc, "evaluation_cutoff_utc")
    _need(all(cutoff > t.intended_kickoff_utc for t in forecasts.manifest.targets),
          "LABEL_SNAPSHOT_TOO_EARLY", "Evaluation snapshot must follow all intended target kickoffs")
    selection = select_as_of(batch, cutoff, include_synthetic=True)
    selected = {r.fixture_id: r for r in selection.observations}
    priorities = ("UNCERTAIN_REVISION", "LICENCE_NOT_CLEARED", "NOT_FINISHED_FT90",
                  "COARSE_KICKOFF", "UNKNOWN_AVAILABILITY", "NOT_YET_AVAILABLE")
    labels = []
    for target in forecasts.manifest.targets:
        row = selected.get(target.fixture_id)
        reason = None
        if row is None:
            reasons = {e.reason for e in selection.exclusions if e.fixture_id == target.fixture_id}
            reason = next((code for code in priorities if code in reasons), "MISSING_LABEL")
        elif not _same_identity(row, target):
            reason = "LABEL_IDENTITY_MISMATCH"
        elif row.kickoff_utc != target.intended_kickoff_utc:
            reason = "KICKOFF_CHANGED"
        elif not (target.prediction_cutoff_utc < row.available_at_utc < cutoff):
            reason = "LABEL_AVAILABILITY_INVALID"
        elif row.available_at_utc < target.intended_kickoff_utc + timedelta(minutes=90):
            reason = "LABEL_AVAILABILITY_INVALID"
        if reason:
            labels.append(EvaluationLabel(target.fixture_id, "excluded", reason,
                          None, None, None, None, None))
        else:
            actual = ("H" if row.home_goals_90 > row.away_goals_90
                      else "A" if row.home_goals_90 < row.away_goals_90 else "D")
            labels.append(EvaluationLabel(target.fixture_id, "eligible", None, row.revision,
                          row.home_goals_90, row.away_goals_90, actual, row.available_at_utc))
    return _seal(LabelSnapshot(forecasts.sha256, cutoff, batch.content_sha256, tuple(labels)))

@dataclass(frozen=True, slots=True)
class ScoreRow:
    target_id: str
    method: str
    status: str
    reason: str | None
    actual: str | None
    scores: Scores | None

@dataclass(frozen=True, slots=True)
class MetricSummary:
    n: int
    log_loss: float | None
    brier: float | None
    rps: float | None
    max_log_loss_truncation_bound: float | None
    evidence: str

@dataclass(frozen=True, slots=True)
class MethodSummary:
    method: str
    model_version: str
    manifest_n: int
    forecasted_n: int
    abstained_n: int
    abstention_reasons: tuple[tuple[str, int], ...]
    predicted_missing_label_n: int
    scoring_error_n: int
    scoring_error_reasons: tuple[tuple[str, int], ...]
    unpaired: MetricSummary
    paired: MetricSummary
    max_omitted_bound: float | None

@dataclass(frozen=True, slots=True)
class CalibrationBin:
    method: str
    category: str
    lower: float
    upper: float
    n: int
    mean_forecast: float | None
    observed_frequency: float | None
    evidence: str

@dataclass(frozen=True, slots=True)
class SeasonComparison:
    season_start_year: int
    manifest_n: int
    eligible_label_n: int
    paired_ids: tuple[str, ...]
    methods: tuple[tuple[str, MetricSummary], ...]

@dataclass(frozen=True, slots=True)
class BacktestReport:
    forecast_hash: str
    label_hash: str
    manifest_n: int
    eligible_label_n: int
    label_exclusion_reasons: tuple[tuple[str, int], ...]
    paired_ids: tuple[str, ...]
    methods: tuple[MethodSummary, ...]
    per_season: tuple[SeasonComparison, ...]
    calibration: tuple[CalibrationBin, ...]
    rows: tuple[ScoreRow, ...]
    config: BacktestConfig
    mass_policy: str = MASS_POLICY
    uncertainty: str = "not estimated; descriptive synthetic counts only"
    banner: str = BANNER
    sha256: str = ""

def _labels_checked(forecasts: ForecastSnapshot, labels: LabelSnapshot) -> None:
    _verify(labels, LabelSnapshot)
    _need(labels.forecast_hash == forecasts.sha256 and labels.policy == LABEL_POLICY
          and labels.banner == BANNER, "SNAPSHOT_INVALID", "Label policy/forecast linkage mismatch")
    targets = {t.fixture_id: t for t in forecasts.manifest.targets}
    ids = [r.target_id for r in labels.labels]
    _need(len(ids) == len(targets) and set(ids) == set(targets),
          "SNAPSHOT_INVALID", "Labels must cover exact full manifest")
    cutoff = _utc(labels.evaluation_cutoff_utc, "evaluation_cutoff_utc")
    for label in labels.labels:
        target = targets[label.target_id]
        _need(cutoff > target.intended_kickoff_utc, "LABEL_SNAPSHOT_TOO_EARLY", "Evaluation precedes target")
        if label.status == "eligible":
            _need(type(label.home_goals_90) is int and label.home_goals_90 >= 0
                  and type(label.away_goals_90) is int and label.away_goals_90 >= 0
                  and type(label.revision) is int and label.revision >= 0 and label.reason is None,
                  "LABEL_INVALID", "Invalid final FT90 label")
            expected = ("H" if label.home_goals_90 > label.away_goals_90
                        else "A" if label.home_goals_90 < label.away_goals_90 else "D")
            available = _utc(label.available_at_utc, "label availability")
            _need(label.actual == expected and target.prediction_cutoff_utc < available < cutoff
                  and available >= target.intended_kickoff_utc + timedelta(minutes=90),
                  "LABEL_INVALID", "Outcome/availability mismatch")
        else:
            _need(label.status == "excluded" and label.reason is not None
                  and all(v is None for v in (label.actual, label.revision, label.home_goals_90,
                                              label.away_goals_90, label.available_at_utc)),
                  "LABEL_INVALID", "Excluded labels cannot expose a fallback outcome")

def _counts(codes) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return tuple(sorted(counts.items()))

def _summary(rows, minimum: int) -> MetricSummary:
    values = [r.scores for r in rows if r.status == "scored"]
    n = len(values)
    if not n:
        return MetricSummary(0, None, None, None, None, "INSUFFICIENT_EVIDENCE")
    return MetricSummary(n, math.fsum(v.log_loss for v in values)/n,
                         math.fsum(v.brier for v in values)/n,
                         math.fsum(v.rps for v in values)/n,
                         max(v.log_loss_truncation_bound for v in values),
                         "INSUFFICIENT_EVIDENCE" if n < minimum else "DESCRIPTIVE_ONLY")

def evaluate_forecasts(forecasts: ForecastSnapshot, labels: LabelSnapshot) -> BacktestReport:
    """Stage3: score frozen predictions without fitting or accessing input data.

    Headline method summaries/calibration use the identical paired scored set.
    Individual coverage/unpaired scores remain explicit and cannot substitute
    for a shared comparison population.
    """
    _forecasts_checked(forecasts)
    _labels_checked(forecasts, labels)
    by_label = {label.target_id: label for label in labels.labels}
    attempts = []
    for forecast in forecasts.records:
        label = by_label[forecast.target_id]
        if forecast.status == "abstained":
            attempts.append(ScoreRow(forecast.target_id, forecast.method, "excluded",
                                    "FORECAST:" + forecast.reason, None, None))
        elif label.status == "excluded":
            attempts.append(ScoreRow(forecast.target_id, forecast.method, "excluded",
                                    "LABEL:" + label.reason, None, None))
        else:
            try:
                values = score_1x2(forecast.probabilities, label.actual,
                                   tail_tolerance=forecasts.config.tail_tolerance)
                attempts.append(ScoreRow(forecast.target_id, forecast.method, "scored", None,
                                        label.actual, values))
            except BacktestError as error:
                attempts.append(ScoreRow(forecast.target_id, forecast.method, "error",
                                        error.code, label.actual, None))
    scored_sets = [{r.target_id for r in attempts if r.method == method and r.status == "scored"}
                   for method in METHODS]
    paired_ids = tuple(sorted(set.intersection(*scored_sets)))
    paired = set(paired_ids)
    summaries, calibration = [], []
    record_map = {(r.target_id, r.method): r for r in forecasts.records}
    for method in METHODS:
        predictions = [r for r in forecasts.records if r.method == method]
        method_rows = [r for r in attempts if r.method == method]
        forecasted = [r for r in predictions if r.status == "predicted"]
        errors = [r for r in method_rows if r.status == "error"]
        summaries.append(MethodSummary(
            method, _method_version(method), len(forecasts.manifest.targets), len(forecasted),
            len(predictions)-len(forecasted),
            _counts(r.reason for r in predictions if r.status == "abstained"),
            sum(by_label[r.target_id].status == "excluded" for r in forecasted),
            len(errors), _counts(r.reason for r in errors),
            _summary(method_rows, forecasts.config.min_evidence),
            _summary([r for r in method_rows if r.target_id in paired], forecasts.config.min_evidence),
            max((r.probabilities.omitted_bound for r in forecasted), default=None)))
        bins = forecasts.config.calibration_bins
        for index, category in enumerate(("H", "D", "A")):
            for number in range(bins):
                values, outcomes = [], []
                for fixture in paired_ids:
                    p = record_map[fixture, method].probabilities
                    value = (p.home, p.draw, p.away)[index]
                    bucket = min(int(value*bins), bins-1)
                    if bucket == number:
                        values.append(value)
                        outcomes.append(by_label[fixture].actual == category)
                n = len(values)
                calibration.append(CalibrationBin(
                    method, category, number/bins, (number+1)/bins, n,
                    math.fsum(values)/n if n else None,
                    sum(outcomes)/n if n else None,
                    "INSUFFICIENT_EVIDENCE" if n < forecasts.config.min_evidence else "DESCRIPTIVE_ONLY"))
    seasons = []
    for year in sorted({t.season_start_year for t in forecasts.manifest.targets}):
        ids = {t.fixture_id for t in forecasts.manifest.targets if t.season_start_year == year}
        season_paired = tuple(sorted(ids & paired))
        seasons.append(SeasonComparison(
            year, len(ids), sum(by_label[i].status == "eligible" for i in ids), season_paired,
            tuple((m, _summary([r for r in attempts if r.method == m and r.target_id in season_paired],
                                forecasts.config.min_evidence)) for m in METHODS)))
    return _seal(BacktestReport(
        forecasts.sha256, labels.sha256, len(forecasts.manifest.targets),
        sum(label.status == "eligible" for label in labels.labels),
        _counts(label.reason for label in labels.labels if label.status == "excluded"),
        paired_ids, tuple(summaries), tuple(seasons), tuple(calibration),
        tuple(attempts), forecasts.config))
