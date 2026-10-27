"""Synthetic-only expected-goal estimation; no feeds, odds or real-data training.

Direct module import preserves earlier APIs. Gamma-Poisson rate ratios are an
approximate comparison, not an oracle for the joint penalized likelihood.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from fractions import Fraction
import hashlib
import json
import math
from numbers import Real
import re

from .match_data import ImportResult, MatchDataError, Observation, parse_synthetic_json, select_as_of
from .poisson import MAX_DISTRIBUTION_RATE, PoissonDistribution, poisson_distribution

class ErrorCode(str, Enum):
    EMPTY_TRAINING = "EMPTY_TRAINING"
    DEGENERATE_ZERO_GOALS = "DEGENERATE_ZERO_GOALS"
    BAD_CONFIG = "BAD_CONFIG"
    GOALS_OUT_OF_RANGE = "GOALS_OUT_OF_RANGE"
    NOT_CONVERGED = "NOT_CONVERGED"
    HESSIAN_NOT_PD = "HESSIAN_NOT_PD"
    RATE_OUT_OF_RANGE = "RATE_OUT_OF_RANGE"
    CUTOFF_AFTER_KICKOFF = "CUTOFF_AFTER_KICKOFF"
    CUTOFF_MISMATCH = "CUTOFF_MISMATCH"
    NO_HISTORY = "NO_HISTORY"
    CROSS_COMPONENT = "CROSS_COMPONENT"
    PREDICTION_NOT_IDENTIFIED = "PREDICTION_NOT_IDENTIFIED"
    TARGET_IN_TRAINING = "TARGET_IN_TRAINING"
    INPUT_INVALID = "INPUT_INVALID"
    NUMERIC_ERROR = "NUMERIC_ERROR"

class ExpectedGoalsError(ValueError):
    """Typed failure: no partial fitted model/forecast is returned."""
    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        super().__init__(f"{code.value}: {message}")

def _check(condition: bool, code: ErrorCode, message: str) -> None:
    if not condition:
        raise ExpectedGoalsError(code, message)

def _positive(value, name: str) -> float:
    _check(isinstance(value, Real) and not isinstance(value, bool), ErrorCode.BAD_CONFIG,
           name + " must be a finite positive real")
    try:
        number = float(value)
    except OverflowError:
        raise ExpectedGoalsError(ErrorCode.BAD_CONFIG, name + " is outside float range") from None
    _check(math.isfinite(number) and number > 0, ErrorCode.BAD_CONFIG,
           name + " must be finite and positive")
    return number

@dataclass(frozen=True, slots=True)
class ModelConfig:
    tau: float = 4.0
    kappa: float = 4.0
    g_max: int = 20
    n_min: int = 6
    max_iterations: int = 100
    gradient_tolerance: float = 1e-8
    decrement_tolerance: float = 1e-12
    max_teams: int = 40

    def __post_init__(self):
        for name in ("tau", "kappa", "gradient_tolerance", "decrement_tolerance"):
            _positive(getattr(self, name), name)
        for name, lower, upper in (("g_max", 1, 1000), ("n_min", 1, 10000),
                                    ("max_iterations", 1, 1000), ("max_teams", 2, 40)):
            value = getattr(self, name)
            _check(type(value) is int and lower <= value <= upper, ErrorCode.BAD_CONFIG,
                   f"{name} must be an integer in [{lower},{upper}]")
        _check(self.gradient_tolerance < 1 and self.decrement_tolerance < 1,
               ErrorCode.BAD_CONFIG, "Numerical tolerances must be below 1")

@dataclass(frozen=True, slots=True)
class RankDiagnostics:
    rank: int
    parameter_count: int
    maximum_data_rank: int
    model_identified: bool
    components: tuple[tuple[str, ...], ...]
    basis: tuple[tuple[Fraction, ...], ...]

@dataclass(frozen=True, slots=True)
class TrainingData:
    namespace: str
    cutoff_utc: datetime
    batch_hash: str
    row_hash: str
    rows: tuple[Observation, ...]
    teams: tuple[str, ...]
    excluded_reasons: tuple[tuple[str, int], ...]
    appearances: tuple[tuple[str, int], ...]
    home_goals: int
    away_goals: int
    rank: RankDiagnostics
    warnings: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class RateFactors:
    team_id: str
    scored: int
    conceded: int
    exposure_for: float
    exposure_against: float
    alpha: float
    beta: float

@dataclass(frozen=True, slots=True)
class FittedRateRatio:
    config: ModelConfig
    training: TrainingData
    baseline_home: float
    baseline_away: float
    factors: tuple[RateFactors, ...]

@dataclass(frozen=True, slots=True)
class ContrastDiagnostics:
    home_identified: bool
    away_identified: bool
    cross_component: bool
    unknown_teams: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ExpectedGoalsForecast:
    lambda_home: float
    lambda_away: float
    method: str
    prior_driven: bool
    contrasts: ContrastDiagnostics
    model_identified: bool
    target_fixture_id: str
    home_team_id: str
    away_team_id: str
    target_kickoff_utc: datetime
    cutoff_utc: datetime
    training_row_hash: str
    batch_hash: str
    warnings: tuple[str, ...]

    def probabilities(self) -> PoissonDistribution:
        """Integrate through unchanged Phase 1B, retaining its omitted mass."""
        return poisson_distribution(self.lambda_home, self.lambda_away)

def _utc(value, name: str) -> datetime:
    _check(isinstance(value, datetime), ErrorCode.INPUT_INVALID, name + " must be an aware UTC datetime")
    _check(value.tzinfo is not None and value.utcoffset() == timedelta(0),
           ErrorCode.INPUT_INVALID, name + " must have an explicit UTC offset of zero")
    return value.astimezone(timezone.utc)

def _plain(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value

def _json(value) -> bytes:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf8")

def _validated(batch: ImportResult) -> ImportResult:
    _check(isinstance(batch, ImportResult), ErrorCode.INPUT_INVALID,
           "Use parse_synthetic_json(...).require_valid()")
    try:
        batch.require_valid()
        # Reparse through the unchanged Phase2A contract, not just a trusted flag.
        payload = {"schema_version": 1, "namespace": batch.namespace,
                   "teams": [asdict(t) for t in batch.teams],
                   "source_documents": [asdict(s) for s in batch.source_documents],
                   "records": [asdict(r) for r in batch.observations]}
        checked = parse_synthetic_json(_json(payload)).require_valid()
        _check(checked.content_sha256 == batch.content_sha256, ErrorCode.INPUT_INVALID,
               "Batch content hash does not match validated content")
        return checked
    except (MatchDataError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, ExpectedGoalsError):
            raise
        raise ExpectedGoalsError(ErrorCode.INPUT_INVALID, "Batch failed Phase2A revalidation") from error

def _design(teams: tuple[str, ...], home: str, away: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    n = len(teams)
    i, j = teams.index(home), teams.index(away)
    h, a = [0] * (2 + 2*n), [0] * (2 + 2*n)
    h[0] = a[0] = 1
    h[1], h[2+i], h[2+n+j] = 1, 1, -1
    a[2+j], a[2+n+i] = 1, -1
    return tuple(h), tuple(a)

def _reduce(vector, basis):
    row = [Fraction(v) for v in vector]
    for existing in basis:
        pivot = next(i for i, value in enumerate(existing) if value)
        if row[pivot]:
            multiple = row[pivot]
            row = [x - multiple*y for x, y in zip(row, existing)]
    return row

def _rank_basis(designs) -> tuple[tuple[Fraction, ...], ...]:
    basis = []
    for vector in sorted(set(designs)):
        row = _reduce(vector, basis)
        pivot = next((i for i, value in enumerate(row) if value), None)
        if pivot is not None:
            divisor = row[pivot]
            basis.append(tuple(value/divisor for value in row))
            basis.sort(key=lambda r: next(i for i, v in enumerate(r) if v))
    return tuple(basis)

def _components(teams, rows):
    neighbors = {team: set() for team in teams}
    for row in rows:
        neighbors[row.home_team_id].add(row.away_team_id)
        neighbors[row.away_team_id].add(row.home_team_id)
    remaining, groups = set(teams), []
    while remaining:
        pending, group = [min(remaining)], set()
        while pending:
            team = pending.pop()
            if team not in group:
                group.add(team)
                pending.extend(sorted(neighbors[team] - group))
        remaining -= group
        groups.append(tuple(sorted(group)))
    return tuple(sorted(groups))

def _prepare(batch: ImportResult, cutoff_utc: datetime, config: ModelConfig) -> TrainingData:
    _check(isinstance(config, ModelConfig), ErrorCode.BAD_CONFIG, "config must be ModelConfig")
    cutoff = _utc(cutoff_utc, "cutoff_utc")
    checked = _validated(batch)
    selection = select_as_of(checked, cutoff, include_synthetic=True)
    rows = tuple(sorted(selection.observations, key=lambda r: (r.kickoff_utc, r.fixture_id, r.revision)))
    _check(bool(rows), ErrorCode.EMPTY_TRAINING, "No eligible observations strictly before cutoff")
    for row in rows:
        _check(row.is_synthetic is True and row.licence_status == "CLEARED"
               and row.record_type == "result" and row.status == "FINISHED"
               and row.result_basis == "FT90" and row.kickoff_precision == "exact",
               ErrorCode.INPUT_INVALID, "Selected observation violates synthetic FT90 policy")
        kickoff = _utc(row.kickoff_utc, "selected kickoff")
        available = _utc(row.available_at_utc, "selected availability")
        try:
            earliest = kickoff + timedelta(minutes=90)
        except OverflowError:
            raise ExpectedGoalsError(ErrorCode.INPUT_INVALID, "Selected kickoff exceeds datetime range") from None
        _check(earliest <= available < cutoff, ErrorCode.INPUT_INVALID,
               "Selected result violates historical availability")
        for goals in (row.home_goals_90, row.away_goals_90):
            _check(type(goals) is int and goals >= 0, ErrorCode.INPUT_INVALID, "Invalid selected goals")
            _check(goals <= config.g_max, ErrorCode.GOALS_OUT_OF_RANGE, "Selected goals exceed g_max")
    home_total = sum(r.home_goals_90 for r in rows)
    away_total = sum(r.away_goals_90 for r in rows)
    _check(home_total > 0 and away_total > 0, ErrorCode.DEGENERATE_ZERO_GOALS,
           "Both home and away aggregate goals must be strictly positive")
    teams = tuple(sorted({r.home_team_id for r in rows} | {r.away_team_id for r in rows}))
    _check(len(teams) <= config.max_teams, ErrorCode.BAD_CONFIG, "Too many participating teams for dense fit")
    basis = _rank_basis([z for r in rows for z in _design(teams, r.home_team_id, r.away_team_id)])
    rank = RankDiagnostics(len(basis), 2+2*len(teams), 2*len(teams), len(basis) == 2*len(teams),
                           _components(teams, rows), basis)
    excluded: dict[str, int] = {}
    for item in selection.exclusions:
        excluded[item.reason] = excluded.get(item.reason, 0) + 1
    appearances = tuple((t, sum(t in (r.home_team_id, r.away_team_id) for r in rows)) for t in teams)
    warnings = ["SYNTHETIC_ONLY"]
    if not rank.model_identified:
        warnings.append("MODEL_NOT_IDENTIFIED")
    if len(rank.components) > 1:
        warnings.append("DISCONNECTED_TRAINING")
    warnings.extend("SPARSE_TEAM:" + t for t, count in appearances if count < config.n_min)
    content = []
    for row in rows:
        values = asdict(row)
        del values["retrieved_at_utc"]
        content.append(values)
    return TrainingData(checked.namespace, cutoff, checked.content_sha256,
                        hashlib.sha256(_json(content)).hexdigest(), rows, teams,
                        tuple(sorted(excluded.items())), appearances, home_total, away_total,
                        rank, tuple(warnings))

def fit_rate_ratio(batch: ImportResult, cutoff_utc: datetime, *,
                   config: ModelConfig = ModelConfig()) -> FittedRateRatio:
    """Approximate exposure-adjusted Gamma-Poisson comparison; not joint MLE."""
    training = _prepare(batch, cutoff_utc, config)
    hbar = training.home_goals / len(training.rows)
    abar = training.away_goals / len(training.rows)
    factors = []
    for team in training.teams:
        home = [r for r in training.rows if r.home_team_id == team]
        away = [r for r in training.rows if r.away_team_id == team]
        scored = sum(r.home_goals_90 for r in home) + sum(r.away_goals_90 for r in away)
        conceded = sum(r.away_goals_90 for r in home) + sum(r.home_goals_90 for r in away)
        exposure = math.fsum((len(home)*hbar, len(away)*abar))
        against = math.fsum((len(home)*abar, len(away)*hbar))
        alpha = (scored + config.kappa) / (exposure + config.kappa)
        beta = (conceded + config.kappa) / (against + config.kappa)
        _check(all(math.isfinite(v) and v > 0 for v in (alpha, beta)),
               ErrorCode.RATE_OUT_OF_RANGE, "Invalid rate-ratio factors")
        factors.append(RateFactors(team, scored, conceded, exposure, against, alpha, beta))
    return FittedRateRatio(config, training, hbar, abar, tuple(factors))

def prediction_identifiability(model, home_team_id: str, away_team_id: str) -> ContrastDiagnostics:
    """Exact per-rate row-span check; graph connectivity alone is insufficient."""
    _check(isinstance(model, (FittedModel, FittedRateRatio)), ErrorCode.INPUT_INVALID, "Invalid fitted model")
    _check(isinstance(home_team_id, str) and isinstance(away_team_id, str)
           and home_team_id != away_team_id, ErrorCode.INPUT_INVALID, "Distinct team IDs required")
    training = model.training
    unknown = tuple(sorted({home_team_id, away_team_id} - set(training.teams)))
    if unknown:
        return ContrastDiagnostics(False, False, False, unknown)
    h, a = _design(training.teams, home_team_id, away_team_id)
    flags = (not any(_reduce(h, training.rank.basis)), not any(_reduce(a, training.rank.basis)))
    component = {t: index for index, group in enumerate(training.rank.components) for t in group}
    return ContrastDiagnostics(*flags, component[home_team_id] != component[away_team_id], ())

def _exp(eta: float, *, prediction: bool = False) -> float:
    upper = math.log(MAX_DISTRIBUTION_RATE) if prediction else 700.0
    _check(math.isfinite(eta) and -700 <= eta <= upper, ErrorCode.RATE_OUT_OF_RANGE,
           "Log rate outside supported arithmetic/prediction range; no clamping")
    value = math.exp(eta)
    _check(math.isfinite(value) and value > 0 and (not prediction or value <= MAX_DISTRIBUTION_RATE),
           ErrorCode.RATE_OUT_OF_RANGE, "Rate must be finite, positive and within limit")
    return value

@dataclass(frozen=True, slots=True)
class TeamParameters:
    team_id: str
    attack: float
    defense: float

@dataclass(frozen=True, slots=True)
class OptimizerDiagnostics:
    iterations: int
    objective: float
    nll: float
    gradient_inf: float
    newton_decrement_squared: float
    minimum_cholesky_pivot: float
    maximum_cholesky_pivot: float
    backtracks: int
    objective_history: tuple[float, ...]
    fitted_home_total: float
    fitted_away_total: float
    attack_sum: float
    defense_sum: float

@dataclass(frozen=True, slots=True)
class FittedModel:
    config: ModelConfig
    training: TrainingData
    mu: float
    home_advantage: float
    parameters: tuple[TeamParameters, ...]
    diagnostics: OptimizerDiagnostics

    @property
    def theta(self) -> tuple[float, ...]:
        return (self.mu, self.home_advantage,
                *(p.attack for p in self.parameters), *(p.defense for p in self.parameters))

@dataclass(frozen=True, slots=True)
class _Evaluation:
    objective: float
    nll: float
    gradient: tuple[float, ...]
    hessian: tuple[tuple[float, ...], ...]
    rates: tuple[float, ...]

def _problem(training: TrainingData):
    designs, goals = [], []
    for row in training.rows:
        designs.extend(_design(training.teams, row.home_team_id, row.away_team_id))
        goals.extend((row.home_goals_90, row.away_goals_90))
    return tuple(designs), tuple(goals)

def _evaluate(theta, designs, goals, tau, *, derivatives=True) -> _Evaluation:
    """Exact stated float64 objective, analytic g/H; no numerical differences."""
    p = len(theta)
    _check(all(math.isfinite(v) for v in theta), ErrorCode.NUMERIC_ERROR, "Nonfinite parameter")
    gradient = [[] for _ in theta]
    hessian = [[[] for _ in theta] for _ in theta]
    terms, rates = [], []
    try:
        for row, y in zip(designs, goals):
            sparse = [(i, z) for i, z in enumerate(row) if z]
            eta = math.fsum(theta[i]*z for i, z in sparse)
            rate = _exp(eta)
            rates.append(rate)
            terms.append(math.fsum((rate, -y*eta, math.lgamma(y+1))))
            if derivatives:
                residual = rate-y
                for i, z in sparse:
                    gradient[i].append(z*residual)
                    for j, w in sparse:
                        hessian[i][j].append(rate*z*w)
        nll = math.fsum(terms)
        objective = math.fsum((nll, .5*tau*math.fsum(v*v for v in theta[2:])))
        if derivatives:
            for i in range(2, p):
                gradient[i].append(tau*theta[i])
                hessian[i][i].append(tau)
            g = tuple(math.fsum(v) for v in gradient)
            h = tuple(tuple(math.fsum(cell) for cell in row) for row in hessian)
        else:
            g, h = (), ()
        _check(all(math.isfinite(v) for v in (objective, nll, *g))
               and all(math.isfinite(v) for row in h for v in row),
               ErrorCode.NUMERIC_ERROR, "Nonfinite objective/derivatives")
        return _Evaluation(objective, nll, g, h, tuple(rates))
    except (OverflowError, ValueError) as error:
        if isinstance(error, ExpectedGoalsError):
            raise
        raise ExpectedGoalsError(ErrorCode.NUMERIC_ERROR, "Objective arithmetic failed") from error

def _cholesky(matrix):
    n = len(matrix)
    lower = [[0.0]*n for _ in range(n)]
    pivots = []
    try:
        for i in range(n):
            for j in range(i+1):
                value = matrix[i][j] - math.fsum(lower[i][k]*lower[j][k] for k in range(j))
                if i == j:
                    _check(math.isfinite(value) and value > 0, ErrorCode.HESSIAN_NOT_PD,
                           "Nonpositive/nonfinite Cholesky pivot")
                    pivots.append(value)
                    lower[i][j] = math.sqrt(value)
                else:
                    lower[i][j] = value/lower[j][j]
                    _check(math.isfinite(lower[i][j]), ErrorCode.HESSIAN_NOT_PD, "Nonfinite factor")
    except (OverflowError, ZeroDivisionError, ValueError) as error:
        raise ExpectedGoalsError(ErrorCode.HESSIAN_NOT_PD, "Factorization arithmetic failed") from error
    return tuple(tuple(row) for row in lower), min(pivots), max(pivots)

def _solve(lower, rhs):
    n = len(rhs)
    forward, result = [0.0]*n, [0.0]*n
    try:
        for i in range(n):
            forward[i] = (rhs[i] - math.fsum(lower[i][j]*forward[j] for j in range(i)))/lower[i][i]
        for i in reversed(range(n)):
            result[i] = (forward[i] - math.fsum(lower[j][i]*result[j] for j in range(i+1, n)))/lower[i][i]
        _check(all(math.isfinite(v) for v in result), ErrorCode.NUMERIC_ERROR, "Nonfinite Newton solve")
    except (OverflowError, ZeroDivisionError, ValueError) as error:
        raise ExpectedGoalsError(ErrorCode.NUMERIC_ERROR, "Newton solve arithmetic failed") from error
    return tuple(result)

def fit_expected_goals(batch: ImportResult, cutoff_utc: datetime, *,
                       config: ModelConfig = ModelConfig()) -> FittedModel:
    """Ridge-Poisson fit, with typed failures rather than partial convergence.

    mu and h are unpenalized; attack/defense ridge coefficient is positive.
    Dense work is bounded by config.max_teams. No convergence guarantee is
    asserted for arbitrary floating-point configurations.
    """
    training = _prepare(batch, cutoff_utc, config)
    n = len(training.teams)
    designs, goals = _problem(training)
    log_h = math.log(training.home_goals/len(training.rows))
    log_a = math.log(training.away_goals/len(training.rows))
    theta = (log_a, log_h-log_a, *(0.0 for _ in range(2*n)))
    scale = max(1, training.home_goals + training.away_goals)
    history, backtracks = [], 0
    for iteration in range(config.max_iterations+1):
        evaluated = _evaluate(theta, designs, goals, config.tau)
        lower, minimum, maximum = _cholesky(evaluated.hessian)
        solve = _solve(lower, evaluated.gradient)
        decrement = math.fsum(g*v for g, v in zip(evaluated.gradient, solve))
        gradient = max(abs(v) for v in evaluated.gradient)
        _check(math.isfinite(decrement) and decrement >= 0, ErrorCode.NUMERIC_ERROR, "Invalid Newton decrement")
        if not history:
            history.append(evaluated.objective)
        if gradient <= config.gradient_tolerance*scale and decrement/2 <= config.decrement_tolerance*scale:
            attack_sum = math.fsum(theta[2:2+n])
            defense_sum = math.fsum(theta[2+n:])
            home_total = math.fsum(evaluated.rates[::2])
            away_total = math.fsum(evaluated.rates[1::2])
            tolerance = 1e-8*scale
            _check(max(abs(attack_sum), abs(defense_sum), abs(home_total-training.home_goals),
                       abs(away_total-training.away_goals)) <= tolerance,
                   ErrorCode.NOT_CONVERGED, "Post-fit gauge/goal-total identities failed")
            diagnostics = OptimizerDiagnostics(
                iteration, evaluated.objective, evaluated.nll, gradient, decrement,
                minimum, maximum, backtracks, tuple(history), home_total, away_total, attack_sum, defense_sum)
            params = tuple(TeamParameters(t, theta[2+i], theta[2+n+i]) for i, t in enumerate(training.teams))
            return FittedModel(config, training, theta[0], theta[1], params, diagnostics)
        _check(iteration < config.max_iterations, ErrorCode.NOT_CONVERGED, "Newton iteration limit reached")
        step, accepted = 1.0, False
        while step >= 2**-40:
            trial = tuple(x-step*v for x, v in zip(theta, solve))
            try:
                value = _evaluate(trial, designs, goals, config.tau, derivatives=False).objective
                accepted = value <= evaluated.objective - 1e-4*step*decrement
            except ExpectedGoalsError as error:
                if error.code not in (ErrorCode.RATE_OUT_OF_RANGE, ErrorCode.NUMERIC_ERROR):
                    raise
                accepted = False
            if accepted:
                theta = trial
                history.append(value)
                break
            step *= .5
            backtracks += 1
        _check(accepted, ErrorCode.NOT_CONVERGED, "Armijo backtracking failed")
    raise ExpectedGoalsError(ErrorCode.NOT_CONVERGED, "Unreachable iteration boundary")

def _identity(value, training: TrainingData, kind: str) -> str:
    _check(isinstance(value, str) and re.fullmatch(
        re.escape(training.namespace) + ":" + kind + r":[a-z][a-z0-9_-]*", value) is not None,
        ErrorCode.INPUT_INVALID, "Target identifier must use the same synthetic namespace")
    return value

def _ratio_rates(model: FittedRateRatio, home: str, away: str):
    factors = {r.team_id: (r.alpha, r.beta) for r in model.factors}
    ha, hb = factors.get(home, (1.0, 1.0))
    aa, ab = factors.get(away, (1.0, 1.0))
    _check(all(math.isfinite(v) and v > 0 for v in
               (model.baseline_home, model.baseline_away, ha, hb, aa, ab)),
           ErrorCode.RATE_OUT_OF_RANGE, "Invalid comparison factors")
    return (_exp(math.fsum((math.log(model.baseline_home), math.log(ha), math.log(ab))), prediction=True),
            _exp(math.fsum((math.log(model.baseline_away), math.log(aa), math.log(hb))), prediction=True))

def _forecast_rate(values) -> float:
    try:
        eta = math.fsum(values)
    except (OverflowError, ValueError):
        raise ExpectedGoalsError(ErrorCode.RATE_OUT_OF_RANGE, "Forecast log-rate arithmetic failed") from None
    return _exp(eta, prediction=True)

def predict_expected_goals(model: FittedModel | FittedRateRatio, *,
                           target_fixture_id: str, home_team_id: str, away_team_id: str,
                           target_kickoff_utc: datetime, cutoff_utc: datetime,
                           allow_unidentified: bool = False,
                           fallback: str | FittedRateRatio | None = None) -> ExpectedGoalsForecast:
    """Forecast synthetic rates, then use forecast.probabilities() for Phase1B.

    Caller-supplied target metadata is never authenticated by historical results.
    Unsupported pairs require explicit allow_unidentified or fallback. A numeric
    failure is never automatically converted to a fallback.
    """
    _check(isinstance(model, (FittedModel, FittedRateRatio)), ErrorCode.INPUT_INVALID, "Invalid fitted model")
    _check(type(allow_unidentified) is bool, ErrorCode.INPUT_INVALID, "allow_unidentified must be bool")
    _check(fallback is None or isinstance(fallback, FittedRateRatio) or
           (isinstance(fallback, str) and fallback == "league"),
           ErrorCode.INPUT_INVALID, "fallback must be None, 'league' or a fitted rate-ratio")
    training = model.training
    cutoff, kickoff = _utc(cutoff_utc, "cutoff_utc"), _utc(target_kickoff_utc, "target_kickoff_utc")
    _check(cutoff < kickoff, ErrorCode.CUTOFF_AFTER_KICKOFF, "Cutoff must strictly precede target kickoff")
    _check(cutoff == training.cutoff_utc, ErrorCode.CUTOFF_MISMATCH, "Prediction cutoff must equal fitting cutoff")
    fixture = _identity(target_fixture_id, training, "fixture")
    home = _identity(home_team_id, training, "team")
    away = _identity(away_team_id, training, "team")
    _check(home != away, ErrorCode.INPUT_INVALID, "Target teams must differ")
    _check(fixture not in {r.fixture_id for r in training.rows},
           ErrorCode.TARGET_IN_TRAINING, "Target fixture is present in training")
    contrasts = prediction_identifiability(model, home, away)
    unsupported = not (contrasts.home_identified and contrasts.away_identified)
    if unsupported and not (allow_unidentified or fallback is not None):
        code = (ErrorCode.NO_HISTORY if contrasts.unknown_teams else ErrorCode.CROSS_COMPONENT
                if contrasts.cross_component else ErrorCode.PREDICTION_NOT_IDENTIFIED)
        raise ExpectedGoalsError(code, "Requested rates are not data identified")
    if isinstance(fallback, FittedRateRatio):
        _check((fallback.training.batch_hash, fallback.training.row_hash, fallback.training.cutoff_utc) ==
               (training.batch_hash, training.row_hash, training.cutoff_utc),
               ErrorCode.INPUT_INVALID, "Fallback must use the same validated batch, rows and cutoff")
    warnings = [*training.warnings, "TARGET_METADATA_UNVERIFIED"]
    if unsupported:
        warnings.append("PRIOR_OR_FALLBACK_DRIVEN")
    if unsupported and fallback == "league":
        values = (training.home_goals/len(training.rows), training.away_goals/len(training.rows))
        h, a = (_exp(math.log(v), prediction=True) for v in values)
        method = "league_fallback"
    elif unsupported and isinstance(fallback, FittedRateRatio):
        h, a = _ratio_rates(fallback, home, away)
        method = "rate_ratio_fallback"
        warnings.append("APPROXIMATE_RATE_RATIO")
    elif isinstance(model, FittedRateRatio):
        h, a = _ratio_rates(model, home, away)
        method = "rate_ratio_approximate"
        warnings.append("APPROXIMATE_RATE_RATIO")
    else:
        params = {p.team_id: (p.attack, p.defense) for p in model.parameters}
        ha, hd = params.get(home, (0.0, 0.0))
        aa, ad = params.get(away, (0.0, 0.0))
        h = _forecast_rate((model.mu, model.home_advantage, ha, -ad))
        a = _forecast_rate((model.mu, aa, -hd))
        method = "ridge_prior" if unsupported else "ridge_poisson"
    for name, value in (("home", h), ("away", a)):
        if not .05 <= value <= 8:
            warnings.append("RATE_PLAUSIBILITY:" + name)
    return ExpectedGoalsForecast(h, a, method, unsupported, contrasts, training.rank.model_identified,
                                 fixture, home, away, kickoff, cutoff, training.row_hash,
                                 training.batch_hash, tuple(warnings))
