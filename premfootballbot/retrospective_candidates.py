"""Offline training-frequency cold start only; no fitting or outcome scoring.

Public construction/replay requires the pinned archive and C1 protocol. Private
helpers support invented unit-test oracles, never source authorization. Seals
are consistency checks, not signatures or historical availability evidence.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
import math
import re

from . import chronological_candidates as cp
from . import completed_epl as data

VERSION = "phase4c2a-prior-only-v1"
STATUS = cp.STATUS
CATEGORIES = ("ESTABLISHED_HISTORY", "PRIOR_ONLY", "ABSTAIN")
WARNINGS = (
    "NO NEW MODEL FITTING OR OUTCOME SCORING; NO PROSPECTIVE VALIDITY CLAIM",
    "Unconditional training-only H/D/A frequencies; no team-strength inference or smoothing",
    "Established teams remain unfitted and unevaluated",
    "Archive acquisition and calendar embargo do not prove historical availability",
    "2025-26 EXPOSED_HOLDOUT_NOT_CONFIRMATORY; no holdout targets or selection",
)


class ColdStartError(ValueError):
    code = "COLD_START_INVALID"


def _need(condition, message):
    if not condition:
        raise ColdStartError(message)


def _seal(value):
    payload = asdict(value)
    payload.pop("sha256")
    return replace(value, sha256=data.archive._hash(payload))


def _restrictions(value):
    _need(value.status == STATUS and value.historical_available_at is None
          and value.kickoff_utc is None and value.strict_point_in_time_eligible is False,
          "Retrospective restrictions changed")


def _digest(value):
    _need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "SHA256 required")


def _history(counts, minimum):
    _need(type(counts) is tuple and len(counts) == 3
          and all(type(n) is int and 0 <= n <= 380 for n in counts), "Integer H/D/A counts required")
    _need(type(minimum) is int and 1 <= minimum <= 380, "Invalid minimum history")
    n = sum(counts)
    _need(n <= 380, "Impossible training denominator")
    return n


def _decision(counts, minimum, population, home, away):
    """Pure conditional oracle. No season, source, labels or model inference."""
    n = _history(counts, minimum)
    _need(type(population) is tuple and all(type(t) is str and t for t in population)
          and population == tuple(sorted(set(population))), "Unique training population required")
    _need(type(home) is str and type(away) is str and home and away and home != away,
          "Distinct target identities required")
    if n < minimum:
        return "ABSTAIN", "INSUFFICIENT_HISTORY", ()
    if 0 in counts:
        return "ABSTAIN", "ZERO_TRAINING_CLASS", ()
    if home in population and away in population:
        return "ESTABLISHED_HISTORY", "ESTABLISHED_NOT_EVALUATED", ()
    probabilities = tuple(c / n for c in counts)
    _need(all(math.isfinite(p) and 0 < p <= 1 for p in probabilities)
          and abs(math.fsum(probabilities) - 1) <= 1e-15, "Invalid empirical probabilities")
    return "PRIOR_ONLY", "TEAM_STRENGTH_UNIDENTIFIED", probabilities


@dataclass(frozen=True, slots=True)
class ColdStartForecast:
    fixture: cp.FixtureReference
    fold_sha256: str
    protocol_sha256: str
    source_fingerprint: str
    category: str
    reason: str
    probabilities: tuple[float, ...]
    training_counts: tuple[int, int, int]
    training_matches: int
    training_ids_sha256: str
    training_rows_sha256: str
    status: str = STATUS
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False


@dataclass(frozen=True, slots=True)
class ColdStartFold:
    target_date: date
    training_date_limit: date
    fold_sha256: str
    training_ids: tuple[str, ...]
    training_population: tuple[str, ...]
    training_counts: tuple[int, int, int]
    training_ids_sha256: str
    training_rows_sha256: str
    forecasts: tuple[ColdStartForecast, ...]
    status: str = STATUS
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False
    sha256: str = ""


@dataclass(frozen=True, slots=True)
class ColdStartArtifact:
    policy: cp.ProtocolPolicy
    protocol_sha256: str
    dataset_sha256: str
    sources: tuple[data.archive.OpenFootballSource, ...]
    alias_version: str
    profile_sha256: str
    source_fingerprint: str
    folds: tuple[ColdStartFold, ...]
    category_counts: tuple[tuple[str, int], ...]
    all_targets: int
    exposure: tuple[tuple[int, str], ...] = ((2024, "DEVELOPMENT_ONLY"), (2025, cp.EXPOSED))
    version: str = VERSION
    warnings: tuple[str, ...] = WARNINGS
    status: str = STATUS
    historical_available_at: None = None
    kickoff_utc: None = None
    strict_point_in_time_eligible: bool = False
    sha256: str = ""


def _fingerprint(value):
    return data.archive._hash((value.dataset_sha256, value.sources, value.alias_version, value.profile_sha256))


def _training_summary(fold, rows):
    """Rejoin ONLY selected training identities before reading any result label.

    FT90 eligibility is enforced by the unchanged source parser/replay. Identity,
    ordered canonical teams, source, season and cutoff are also checked here.
    """
    lookup = {row.original.fixture_id: row for row in rows}
    _need(len(lookup) == len(rows), "Duplicate dataset identity")
    ids = tuple(r.fixture_id for r in fold.training)
    _need(len(set(ids)) == len(ids), "Duplicate training identity")
    counts = [0, 0, 0]
    supporting = []
    for ref in fold.training:
        _need(ref.fixture_id in lookup, "Missing training identity")
        row = lookup[ref.fixture_id]
        r = row.original
        actual = cp.FixtureReference(r.fixture_id, r.season_start_year, r.match_date,
                                    row.home_team_id, row.away_team_id, r.source_sha256)
        _need(actual == ref and ref.season_start_year == 2024
              and type(ref.match_date) is date and ref.match_date <= fold.training_date_limit,
              "Training identity/source/date mismatch")
        h, a = r.home_goals_ft90, r.away_goals_ft90
        _need(type(h) is int and type(a) is int and 0 <= h <= 100 and 0 <= a <= 100,
              "Invalid training FT90 result")
        counts[0 if h > a else 1 if h == a else 2] += 1
        supporting.append((ref, h, a))
    counts = tuple(counts)
    _need(_history(counts, 1) == len(ids), "Training denominator mismatch")
    return counts, data.archive._hash(ids), data.archive._hash(tuple(supporting))


def _assemble(protocol, rows):
    """Private pure assembly oracle; public callers MUST use source-backed build."""
    groups, totals = [], Counter()
    fingerprint = _fingerprint(protocol)
    for fold in protocol.folds:
        counts, ids_hash, rows_hash = _training_summary(fold, rows)
        forecasts = []
        for audit in fold.targets:
            ref = audit.fixture
            category, reason, probabilities = _decision(counts, protocol.policy.minimum_history_matches,
                fold.training_population, ref.home_team_id, ref.away_team_id)
            forecasts.append(ColdStartForecast(ref, fold.sha256, protocol.sha256, fingerprint,
                category, reason, probabilities, counts, len(fold.training), ids_hash, rows_hash))
            totals[category] += 1
        groups.append(_seal(ColdStartFold(fold.target_date, fold.training_date_limit, fold.sha256,
            tuple(r.fixture_id for r in fold.training), fold.training_population, counts, ids_hash,
            rows_hash, tuple(forecasts))))
    return _seal(ColdStartArtifact(protocol.policy, protocol.sha256, protocol.dataset_sha256, protocol.sources,
        protocol.alias_version, protocol.profile_sha256, fingerprint, tuple(groups),
        tuple((k, totals[k]) for k in CATEGORIES), sum(totals.values())))


def _policy(policy):
    # Preserve C1 governance; do not lower its default history gate to create
    # real unseen-team examples. Stricter predeclared controls remain possible.
    cp._policy(policy)
    _need(policy.minimum_history_matches >= 100, "C2-A requires at least100 training matches")


def cold_start_json(artifact: ColdStartArtifact) -> bytes:
    """Validate internal consistency, NOT source authenticity; no JSON loader."""
    _need(type(artifact) is ColdStartArtifact, "Typed ColdStartArtifact required")
    _policy(artifact.policy)
    _restrictions(artifact)
    _need(artifact.version == VERSION and artifact.warnings == WARNINGS
          and artifact.exposure == ((2024, "DEVELOPMENT_ONLY"), (2025, cp.EXPOSED)), "Governance changed")
    _need(type(artifact.sources) is tuple and len(artifact.sources) == 2
          and all(type(s) is data.archive.OpenFootballSource for s in artifact.sources), "Typed sources required")
    for digest in (artifact.protocol_sha256, artifact.dataset_sha256, artifact.profile_sha256, artifact.source_fingerprint):
        _digest(digest)
    _need(artifact.source_fingerprint == _fingerprint(artifact), "Source fingerprint changed")
    _need(type(artifact.folds) is tuple and 1 <= len(artifact.folds) <= 380
          and all(type(f) is ColdStartFold for f in artifact.folds), "Immutable nonempty folds required")
    dates = tuple(f.target_date for f in artifact.folds)
    _need(all(type(d) is date for d in dates) and dates == tuple(sorted(set(dates))), "Invalid target date groups")
    totals, targets = Counter(), set()
    for fold in artifact.folds:
        _restrictions(fold)
        _need(fold == _seal(fold), "Fold seal mismatch")
        _need(fold.training_date_limit == fold.target_date - timedelta(days=artifact.policy.embargo_days), "Cutoff changed")
        for digest in (fold.fold_sha256, fold.training_ids_sha256, fold.training_rows_sha256):
            _digest(digest)
        n = _history(fold.training_counts, artifact.policy.minimum_history_matches)
        _need(type(fold.training_ids) is tuple and all(type(i) is str and i for i in fold.training_ids)
              and len(fold.training_ids) == len(set(fold.training_ids)) == n
              and data.archive._hash(fold.training_ids) == fold.training_ids_sha256, "Training support changed")
        _need(type(fold.forecasts) is tuple and 1 <= len(fold.forecasts) <= 10, "Whole immutable target group required")
        for forecast in fold.forecasts:
            _need(type(forecast) is ColdStartForecast and type(forecast.fixture) is cp.FixtureReference, "Typed forecast required")
            _restrictions(forecast)
            ref = forecast.fixture
            _need(ref.historical_available_at is None and ref.kickoff_utc is None
                  and ref.strict_point_in_time_eligible is False and type(ref.match_date) is date
                  and ref.season_start_year == 2024 and ref.match_date == fold.target_date,
                  "Invalid development target/restrictions")
            _digest(ref.source_sha256)
            _need(type(ref.fixture_id) is str and ref.fixture_id and ref.fixture_id not in targets
                  and ref.fixture_id not in fold.training_ids, "Duplicate/overlapping target")
            targets.add(ref.fixture_id)
            expected = _decision(fold.training_counts, artifact.policy.minimum_history_matches,
                                  fold.training_population, ref.home_team_id, ref.away_team_id)
            _history(forecast.training_counts, artifact.policy.minimum_history_matches)
            _need(type(forecast.probabilities) is tuple
                  and all(type(p) is float and math.isfinite(p) for p in forecast.probabilities)
                  and (forecast.category, forecast.reason, forecast.probabilities) == expected, "Decision/probabilities changed")
            _need((forecast.training_counts, forecast.training_matches, forecast.training_ids_sha256,
                   forecast.training_rows_sha256, forecast.fold_sha256, forecast.protocol_sha256, forecast.source_fingerprint)
                  == (fold.training_counts, n, fold.training_ids_sha256, fold.training_rows_sha256,
                      fold.fold_sha256, artifact.protocol_sha256, artifact.source_fingerprint)
                  and type(forecast.training_matches) is int, "Forecast support mismatch")
            totals[forecast.category] += 1
    _need(type(artifact.category_counts) is tuple
          and all(type(item) is tuple and len(item) == 2 and type(item[1]) is int for item in artifact.category_counts)
          and artifact.category_counts == tuple((k, totals[k]) for k in CATEGORIES)
          and type(artifact.all_targets) is int and artifact.all_targets == len(targets) == sum(totals.values()),
          "All-target accounting mismatch")
    _need(artifact == _seal(artifact), "Artifact seal mismatch")
    return data.archive._json(artifact)


def build_cold_start_artifact(protocol: cp.CandidateProtocol, dataset: data.ExploratoryMultiSeasonDataset,
                              inputs: tuple[data.SeasonInput, ...], *, license_bytes: bytes) -> ColdStartArtifact:
    """Revalidate exact source/license AND full C1 protocol before any label join."""
    _need(type(protocol) is cp.CandidateProtocol, "Typed source-backed C1 protocol required")
    _policy(protocol.policy)
    # verify_protocol rebuilds C1 through development_folds, whose public trust
    # boundary calls verify_completed_dataset. No hash-only shortcut or fitting.
    cp.verify_protocol(protocol, dataset, inputs, license_bytes=license_bytes)
    artifact = _assemble(protocol, dataset.rows)
    cold_start_json(artifact)
    return artifact


def verify_cold_start_artifact(artifact, protocol, dataset, inputs, *, license_bytes):
    """Reject re-sealed spoofs by exact raw-source and protocol recomputation."""
    original = cold_start_json(artifact)
    replay = build_cold_start_artifact(protocol, dataset, inputs, license_bytes=license_bytes)
    _need(original == cold_start_json(replay), "Source-backed cold-start replay mismatch")
    return True
