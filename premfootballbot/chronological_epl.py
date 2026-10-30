"""Fixed offline retrospective experiment; not a live prediction or tuning API."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
import hashlib
import math
import random
import sys

from . import completed_epl as data
from . import real_epl_training as numeric
from .poisson import poisson_distribution

VERSION = "phase4b-fixed-holdout-v1"
STATUS = "RETROSPECTIVE_DATE_LEVEL_SIMULATION_NOT_EX_ANTE_VERIFIED"
TAIL = 1e-10
BOOTSTRAP_SEED = 4042026
BOOTSTRAP_REPLICATES = 4000


class ChronologicalError(ValueError):
    pass


def _need(condition, message):
    if not condition:
        raise ChronologicalError(message)


def _hash(value):
    return hashlib.sha256(data.archive._json(value)).hexdigest()


def _seal(value):
    fields = asdict(value)
    fields.pop("sha256")
    return replace(value,sha256=_hash(fields))


def artifact_json(value):
    _need(type(value) in (DevelopmentModel, HoldoutForecasts, HoldoutEvaluation), "Unknown artifact")
    _need(value == _seal(value), "Artifact integrity mismatch")
    _need(value.status == STATUS and value.kickoff_utc is None and value.historical_available_at is None
          and value.strict_point_in_time_eligible is False and value.version == VERSION,
          "Simulation restrictions changed")
    return data.archive._json(value)


def _validated(dataset, inputs, license_bytes):
    data.verify_completed_dataset(dataset,inputs,license_bytes=license_bytes)
    return dataset


def _date_groups(rows):
    grouped=defaultdict(list)
    for row in rows:
        grouped[row.match_date].append(row.fixture_id)
    return tuple((d,tuple(ids)) for d,ids in sorted(grouped.items()))


@dataclass(frozen=True, slots=True)
class DateFold:
    target_date: date
    embargo_days: int
    training_ids: tuple[str, ...]
    target_ids: tuple[str, ...]
    status: str = STATUS
    strict_point_in_time_eligible: bool = False


def _folds(rows, target_dates, embargo_days):
    _need(type(target_dates) is tuple and all(type(d) is date for d in target_dates)
          and len(target_dates) == len(set(target_dates)), "Unique calendar dates required, not timestamps")
    _need(type(embargo_days) is int and 2 <= embargo_days <= 366, "Calendar embargo must be2..366")
    development = tuple(r for r in rows if r.original.season_start_year == 2024)
    valid_dates = {r.original.match_date for r in development}
    _need(set(target_dates) <= valid_dates, "Only development match dates allowed; holdout reserved")
    return tuple(DateFold(d,embargo_days,
                 tuple(r.original.fixture_id for r in development if r.original.match_date <= d-timedelta(days=embargo_days)),
                 tuple(r.original.fixture_id for r in development if r.original.match_date == d))
                 for d in sorted(target_dates))


def development_folds(dataset, inputs, *, license_bytes, target_dates: tuple[date, ...], embargo_days=2):
    """Partition only2024 date groups; no fitting/search or holdout selection."""
    _validated(dataset,inputs,license_bytes)
    return _folds(dataset.rows,target_dates,embargo_days)


@dataclass(frozen=True, slots=True)
class KernelRow:
    """Explicit numeric adapter: *_raw slots hold CANONICAL IDs, not raw aliases.

    Only the pure numerical kernel consumes this type. Original real source rows
    stay in the audit; no synthetic or 2023-pinned import object is constructed.
    """
    fixture_id: str
    match_date: date
    home_team_raw: str
    away_team_raw: str
    home_goals_ft90: int
    away_goals_ft90: int


@dataclass(frozen=True, slots=True)
class DevelopmentModel:
    training_rows: tuple[KernelRow, ...]
    training_source: data.archive.OpenFootballSource
    training_row_sha256: str
    config: numeric.RealFitConfig
    intercept: float
    home_advantage: float
    teams: tuple[numeric.TeamEffect, ...]
    diagnostics: numeric.FitDiagnostics
    frequency_counts: tuple[int, int, int]
    frequency_baseline: tuple[float, float, float]
    runtime: str
    training_date_groups: tuple[tuple[date, tuple[str, ...]], ...]
    status: str = STATUS
    version: str = VERSION
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False
    sha256: str = ""


def _development(dataset):
    return tuple(KernelRow(r.original.fixture_id,r.original.match_date,r.home_team_id,r.away_team_id,
                          r.original.home_goals_ft90,r.original.away_goals_ft90)
                 for r in dataset.rows if r.original.season_start_year == 2024)


def _outcome(h,a):
    return 0 if h>a else 1 if h==a else 2


def _fit(dataset):
    rows = _development(dataset)
    _need(len(rows) == 380, "Exact development season required")
    config = numeric.RealFitConfig()  # Fixed4.0, never selected from holdout.
    mu,h,effects,diagnostics = numeric._fit_rows(rows,config)
    _need(diagnostics.gradient_inf_norm <= config.gradient_tolerance, "Optimizer not converged")
    _need(all(math.isfinite(x) and abs(x)<20 for x in (mu,h,*(t.attack for t in effects),
                                                           *(t.defense_vulnerability for t in effects))),
          "Implausible/nonfinite coefficients")
    counts = Counter(_outcome(r.home_goals_ft90,r.away_goals_ft90) for r in rows)
    frequencies = tuple(counts[i]/len(rows) for i in range(3))
    _need(all(x>0 for x in frequencies), "Training-only frequency baseline has a zero class")
    source = next(s.source for s in dataset.seasons if s.season_start_year == 2024)
    return _seal(DevelopmentModel(rows,source,_hash(rows),config,mu,h,effects,diagnostics,
                 tuple(counts[i] for i in range(3)),frequencies,
                 f"{sys.implementation.name} {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                 _date_groups(rows)))


def fit_development(dataset, inputs, *, license_bytes):
    """Fit only2024 after source replay. This API has no selectable hyperparameters."""
    _validated(dataset,inputs,license_bytes)
    return _fit(dataset)


@dataclass(frozen=True, slots=True)
class HoldoutRow:
    fixture_id: str
    match_date: date
    home_team_id: str
    away_team_id: str
    decision: str
    reason: str
    probabilities: tuple[float, ...]
    raw_probabilities: tuple[float, ...]
    baseline: tuple[float, ...]
    rates: tuple[float, ...]
    mass: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class HoldoutForecasts:
    model_sha256: str
    source_dataset_sha256: str
    rows: tuple[HoldoutRow, ...]
    date_groups: tuple[tuple[date, tuple[str, ...]], ...]
    policy: str = "FIXED2024_TRAIN2025_HOLDOUT_NO_REFIT_CONDITIONAL_RETAINED_MASS"
    status: str = STATUS
    version: str = VERSION
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False
    sha256: str = ""


def _forecast(model,dataset):
    teams = {t.team:t for t in model.teams}
    rows=[]
    for target in dataset.rows:
        if target.original.season_start_year != 2025:
            continue
        # Identity/date only: holdout goal labels are never read in this stage.
        identity=(target.original.fixture_id,target.original.match_date,target.home_team_id,target.away_team_id)
        if target.home_team_id not in teams or target.away_team_id not in teams:
            rows.append(HoldoutRow(*identity,"ABSTAIN","UNSEEN_PROMOTED_TEAM",(),(),(),(),()))
            continue
        h,a=teams[target.home_team_id],teams[target.away_team_id]
        rates=(math.exp(model.intercept+model.home_advantage+h.attack+a.defense_vulnerability),
               math.exp(model.intercept+a.attack+h.defense_vulnerability))
        _need(all(math.isfinite(v) and 0<v<=100 for v in rates), "Invalid goal rates")
        p=poisson_distribution(*rates,tolerance=TAIL,max_goals=512).one_x_two()
        raw=(p.home_win,p.draw,p.away_win)
        m=p.mass
        _need(all(math.isfinite(v) for v in (*raw,*asdict(m).values())) and all(v>=0 for v in raw)
              and 0 <= m.omitted_mass <= m.omitted_mass_bound <= TAIL
              and abs(m.mass_roundoff)<=5e-12 and abs(math.fsum(raw)-m.retained_mass)<=5e-12
              and abs(m.retained_mass+m.omitted_mass-1)<=5e-12, "Invalid probability/tail mass")
        total=math.fsum(raw)
        _need(total>0, "No retained probability")
        probs=tuple(v/total for v in raw)
        rows.append(HoldoutRow(*identity,"FORECAST","KNOWN_TRAINING_TEAMS",probs,raw,
                                model.frequency_baseline,rates,tuple(asdict(m).items())))
    _need(len(rows)==380, "Exact holdout required")
    return _seal(HoldoutForecasts(model.sha256,dataset.sha256,tuple(rows),_date_groups(rows)))


def forecast_holdout(model,dataset,inputs,*,license_bytes):
    _validated(dataset,inputs,license_bytes)
    artifact_json(model)
    _need(model==_fit(dataset), "Model differs from exact development replay")
    return _forecast(model,dataset)


def _scores(probabilities,actual):
    _need(len(probabilities)==3 and all(math.isfinite(v) and 0<=v<=1 for v in probabilities)
          and abs(math.fsum(probabilities)-1)<5e-12 and type(actual) is int and 0<=actual<3,
          "Invalid categorical scoring input")
    _need(probabilities[actual]>0, "Zero actual probability: infinite log loss; no clipping")
    return (math.fsum((p-int(i==actual))**2 for i,p in enumerate(probabilities)),
            -math.log(probabilities[actual]))


@dataclass(frozen=True, slots=True)
class ScoredRow:
    fixture_id: str
    match_date: date
    actual: int
    brier: float
    log_loss: float
    baseline_brier: float
    baseline_log_loss: float


@dataclass(frozen=True, slots=True)
class HoldoutEvaluation:
    forecasts_sha256: str
    dataset_sha256: str
    scored_rows: tuple[ScoredRow, ...]
    holdout_total: int
    scored: int
    abstentions: tuple[tuple[str, int], ...]
    coverage: float
    means: tuple[tuple[str, float], ...]
    date_clusters: int
    paired_descriptive_95_intervals: tuple[tuple[str, tuple[float, float]], ...]
    bootstrap_seed: int
    bootstrap_replicates: int
    calibration: tuple[tuple[int, int, int, float, float], ...]
    maximum_omitted_bound: float
    warnings: tuple[str, ...] = (
        "One retrospective season holdout, not historical ex-ante evidence",
        "Selected coverage excludes unseen promoted teams; not full-league accuracy",
        "Posthoc date-cluster bootstrap is descriptive, not preregistered significance",
        "Holdout already inspected in research; future choices need a fresh evaluation window",
        "No current-season, betting value, profitability or calibrated-validity claim",
    )
    status: str = STATUS
    version: str = VERSION
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False
    sha256: str = ""


def _bootstrap(rows):
    groups=defaultdict(list)
    for r in rows:
        groups[r.match_date].append((r.baseline_brier-r.brier,r.baseline_log_loss-r.log_loss))
    values=[groups[k] for k in sorted(groups)]
    _need(bool(values), "No scored dates for uncertainty")
    rng=random.Random(BOOTSTRAP_SEED)
    samples=[[],[]]
    for _ in range(BOOTSTRAP_REPLICATES):
        picked=[values[rng.randrange(len(values))] for _ in values]
        n=sum(len(g) for g in picked)
        for j in (0,1):
            samples[j].append(math.fsum(v[j] for g in picked for v in g)/n)
    def quantile(sorted_values,p):
        position=(len(sorted_values)-1)*p
        i=int(position); f=position-i
        return sorted_values[i]*(1-f)+sorted_values[min(i+1,len(sorted_values)-1)]*f
    return len(values),tuple((name,(quantile(sorted(v),.025),quantile(sorted(v),.975)))
                            for name,v in zip(("baseline_minus_model_brier","baseline_minus_model_log_loss"),samples))


def _evaluate(snapshot,dataset):
    labels={r.original.fixture_id:_outcome(r.original.home_goals_ft90,r.original.away_goals_ft90)
            for r in dataset.rows if r.original.season_start_year==2025}
    scored=[]; abstain=Counter(); bins=defaultdict(list); max_bound=0.0
    for row in snapshot.rows:
        if row.decision=="ABSTAIN":
            abstain[row.reason]+=1; continue
        actual=labels[row.fixture_id]
        b,l=_scores(row.probabilities,actual)
        bb,bl=_scores(row.baseline,actual)
        scored.append(ScoredRow(row.fixture_id,row.match_date,actual,b,l,bb,bl))
        max_bound=max(max_bound,dict(row.mass)["omitted_mass_bound"])
        for k,p in enumerate(row.probabilities):
            bins[(k,min(9,int(p*10)))].append((p,int(k==actual)))
    n=len(scored)
    _need(n>0 and n+sum(abstain.values())==len(snapshot.rows), "Coverage mismatch or no scores")
    means=tuple((name,math.fsum(getattr(r,name) for r in scored)/n)
                for name in ("brier","log_loss","baseline_brier","baseline_log_loss"))
    clusters,intervals=_bootstrap(scored)
    calibration=tuple((k,b,len(v),math.fsum(x[0] for x in v)/len(v),math.fsum(x[1] for x in v)/len(v))
                      for (k,b),v in sorted(bins.items()))
    return _seal(HoldoutEvaluation(snapshot.sha256,dataset.sha256,tuple(scored),len(snapshot.rows),n,
                 tuple(sorted(abstain.items())),n/len(snapshot.rows),means,clusters,intervals,
                 BOOTSTRAP_SEED,BOOTSTRAP_REPLICATES,calibration,max_bound))


def evaluate_holdout(model,snapshot,dataset,inputs,*,license_bytes):
    expected=forecast_holdout(model,dataset,inputs,license_bytes=license_bytes)
    artifact_json(snapshot)
    _need(snapshot==expected, "Forecast snapshot differs from label-free replay")
    return _evaluate(snapshot,dataset)


def verify_evaluation(evaluation,model,snapshot,dataset,inputs,*,license_bytes):
    original=artifact_json(evaluation)
    replay=evaluate_holdout(model,snapshot,dataset,inputs,license_bytes=license_bytes)
    _need(original==artifact_json(replay), "Evaluation replay mismatch")
    return True
