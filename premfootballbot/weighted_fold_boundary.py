"""B2A source-backed, read-only EPL development-fold manifest; NO FITTING.

A source-verified training-only evidence boundary, NOT a converter to the B1
invented numerical kernel. Dates are retrospective proxies, never proven
historic kickoff or pre-match availability. No predictions, scores, weights,
model selection, file/network access or executable training path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
import re

from . import chronological_candidates as cp
from . import completed_epl as data

VERSION = "phase4c2b2a-readonly-training-boundary-v1"
STATUS = cp.STATUS
WARNINGS = (
    "READ_ONLY_TRAINING_IDENTITY_AND_AGE_MANIFEST_NO_FITTING_OR_SCORING",
    "NO REAL DATA ADAPTER TO INVENTED WEIGHTED POISSON KERNEL",
    "2025-26 EXPOSED_HOLDOUT_NOT_CONFIRMATORY_NO_SELECTION",
    "Date-level embargo is NOT verified pre-kickoff information availability",
    "Raw archive acquisition date does NOT certify historical first publication",
)
EXPOSURE = ((2024, "DEVELOPMENT_ONLY"), (2025, cp.EXPOSED))


class TrainingBoundaryError(ValueError):
    code = "B2A_BOUNDARY_INVALID"


def _need(condition, message):
    if not condition:
        raise TrainingBoundaryError(message)


def _digest(value):
    _need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "SHA256 digest required")


def _seal(value):
    payload = asdict(value)
    payload.pop("sha256")
    return replace(value, sha256=data.archive._hash(payload))


def _policy(policy):
    cp._policy(policy)
    _need(policy.minimum_history_matches >= 100 and policy.embargo_days >= 2,
          "B2A requires minimum history >=100 and calendar embargo >=2")


def _restricted(value):
    _need((not hasattr(value, "status") or value.status == STATUS)
          and value.historical_available_at is None
          and value.kickoff_utc is None and value.strict_point_in_time_eligible is False,
          "Cannot elevate retrospective timing eligibility")


@dataclass(frozen=True, slots=True)
class TrainingObservation:
    """Only authenticated training FT90 labels; no target result fields."""
    fixture: cp.FixtureReference
    home_goals_ft90: int
    away_goals_ft90: int
    age_days: int


@dataclass(frozen=True, slots=True)
class TrainingFold:
    target_date: date
    training_date_limit: date
    protocol_fold_sha256: str
    training: tuple[TrainingObservation, ...]
    targets: tuple[cp.TargetAudit, ...]  # ID, category, reason: NEVER results.
    training_population: tuple[str, ...]
    history_status: str
    training_ids_sha256: str
    training_rows_sha256: str
    status: str = STATUS
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False
    real_fitting_authorized: bool = False
    sha256: str = ""


@dataclass(frozen=True, slots=True)
class TrainingBoundary:
    policy: cp.ProtocolPolicy
    protocol_sha256: str
    dataset_sha256: str
    sources: tuple[data.archive.OpenFootballSource, ...]
    alias_version: str
    profile_sha256: str
    source_fingerprint: str
    folds: tuple[TrainingFold, ...]
    target_count: int
    exposure: tuple[tuple[int, str], ...] = EXPOSURE
    version: str = VERSION
    warnings: tuple[str, ...] = WARNINGS
    status: str = STATUS
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False
    real_fitting_authorized: bool = False
    scoring_authorized: bool = False
    candidate_selection_authorized: bool = False
    sha256: str = ""


def _fingerprint(value):
    return data.archive._hash((value.dataset_sha256, value.sources, value.alias_version, value.profile_sha256))


def _observation(ref, row, fold):
    """Private pure identity oracle; public access MUST replay the pinned source."""
    original = row.original
    actual = cp.FixtureReference(original.fixture_id, original.season_start_year,
                                 original.match_date, row.home_team_id, row.away_team_id,
                                 original.source_sha256)
    _need(type(ref) is cp.FixtureReference and ref == actual
          and ref.season_start_year == 2024 and type(ref.match_date) is date
          and ref.match_date <= fold.training_date_limit,
          "Source/team/season/date/cutoff identity mismatch")
    age = (fold.target_date - ref.match_date).days
    _need(type(age) is int and 2 <= age <= 1000000
          and age >= fold.embargo_days, "Invalid training age or embargo")
    home, away = original.home_goals_ft90, original.away_goals_ft90
    _need(type(home) is int and type(away) is int
          and 0 <= home <= 100 and 0 <= away <= 100,
          "Invalid training FT90 labels")
    return TrainingObservation(ref, home, away, age)


def _assemble(protocol, rows):
    """Private, untrusted oracle. Reads result labels for SELECTED training IDs only."""
    _policy(protocol.policy)
    lookup = {row.original.fixture_id: row for row in rows}
    _need(len(lookup) == len(rows), "Duplicate source fixture identity")
    folds, target_count = [], 0
    for fold in protocol.folds:
        _need(type(fold) is cp.FoldDefinition, "Typed C1 fold required")
        _need(fold.training_date_limit == fold.target_date - timedelta(days=protocol.policy.embargo_days)
              and fold.embargo_days == protocol.policy.embargo_days,
              "Training cutoff changed")
        refs = fold.training
        _need(len({r.fixture_id for r in refs}) == len(refs)
              and all(ref.fixture_id in lookup for ref in refs), "Missing/duplicate training fixture")
        training = tuple(_observation(ref, lookup[ref.fixture_id], fold) for ref in refs)
        ids = tuple(r.fixture.fixture_id for r in training)
        targets = fold.targets
        _need(type(targets) is tuple and targets, "Whole target-date group required")
        _need(all(type(t) is cp.TargetAudit and type(t.fixture) is cp.FixtureReference
                  and t.fixture.season_start_year == 2024 and t.fixture.match_date == fold.target_date
                  for t in targets), "Development-only target IDs required")
        _need(set(ids).isdisjoint({t.fixture.fixture_id for t in targets}),
              "Target leaked into training")
        populations = tuple(sorted({team for t in training for team in
                                   (t.fixture.home_team_id, t.fixture.away_team_id)}))
        _need(fold.training_population == populations,
              "Training team population mismatch")
        sufficient = len(training) >= protocol.policy.minimum_history_matches
        _need(fold.history_status == ("SUFFICIENT_HISTORY_NOT_TRAINED" if sufficient
                                      else "INSUFFICIENT_HISTORY"),
              "History threshold changed")
        result = _seal(TrainingFold(fold.target_date, fold.training_date_limit, fold.sha256,
            training, targets, populations, fold.history_status,
            data.archive._hash(ids),
            data.archive._hash(tuple((r.fixture, r.home_goals_ft90, r.away_goals_ft90,
                                     r.age_days) for r in training))))
        folds.append(result)
        target_count += len(targets)
    return _seal(TrainingBoundary(protocol.policy, protocol.sha256, protocol.dataset_sha256,
        protocol.sources, protocol.alias_version, protocol.profile_sha256,
        _fingerprint(protocol), tuple(folds), target_count))


def boundary_json(boundary: TrainingBoundary) -> bytes:
    """Structural checks only. Hashes aren't signatures; source replay is mandatory."""
    _need(type(boundary) is TrainingBoundary, "Typed training boundary required")
    _policy(boundary.policy)
    _restricted(boundary)
    _need(boundary.version == VERSION and boundary.warnings == WARNINGS
          and boundary.exposure == EXPOSURE and boundary.real_fitting_authorized is False
          and boundary.scoring_authorized is False and boundary.candidate_selection_authorized is False,
          "Model/holdout authorization flags changed")
    _need(type(boundary.sources) is tuple and len(boundary.sources) == 2
          and all(type(s) is data.archive.OpenFootballSource for s in boundary.sources),
          "Typed source manifests required")
    for digest in (boundary.protocol_sha256, boundary.dataset_sha256,
                   boundary.profile_sha256, boundary.source_fingerprint):
        _digest(digest)
    _need(boundary.source_fingerprint == _fingerprint(boundary), "Source fingerprint changed")
    _need(type(boundary.folds) is tuple and 1 <= len(boundary.folds) <= 380
          and all(type(f) is TrainingFold for f in boundary.folds),
          "Immutable nonempty folds required")
    dates = tuple(f.target_date for f in boundary.folds)
    _need(all(type(d) is date for d in dates) and dates == tuple(sorted(set(dates))),
          "Invalid target-date order")
    target_ids, count = set(), 0
    for fold in boundary.folds:
        _restricted(fold)
        _need(fold.real_fitting_authorized is False and fold == _seal(fold),
              "Fold authorization or seal changed")
        _digest(fold.protocol_fold_sha256)
        _digest(fold.training_ids_sha256)
        _digest(fold.training_rows_sha256)
        _need(type(fold.target_date) is date and type(fold.training_date_limit) is date
              and fold.training_date_limit == fold.target_date - timedelta(days=boundary.policy.embargo_days),
              "Calendar cutoff or embargo changed")
        _need(type(fold.training) is tuple and len(fold.training) <= 380
              and all(type(x) is TrainingObservation for x in fold.training),
              "Training-only immutable observations required")
        _need(type(fold.targets) is tuple and bool(fold.targets)
              and all(type(t) is cp.TargetAudit for t in fold.targets),
              "Nonempty immutable target audit group required")
        ids = tuple(r.fixture.fixture_id for r in fold.training)
        _need(len(set(ids)) == len(ids), "Duplicate training IDs")
        for r in fold.training:
            f = r.fixture
            _need(type(f) is cp.FixtureReference and f.season_start_year == 2024
                  and type(f.match_date) is date and f.match_date <= fold.training_date_limit
                  and type(r.home_goals_ft90) is int and type(r.away_goals_ft90) is int
                  and 0 <= r.home_goals_ft90 <= 100 and 0 <= r.away_goals_ft90 <= 100
                  and type(r.age_days) is int
                  and r.age_days == (fold.target_date-f.match_date).days
                  and r.age_days >= boundary.policy.embargo_days,
                  "Training identity/goals/age/date invalid")
            _restricted(f)
        populations = tuple(sorted({t for r in fold.training for t in
                                    (r.fixture.home_team_id, r.fixture.away_team_id)}))
        _need(fold.training_population == populations, "Training population mismatch")
        enough = len(fold.training) >= boundary.policy.minimum_history_matches
        _need(fold.history_status == ("SUFFICIENT_HISTORY_NOT_TRAINED" if enough
                                      else "INSUFFICIENT_HISTORY"), "History status mismatch")
        _need(fold.training_ids_sha256 == data.archive._hash(ids)
              and fold.training_rows_sha256 == data.archive._hash(tuple(
                  (r.fixture, r.home_goals_ft90, r.away_goals_ft90, r.age_days)
                  for r in fold.training)), "Training support digest mismatch")
        for audit in fold.targets:
            ref = audit.fixture
            _need(type(ref) is cp.FixtureReference and ref.season_start_year == 2024
                  and type(ref.match_date) is date and ref.match_date == fold.target_date
                  and ref.fixture_id not in ids and ref.fixture_id not in target_ids,
                  "Target/date/duplicate leakage")
            _restricted(ref)
            known = ref.home_team_id in populations and ref.away_team_id in populations
            expected = ("ESTABLISHED_HISTORY", "HISTORY_ONLY_NO_EXECUTION") if enough and known else (
                "NO_PREDICTION", "INSUFFICIENT_HISTORY" if not enough else "UNSEEN_TEAM_ABSTAIN_CONTROL")
            _need((audit.category, audit.reason) == expected,
                  "Target category changed")
            target_ids.add(ref.fixture_id)
        count += len(fold.targets)
    _need(type(boundary.target_count) is int and boundary.target_count == count
          and count <= 380, "Target coverage mismatch")
    _need(boundary == _seal(boundary), "Training-boundary seal mismatch")
    return data.archive._json(boundary)


def build_training_boundary(protocol: cp.CandidateProtocol,
                            dataset: data.ExploratoryMultiSeasonDataset,
                            inputs: tuple[data.SeasonInput, ...], *, license_bytes: bytes) -> TrainingBoundary:
    """Public entry point: source and C1 replay BEFORE any training-label join."""
    _need(type(protocol) is cp.CandidateProtocol, "Typed C1 protocol required")
    _policy(protocol.policy)
    cp.verify_protocol(protocol, dataset, inputs, license_bytes=license_bytes)
    result = _assemble(protocol, dataset.rows)
    boundary_json(result)
    return result


def verify_training_boundary(boundary: TrainingBoundary, protocol: cp.CandidateProtocol,
                             dataset: data.ExploratoryMultiSeasonDataset,
                             inputs: tuple[data.SeasonInput, ...], *, license_bytes: bytes) -> bool:
    """Recompute from pinned raw source. Never trust an internally re-sealed blob."""
    encoded = boundary_json(boundary)
    expected = build_training_boundary(protocol, dataset, inputs, license_bytes=license_bytes)
    _need(encoded == boundary_json(expected), "Source-backed training-boundary replay mismatch")
    return True
