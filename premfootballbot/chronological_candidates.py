"""Offline protocol/fold audit only. NO NEW MODEL FITTING OR OUTCOME SCORING.

Source replay proves consistency, never historical availability. No forecasts,
metrics, model search, I/O, randomness or trusted time are implemented here.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, timedelta
import re

from . import completed_epl as data
from . import chronological_epl as chronology

VERSION = "phase4c1-protocol-v1"
STATUS = "RETROSPECTIVE_DATE_LEVEL_SIMULATION_NOT_EX_ANTE_VERIFIED"
EXPOSED = "EXPOSED_HOLDOUT_NOT_CONFIRMATORY"


class ProtocolError(ValueError):
    code = "PROTOCOL_INVALID"


def _need(condition, message):
    if not condition:
        raise ProtocolError(message)


@dataclass(frozen=True, slots=True)
class ProtocolPolicy:
    embargo_days: int = 2
    minimum_history_matches: int = 100
    source_seasons: tuple[int, ...] = (2024, 2025)
    selection_seasons: tuple[int, ...] = (2024,)
    exposed_seasons: tuple[int, ...] = (2025,)
    exposed_label: str = EXPOSED
    candidate_selection: str = "DEVELOPMENT_ONLY_NO_HOLDOUT_SELECTION"
    benchmarks: tuple[str, ...] = ("ABSTAIN_CONTROL", "TRAINING_CLASS_FREQUENCY", "FIXED_RIDGE4_REFERENCE")
    cold_start_categories: tuple[str, ...] = ("ESTABLISHED_HISTORY", "PRIOR_ONLY_RESERVED_NOT_EXECUTED", "NO_PREDICTION")
    paired_policy: str = "COMMON_FIXTURE_IDS_PLUS_ALL_MATCH_DENOMINATORS"
    coverage_segments: tuple[str, ...] = ("ALL_TARGETS", "ESTABLISHED", "PRIOR_ONLY", "ABSTAINED", "FAILURES")
    future_metrics: tuple[str, ...] = ("UNSCALED_MULTICLASS_BRIER", "NATURAL_LOG_LOSS", "CLASSWISE_CALIBRATION")
    future_scoring: str = "LABEL_JOIN_AFTER_FROZEN_FORECASTS_SEPARATE_APPROVAL_REQUIRED"
    uncertainty: str = "PAIRED_DATE_CLUSTER_DESCRIPTIVE_NOT_SIGNIFICANCE"
    uncertainty_seed: int = 4042026
    uncertainty_replicates: int = 4000
    stop_conditions: tuple[str, ...] = ("SOURCE_OR_IDENTITY_FAILURE", "TEMPORAL_LEAKAGE", "EXPOSED_HOLDOUT_SELECTION",
                                       "MISSING_HISTORY_ABSTAIN", "NEW_EXECUTION_REQUIRES_OWNER_APPROVAL")


def _policy(policy):
    _need(type(policy) is ProtocolPolicy, "Typed immutable policy required; no JSON policies")
    _need(type(policy.embargo_days) is int and 2 <= policy.embargo_days <= 366, "Embargo must be2..366 calendar days")
    _need(type(policy.minimum_history_matches) is int and 1 <= policy.minimum_history_matches <= 380,
          "Minimum history must be1..380 matches")
    defaults=ProtocolPolicy()
    for f in fields(defaults):
        if f.name not in ("embargo_days", "minimum_history_matches"):
            _need(type(getattr(policy,f.name)) is type(getattr(defaults,f.name))
                  and getattr(policy,f.name)==getattr(defaults,f.name), "Unapproved policy field: "+f.name)
    return policy


@dataclass(frozen=True, slots=True)
class FixtureReference:
    fixture_id: str
    season_start_year: int
    match_date: date
    home_team_id: str
    away_team_id: str
    source_sha256: str
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False


@dataclass(frozen=True, slots=True)
class TargetAudit:
    fixture: FixtureReference
    category: str
    reason: str


@dataclass(frozen=True, slots=True)
class FoldDefinition:
    target_date: date
    training_date_limit: date
    embargo_days: int
    training: tuple[FixtureReference, ...]
    targets: tuple[TargetAudit, ...]
    training_population: tuple[str, ...]
    exclusions: tuple[tuple[str, int], ...]
    history_status: str
    status: str = STATUS
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False
    sha256: str = ""


@dataclass(frozen=True, slots=True)
class CandidateProtocol:
    policy: ProtocolPolicy
    dataset_sha256: str
    sources: tuple[data.archive.OpenFootballSource, ...]
    alias_version: str
    profile_sha256: str
    folds: tuple[FoldDefinition, ...]
    exposure: tuple[tuple[int, str], ...] = ((2024, "DEVELOPMENT_ONLY"), (2025, EXPOSED))
    version: str = VERSION
    status: str = STATUS
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False
    execution_status: str = "PROTOCOL_ONLY_NOT_EXECUTED"
    warnings: tuple[str, ...] = (
        "NO NEW MODEL FITTING OR OUTCOME SCORING", "NO PROSPECTIVE VALIDITY CLAIM",
        "Archive acquisition/checksum does not establish historical first publication",
        "Embargo is a date-level proxy, not verified information availability",
        "2025-26 already exposed; not a fresh confirmatory or selection set",
        "Coverage/prior-only/abstention policies are placeholders, not new predictions",
    )
    sha256: str = ""


def _seal(value):
    payload=asdict(value)
    payload.pop("sha256")
    return replace(value,sha256=data.archive._hash(payload))


def _restrictions(value):
    _need(value.historical_available_at is None and value.kickoff_utc is None
          and value.strict_point_in_time_eligible is False, "No historical timing certification permitted")


def protocol_json(protocol: CandidateProtocol) -> bytes:
    _need(type(protocol) is CandidateProtocol, "CandidateProtocol required; untrusted JSON is not a protocol")
    _policy(protocol.policy)
    _restrictions(protocol)
    _need(protocol.version==VERSION and protocol.status==STATUS
          and protocol.execution_status=="PROTOCOL_ONLY_NOT_EXECUTED"
          and protocol.exposure==CandidateProtocol.__dataclass_fields__["exposure"].default
          and protocol.warnings==CandidateProtocol.__dataclass_fields__["warnings"].default,
          "Governance/disclaimer altered")
    _need(type(protocol.folds) is tuple and 1<=len(protocol.folds)<=380, "Bounded immutable folds required")
    _need(all(type(f) is FoldDefinition for f in protocol.folds), "Typed folds required")
    _need(type(protocol.sources) is tuple and len(protocol.sources)==2
          and all(type(s) is data.archive.OpenFootballSource for s in protocol.sources), "Typed source manifests required")
    _need(type(protocol.dataset_sha256) is str and re.fullmatch(r"[0-9a-f]{64}",protocol.dataset_sha256),
          "Dataset identity required")
    dates=tuple(f.target_date for f in protocol.folds)
    _need(all(type(d) is date for d in dates) and dates==tuple(sorted(set(dates))), "Duplicate/unordered dates")
    for fold in protocol.folds:
        _need(type(fold) is FoldDefinition and fold==_seal(fold) and fold.status==STATUS, "Fold integrity changed")
        _restrictions(fold)
        _need(fold.embargo_days==protocol.policy.embargo_days
              and fold.training_date_limit==fold.target_date-timedelta(days=fold.embargo_days), "Date limit mismatch")
        _need(type(fold.training) is tuple and type(fold.targets) is tuple and fold.targets, "Immutable nonempty date block required")
        _need(all(type(t) is TargetAudit for t in fold.targets) and type(fold.exclusions) is tuple
              and all(type(item) is tuple and len(item)==2 and type(item[0]) is str
                      and type(item[1]) is int and item[1]>=0 for item in fold.exclusions),
              "Typed immutable audits/exclusions required")
        refs=fold.training+tuple(t.fixture for t in fold.targets)
        _need(all(type(r) is FixtureReference for r in refs), "Typed fixture references required")
        _need(len({r.fixture_id for r in refs})==len(refs), "Duplicate fixture or target in training")
        for r in refs:
            _restrictions(r)
            _need(type(r) is FixtureReference and r.season_start_year==2024 and type(r.match_date) is date,
                  "Development-only date references required")
        _need(all(r.match_date<=fold.training_date_limit for r in fold.training)
              and all(t.fixture.match_date==fold.target_date for t in fold.targets), "Temporal leakage")
        population=tuple(sorted({team for r in fold.training for team in (r.home_team_id,r.away_team_id)}))
        _need(population==fold.training_population, "Population must come only from selected training history")
        sufficient=len(fold.training)>=protocol.policy.minimum_history_matches
        _need(fold.history_status==("SUFFICIENT_HISTORY_NOT_TRAINED" if sufficient else "INSUFFICIENT_HISTORY"),
              "History-status mismatch")
        for audit in fold.targets:
            known=audit.fixture.home_team_id in population and audit.fixture.away_team_id in population
            expected=("ESTABLISHED_HISTORY","HISTORY_ONLY_NO_EXECUTION") if sufficient and known else (
                      "NO_PREDICTION","INSUFFICIENT_HISTORY" if not sufficient else "UNSEEN_TEAM_ABSTAIN_CONTROL")
            _need((audit.category,audit.reason)==expected, "Target audit classification mismatch")
    _need(protocol==_seal(protocol), "Protocol integrity mismatch")
    return data.archive._json(protocol)


def _reference(row):
    r=row.original
    return FixtureReference(r.fixture_id,r.season_start_year,r.match_date,row.home_team_id,row.away_team_id,r.source_sha256)


def _assemble(dataset,base_folds,policy):
    _policy(policy)
    lookup={r.original.fixture_id:r for r in dataset.rows}
    _need(len(lookup)==len(dataset.rows), "Duplicate dataset fixture identity")
    result=[]
    for base in base_folds:
        selected=tuple(_reference(lookup[i]) for i in base.training_ids)
        target=tuple(_reference(lookup[i]) for i in base.target_ids)
        _need(all(r.season_start_year==2024 for r in (*selected,*target)), "Holdout cannot be selected")
        _need({r.fixture_id for r in target}=={r.original.fixture_id for r in dataset.rows
              if r.original.season_start_year==2024 and r.original.match_date==base.target_date}, "Partial date group")
        population=tuple(sorted({team for r in selected for team in (r.home_team_id,r.away_team_id)}))
        sufficient=len(selected)>=policy.minimum_history_matches
        audits=[]
        for t in target:
            known=t.home_team_id in population and t.away_team_id in population
            audits.append(TargetAudit(t,"ESTABLISHED_HISTORY" if sufficient and known else "NO_PREDICTION",
                         "HISTORY_ONLY_NO_EXECUTION" if sufficient and known else
                         "INSUFFICIENT_HISTORY" if not sufficient else "UNSEEN_TEAM_ABSTAIN_CONTROL"))
        excluded=Counter()
        limit=base.target_date-timedelta(days=policy.embargo_days)
        for row in dataset.rows:
            r=row.original
            if r.season_start_year==2025: excluded["EXPOSED_HOLDOUT_RESERVED"]+=1
            elif r.match_date==base.target_date: excluded["TARGET_DATE"]+=1
            elif r.match_date>base.target_date: excluded["FUTURE_DEVELOPMENT"]+=1
            elif r.match_date>limit: excluded["EMBARGO"]+=1
        _need(len(selected)+sum(excluded.values())==len(dataset.rows), "Unaccounted source rows")
        result.append(_seal(FoldDefinition(base.target_date,limit,policy.embargo_days,selected,tuple(audits),
                      population,tuple(sorted(excluded.items())),"SUFFICIENT_HISTORY_NOT_TRAINED" if sufficient else "INSUFFICIENT_HISTORY")))
    protocol=_seal(CandidateProtocol(policy,dataset.sha256,tuple(s.source for s in dataset.seasons),
                                    dataset.alias_version,dataset.profile_sha256,tuple(result)))
    protocol_json(protocol)
    return protocol


def build_protocol(dataset, inputs, *, license_bytes, target_dates: tuple[date, ...], policy=ProtocolPolicy()):
    """Source-backed wrapper of the approved NON-TRAINING development_folds API."""
    _policy(policy)
    _need(type(target_dates) is tuple and 1<=len(target_dates)<=380, "Explicit bounded target-date tuple required")
    # Existing function replays exact completed dataset/license and rejects
    # duplicate/holdout dates and invalid calendar embargo. It never fits/scores.
    folds=chronology.development_folds(dataset,inputs,license_bytes=license_bytes,
                                      target_dates=target_dates,embargo_days=policy.embargo_days)
    return _assemble(dataset,folds,policy)


def verify_protocol(protocol,dataset,inputs,*,license_bytes):
    original=protocol_json(protocol)
    replay=build_protocol(dataset,inputs,license_bytes=license_bytes,
                          target_dates=tuple(f.target_date for f in protocol.folds),policy=protocol.policy)
    _need(original==protocol_json(replay), "Source-backed protocol replay mismatch")
    return True
