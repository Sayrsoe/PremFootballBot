"""B1 numerical laboratory on invented matches ONLY; no real-data adapter.

Raw (not normalized) match weights multiply both goal likelihoods. Ridge is
unchanged, so decay changes effective regularization. No forecasts, scoring,
source authorization, I/O, wall clock, RNG or existing training functions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import re

VERSION = "phase4c2b1-weighted-poisson-v1"
STATUS = "INVENTED_NUMERICAL_TEST_ONLY_NOT_MODEL_AUTHORIZED"
HALF_LIFE_CANDIDATES = (None, 90, 180, 365)  # Design candidates, never selected here.
MAX_MATCHES = 10000
MAX_TEAMS = 20


class WeightedPoissonError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _need(condition, code, message):
    if not condition:
        raise WeightedPoissonError(code, message)


def _number(value, lower, upper, name):
    _need(type(value) in (int, float) and lower <= value <= upper,
          "INVALID_NUMBER", f"{name} must be finite in [{lower},{upper}]")
    return float(value)


def _age(value):
    _need(type(value) is int and 0 <= value <= 1000000, "INVALID_AGE", "age_days must be an integer0..1000000")


def _half_life(value):
    if value is not None:
        _need(type(value) in (int, float) and 0 < value <= 1e9,
              "INVALID_HALF_LIFE", "Use None for no decay or finite positive half-life<=1e9 days")
    return None if value is None else float(value)


def decay_weights(ages: tuple[int, ...], half_life_days: float | None) -> tuple[float, ...]:
    """Explicit ages, no inferred cutoff; zero/underflow weights fail closed."""
    _need(type(ages) is tuple and 1 <= len(ages) <= MAX_MATCHES, "INPUT_TYPE", "Bounded immutable ages required")
    half_life = _half_life(half_life_days)
    result = []
    for age in ages:
        _age(age)  # Also validate ages in the no-decay control.
        weight = 1.0 if half_life is None else 2.0 ** (-age / half_life)
        _need(math.isfinite(weight) and 0 < weight <= 1, "INVALID_WEIGHT", "Decay underflow/invalid weight; never clip or drop")
        result.append(weight)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class InventedMatch:
    fixture_id: str
    home: str
    away: str
    home_goals: int
    away_goals: int
    age_days: int
    record_kind: str = STATUS


@dataclass(frozen=True, slots=True)
class WeightedConfig:
    half_life_days: float | None = None
    ridge: float = 4.0
    max_iterations: int = 100
    gradient_tolerance: float = 1e-7

    def __post_init__(self):
        _half_life(self.half_life_days)
        _number(self.ridge, 0.01, 10000, "ridge")
        _number(self.gradient_tolerance, 1e-10, 1e-5, "gradient_tolerance")
        _need(type(self.max_iterations) is int and 1 <= self.max_iterations <= 200,
              "INVALID_CONFIG", "max_iterations must be1..200")


@dataclass(frozen=True, slots=True)
class WeightSummary:
    matches: int
    sum_weights: float
    minimum: float
    maximum: float
    effective_sample_size: float


def weight_summary(weights: tuple[float, ...]) -> WeightSummary:
    """Match-level ESS=(sum w)^2/sum(w^2), scaled to avoid square underflow."""
    _need(type(weights) is tuple and 1 <= len(weights) <= MAX_MATCHES, "INPUT_TYPE", "Bounded immutable weights required")
    _need(all(type(w) in (int, float) and 0 < w <= 1 for w in weights),
          "INVALID_WEIGHT", "Every weight must be finite in(0,1]")
    maximum = float(max(weights))
    scaled = tuple(w / maximum for w in weights)
    ess = math.fsum(scaled) ** 2 / math.fsum(w * w for w in scaled)
    _need(math.isfinite(ess) and 1 - 1e-12 <= ess <= len(weights) + 1e-10,
          "NUMERIC_ERROR", "Invalid effective sample size")
    return WeightSummary(len(weights), math.fsum(weights), float(min(weights)), maximum, ess)


def _prepare(matches, weights):
    _need(type(matches) is tuple and 1 <= len(matches) <= MAX_MATCHES
          and all(type(r) is InventedMatch for r in matches), "INPUT_TYPE", "InventedMatch tuple required; no archive adapters")
    summary = weight_summary(weights)
    _need(len(matches) == len(weights), "INPUT_SHAPE", "Exactly one weight per match")
    for row in matches:
        _need(row.record_kind == STATUS, "INPUT_TYPE", "Invented numerical-test marker required")
        for value in (row.fixture_id, row.home, row.away):
            _need(type(value) is str and re.fullmatch(r"toy:[A-Za-z0-9_-]{1,60}", value),
                  "IDENTITY", "Explicit bounded toy: identifiers required")
        _need(row.home != row.away, "IDENTITY", "Distinct teams required")
        _age(row.age_days)
        _need(all(type(g) is int and 0 <= g <= 100 for g in (row.home_goals, row.away_goals)),
              "INVALID_GOALS", "Ordinary integer goal counts0..100 required")
    _need(len({r.fixture_id for r in matches}) == len(matches), "IDENTITY", "Duplicate fixture ID")
    paired = tuple(sorted(zip(matches, weights), key=lambda pair: (-pair[0].age_days, pair[0].fixture_id)))
    teams = tuple(sorted({t for row in matches for t in (row.home, row.away)}))
    _need(2 <= len(teams) <= MAX_TEAMS, "INPUT_SHAPE", "Require2..20 observed teams")
    index = {team: i for i, team in enumerate(teams)}
    observations = []
    n = len(teams)
    for row, w in paired:
        home, away = index[row.home], index[row.away]
        observations.append(((0, 1, 2 + home, 2 + n + away), row.home_goals, float(w)))
        observations.append(((0, 2 + away, 2 + n + home), row.away_goals, float(w)))
    return teams, paired, tuple(observations), summary


@dataclass(frozen=True, slots=True)
class ObjectiveEvaluation:
    objective: float
    negative_log_likelihood: float
    penalty: float
    gradient: tuple[float, ...]
    hessian: tuple[tuple[float, ...], ...]


def _calculate(theta, observations, ridge):
    _need(all(type(t) in (int, float) and -100 < t < 100 for t in theta),
          "NUMERIC_RANGE", "Finite parameters with abs<100 required; never clip")
    size = len(theta)
    gradient = [0.0, 0.0] + [ridge * t for t in theta[2:]]
    hessian = [[0.0] * size for _ in theta]
    for j in range(2, size): hessian[j][j] = ridge
    terms = []
    for active, goals, weight in observations:
        eta = math.fsum(theta[j] for j in active)
        rate = math.exp(eta)
        curvature = weight * rate
        _need(math.isfinite(curvature) and curvature > 0, "NUMERIC_RANGE", "Weighted curvature underflow/overflow")
        terms.append(weight * (rate - goals * eta + math.lgamma(goals + 1)))
        residual = weight * (rate - goals)
        for j in active:
            gradient[j] += residual
            for k in active: hessian[j][k] += curvature
    nll = math.fsum(terms)
    penalty = ridge / 2 * math.fsum(t * t for t in theta[2:])
    _need(all(math.isfinite(x) for x in (nll, penalty, *gradient, *(x for row in hessian for x in row))),
          "NUMERIC_ERROR", "Nonfinite objective/derivatives")
    return ObjectiveEvaluation(nll + penalty, nll, penalty, tuple(gradient), tuple(tuple(row) for row in hessian))


def evaluate_objective(matches: tuple[InventedMatch, ...], weights: tuple[float, ...],
                       theta: tuple[float, ...], *, ridge: float = 4.0) -> ObjectiveEvaluation:
    """Pure weighted NLL/gradient/Hessian. Parameter order:mu,h,attack,vulnerability.

    Team blocks use sorted IDs. Provided weights align with the input match
    order; sorting preserves each pair. Intercept/home effect are unpenalized.
    """
    teams, _, observations, _ = _prepare(matches, weights)
    ridge = _number(ridge, 0.01, 10000, "ridge")
    _need(type(theta) is tuple and len(theta) == 2 + 2 * len(teams), "INPUT_SHAPE", "Parameter dimension/type mismatch")
    return _calculate(theta, observations, ridge)


def _newton_step(matrix, rhs):
    """Textbook dense Cholesky; relative pivot is a guard, NOT a condition number."""
    n = len(rhs)
    scale = max(matrix[i][i] for i in range(n))
    lower = [[0.0] * n for _ in range(n)]
    minimum = 1.0
    for i in range(n):
        for j in range(i + 1):
            pivot = matrix[i][j] - math.fsum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                _need(math.isfinite(pivot) and pivot > 1e-12 * scale,
                      "ILL_CONDITIONED", "Cholesky pivot too small/nonpositive; no jitter or fallback")
                minimum = min(minimum, pivot / scale)
                lower[i][j] = math.sqrt(pivot)
            else:
                lower[i][j] = pivot / lower[j][j]
    intermediate = []
    for i in range(n):
        intermediate.append((rhs[i] - math.fsum(lower[i][j] * intermediate[j] for j in range(i))) / lower[i][i])
    step = [0.0] * n
    for i in reversed(range(n)):
        step[i] = (intermediate[i] - math.fsum(lower[j][i] * step[j] for j in range(i + 1, n))) / lower[i][i]
    _need(all(math.isfinite(x) for x in step), "NUMERIC_ERROR", "Nonfinite Newton direction")
    return step, minimum


@dataclass(frozen=True, slots=True)
class TeamEstimate:
    team: str
    attack: float
    defense_vulnerability: float
    exposure: WeightSummary


@dataclass(frozen=True, slots=True)
class WeightedDiagnostics:
    iterations: int
    backtracks: int
    objective_trace: tuple[float, ...]
    negative_log_likelihood: float
    penalty: float
    gradient_inf_norm: float
    gradient_threshold: float
    minimum_relative_pivot: float
    weights: WeightSummary
    weighted_observed_home: float
    weighted_observed_away: float
    weighted_fitted_home: float
    weighted_fitted_away: float


@dataclass(frozen=True, slots=True)
class WeightedFit:
    config: WeightedConfig
    input_sha256: str
    intercept: float
    home_advantage: float
    teams: tuple[TeamEstimate, ...]
    diagnostics: WeightedDiagnostics
    version: str = VERSION
    status: str = STATUS
    real_data_authorized: bool = False
    prediction_api_available: bool = False
    strict_point_in_time_eligible: bool = False
    sha256: str = ""


def _json(value):
    return json.dumps(asdict(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")


def _seal(value):
    return replace(value, sha256=hashlib.sha256(_json(replace(value, sha256=""))).hexdigest())


def fit_invented_matches(matches: tuple[InventedMatch, ...], config: WeightedConfig = WeightedConfig()) -> WeightedFit:
    """Fit invented numerical examples only. No chronology/source/forecast API."""
    _need(type(config) is WeightedConfig, "INVALID_CONFIG", "WeightedConfig required")
    config.__post_init__()
    config = WeightedConfig(_half_life(config.half_life_days), float(config.ridge),
                            config.max_iterations, float(config.gradient_tolerance))
    _need(type(matches) is tuple and 1 <= len(matches) <= MAX_MATCHES
          and all(type(r) is InventedMatch for r in matches), "INPUT_TYPE", "InventedMatch tuple required")
    weights = decay_weights(tuple(r.age_days for r in matches), config.half_life_days)
    teams, paired, observations, summary = _prepare(matches, weights)
    home_total = math.fsum(r.home_goals * w for r, w in paired)
    away_total = math.fsum(r.away_goals * w for r, w in paired)
    _need(home_total > 0 and away_total > 0, "DEGENERATE_DATA", "Both weighted venue goal totals must be positive")
    # Differences of logs avoid overflowing/underflowing an intermediate ratio.
    theta = [math.log(away_total) - math.log(summary.sum_weights),
             math.log(home_total) - math.log(away_total)] + [0.0] * (2 * len(teams))
    current = _calculate(theta, observations, config.ridge)
    trace, backtracks, minimum_pivot = [current.objective], 0, 1.0
    # Match the existing absolute tolerance for mass>=1; tighten it for tiny
    # mass so down-weighting cannot itself manufacture gradient convergence.
    threshold = config.gradient_tolerance * min(1.0, summary.sum_weights)
    for iteration in range(config.max_iterations + 1):
        step, pivot = _newton_step(current.hessian, current.gradient)
        minimum_pivot = min(minimum_pivot, pivot)
        norm = max(abs(g) for g in current.gradient)
        if norm <= threshold: break
        _need(iteration < config.max_iterations, "NOT_CONVERGED", "Iteration budget exhausted")
        descent = math.fsum(g * s for g, s in zip(current.gradient, step))
        _need(math.isfinite(descent) and descent > 0, "NUMERIC_ERROR", "Non-descent Newton direction")
        scale = 1.0
        for _ in range(50):
            trial = [t - scale * s for t, s in zip(theta, step)]
            try:
                evaluated = _calculate(trial, observations, config.ridge)
            except WeightedPoissonError as error:
                if error.code not in ("NUMERIC_RANGE", "NUMERIC_ERROR"): raise
                evaluated = None
            if evaluated is not None and evaluated.objective <= current.objective - 1e-4 * scale * descent:
                break
            scale *= 0.5
            backtracks += 1
        else:
            raise WeightedPoissonError("NOT_CONVERGED", "Line search exhausted; no approximate result")
        theta, current = trial, evaluated
        trace.append(current.objective)
    rates = tuple(math.exp(math.fsum(theta[j] for j in active)) for active, _, _ in observations)
    fitted_home = math.fsum(rate * obs[2] for rate, obs in zip(rates[::2], observations[::2]))
    fitted_away = math.fsum(rate * obs[2] for rate, obs in zip(rates[1::2], observations[1::2]))
    effects = tuple(TeamEstimate(team, theta[2 + i], theta[2 + len(teams) + i],
        weight_summary(tuple(w for row, w in paired if team in (row.home, row.away)))) for i, team in enumerate(teams))
    diagnostics = WeightedDiagnostics(iteration, backtracks, tuple(trace), current.negative_log_likelihood,
        current.penalty, norm, threshold, minimum_pivot, summary, home_total, away_total, fitted_home, fitted_away)
    encoded = json.dumps([(asdict(row), float(w)) for row, w in paired], sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf8")
    return _seal(WeightedFit(config, hashlib.sha256(encoded).hexdigest(), theta[0], theta[1], effects, diagnostics))


def weighted_fit_json(model: WeightedFit) -> bytes:
    """Internal seal/flags check, NOT authorization; replay before trusting."""
    _need(type(model) is WeightedFit and model == _seal(model), "ARTIFACT_INVALID", "Typed sealed WeightedFit required")
    _need(model.version == VERSION and model.status == STATUS and model.real_data_authorized is False
          and model.prediction_api_available is False and model.strict_point_in_time_eligible is False,
          "ARTIFACT_INVALID", "Numerical-only restrictions changed")
    return _json(model)


def verify_weighted_fit(model, matches):
    """Exact replay in the same Python/math runtime; checksums are not signatures."""
    original = weighted_fit_json(model)
    replay = fit_invented_matches(matches, model.config)
    _need(original == weighted_fit_json(replay), "REPLAY_MISMATCH", "Invented-input replay differs")
    return True
