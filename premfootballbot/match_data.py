"""Strict offline synthetic observations; no provider access or model fitting.

Import through parse_synthetic_json. Select only historically available FT90
outcomes through select_as_of. Existing settlement/Poisson APIs are independent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Mapping

SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 10_000
_UTC = timezone.utc
_NAMESPACE = re.compile(r"synthetic:[a-z][a-z0-9_-]*")
_SLUG = r"[a-z][a-z0-9_-]*"
_STAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
_STATUSES = {"SCHEDULED", "TIMED", "IN_PLAY", "FINISHED", "POSTPONED",
             "CANCELLED", "ABANDONED", "AWARDED", "SUSPENDED"}
_RESULT_STATUSES = {"FINISHED", "POSTPONED", "CANCELLED", "ABANDONED",
                    "AWARDED", "SUSPENDED"}

@dataclass(frozen=True, slots=True, order=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str

class MatchDataError(ValueError):
    """Invalid import; issues carry deterministic machine-readable diagnostics."""
    def __init__(self, issues: tuple[Issue, ...]):
        self.issues = issues
        super().__init__("; ".join(f"{i.code} at {i.path}: {i.message}" for i in issues))

@dataclass(frozen=True, slots=True)
class Team:
    team_id: str
    aliases: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class SourceDocument:
    source_id: str
    source_document_id: str
    content_utf8: str
    source_checksum_sha256: str
    source_terms_id: str
    licence_status: str
    is_synthetic: bool

@dataclass(frozen=True, slots=True)
class Observation:
    schema_version: int
    competition_code: str
    season_start_year: int
    fixture_id: str
    revision: int
    record_type: str
    status: str
    home_team_id: str
    away_team_id: str
    kickoff_utc: datetime | None
    kickoff_precision: str
    home_goals_90: int | None
    away_goals_90: int | None
    result_basis: str | None
    available_at_utc: datetime | None
    retrieved_at_utc: datetime
    source_id: str
    source_record_id: str
    source_document_id: str
    source_checksum_sha256: str
    source_terms_id: str
    licence_status: str
    is_synthetic: bool
    supersedes_revision: int | None = None
    match_date: date | None = None
    home_team_name_raw: str | None = None
    away_team_name_raw: str | None = None

@dataclass(frozen=True, slots=True)
class ImportResult:
    namespace: str | None = None
    teams: tuple[Team, ...] = ()
    source_documents: tuple[SourceDocument, ...] = ()
    observations: tuple[Observation, ...] = ()
    issues: tuple[Issue, ...] = ()
    duplicates_removed: int = 0
    content_sha256: str | None = None

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity == "warning")

    @property
    def valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> ImportResult:
        if self.errors:
            raise MatchDataError(self.errors)
        return self

@dataclass(frozen=True, slots=True, order=True)
class Exclusion:
    fixture_id: str
    revision: int
    reason: str

@dataclass(frozen=True, slots=True)
class AsOfSelection:
    cutoff_utc: datetime
    observations: tuple[Observation, ...]
    exclusions: tuple[Exclusion, ...]

@dataclass(frozen=True, slots=True)
class SnapshotManifest:
    schema_version: int
    namespace: str
    content_sha256: str
    observation_count: int
    retrievals: tuple[tuple[str, str, int, datetime], ...]
    source_checksums: tuple[tuple[str, str, str], ...]

@dataclass(frozen=True, slots=True)
class SeasonCoverage:
    season_start_year: int
    observation_count: int
    fixture_count: int
    eligible_results: int
    unknown_availability: int
    coarse_kickoffs: int
    status_counts: tuple[tuple[str, int], ...]
    expected_matches: int | None
    fixture_completeness: str
    result_completeness: str

class _Invalid(Exception):
    def __init__(self, code: str, path: str, message: str):
        self.issue = Issue("error", code, path, message)

def _need(condition: bool, code: str, path: str, message: str) -> None:
    if not condition:
        raise _Invalid(code, path, message)

def _shape(raw, required: set[str], optional: set[str], path: str) -> None:
    _need(isinstance(raw, dict), "TYPE", path, "Expected a JSON object")
    missing = required - raw.keys()
    _need(not missing, "MISSING_FIELD", path, "Missing: " + ", ".join(sorted(missing)))
    extra = raw.keys() - required - optional
    _need(not extra, "UNKNOWN_FIELD", path, "Unknown: " + ", ".join(sorted(extra)))

def _text(value, path: str) -> str:
    _need(isinstance(value, str) and bool(value) and value == value.strip(),
          "TEXT", path, "Expected nonempty text without surrounding whitespace")
    try:
        value.encode("utf8")
    except UnicodeEncodeError:
        raise _Invalid("TEXT", path, "Text must encode as UTF8") from None
    return value

def _integer(value, path: str, minimum: int = 0, maximum: int | None = None) -> int:
    _need(type(value) is int, "INTEGER", path, "Expected an integer, excluding bool")
    _need(value >= minimum and (maximum is None or value <= maximum),
          "RANGE", path, "Integer outside supported range")
    return value

def _choice(value, allowed: set[str], path: str) -> str:
    _need(isinstance(value, str) and value in allowed, "ENUM", path,
          "Expected one of: " + ", ".join(sorted(allowed)))
    return value

def _identifier(value, namespace: str, kind: str, path: str) -> str:
    value = _text(value, path)
    _need(re.fullmatch(re.escape(namespace) + ":" + kind + ":" + _SLUG, value) is not None,
          "NAMESPACE", path, f"Expected {namespace}:{kind}:<slug>")
    return value

def _timestamp(value, path: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    _need(isinstance(value, str) and _STAMP.fullmatch(value) is not None
          and not value.endswith("-00:00"), "TIMESTAMP", path,
          "Expected exact RFC3339 timestamp with known offset, at most six fraction digits")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_UTC)
    except (ValueError, OverflowError):
        raise _Invalid("TIMESTAMP", path, "Invalid or out-of-range timestamp") from None

def _label(raw) -> str:
    if not isinstance(raw, dict):
        return "records[invalid]"
    fixture = raw.get("fixture_id")
    revision = raw.get("revision")
    if not isinstance(fixture, str) or re.fullmatch(r"[a-z0-9:_-]+", fixture) is None:
        fixture = "invalid"
    return f"records[{fixture}@{revision if type(revision) is int else 'invalid'}]"

def _team(raw, ns: str) -> Team:
    _shape(raw, {"team_id", "aliases"}, set(), "teams")
    name = _identifier(raw["team_id"], ns, "team", "teams.team_id")
    aliases = raw["aliases"]
    _need(isinstance(aliases, list), "TYPE", name, "aliases must be a list")
    values = tuple(sorted(_text(a, name + ".aliases") for a in aliases))
    _need(len(set(values)) == len(values), "ALIAS", name, "Duplicate alias")
    return Team(name, values)

def _source(raw, ns: str) -> SourceDocument:
    fields = set(SourceDocument.__dataclass_fields__)
    _shape(raw, fields, set(), "source_documents")
    for key, kind in (("source_id", "source"), ("source_document_id", "document"),
                      ("source_terms_id", "terms")):
        _identifier(raw[key], ns, kind, "source_documents." + key)
    _need(type(raw["is_synthetic"]) is bool and raw["is_synthetic"],
          "SYNTHETIC_ONLY", "source_documents", "Only explicit synthetic documents accepted")
    _choice(raw["licence_status"], {"CLEARED", "UNKNOWN", "BLOCKED"},
            "source_documents.licence_status")
    content = _text(raw["content_utf8"], "source_documents.content_utf8")
    checksum = _text(raw["source_checksum_sha256"], "source_documents.source_checksum_sha256")
    _need(re.fullmatch(r"[0-9a-f]{64}", checksum) is not None
          and hashlib.sha256(content.encode("utf8")).hexdigest() == checksum,
          "SOURCE_CHECKSUM", "source_documents", "Declared checksum must match embedded text bytes")
    return SourceDocument(**raw)

_OPTIONAL = {"supersedes_revision", "match_date", "home_team_name_raw", "away_team_name_raw"}
_REQUIRED = set(Observation.__dataclass_fields__) - _OPTIONAL

def _observation(raw, ns: str, teams: set[str], aliases: dict[str, str],
                 sources: dict[tuple[str, str], SourceDocument]) -> Observation:
    path = _label(raw)
    _shape(raw, _REQUIRED, _OPTIONAL, path)
    row = dict(raw)
    for name in _OPTIONAL:
        row.setdefault(name, None)
    _need(type(row["schema_version"]) is int and row["schema_version"] == SCHEMA_VERSION,
          "VERSION", path, "schema_version must be integer 1")
    _need(row["competition_code"] == "EPL", "COMPETITION", path, "Only EPL is supported")
    _integer(row["season_start_year"], path + ".season_start_year", 1992, 9998)
    _integer(row["revision"], path + ".revision")
    if row["supersedes_revision"] is not None:
        _integer(row["supersedes_revision"], path + ".supersedes_revision")
    for name, kind in (("fixture_id", "fixture"), ("source_id", "source"),
                       ("source_record_id", "record"), ("source_document_id", "document"),
                       ("source_terms_id", "terms")):
        _identifier(row[name], ns, kind, path + "." + name)
    _need(type(row["is_synthetic"]) is bool and row["is_synthetic"],
          "SYNTHETIC_ONLY", path, "Only explicit synthetic observations accepted")
    for side in ("home", "away"):
        team = _text(row[side + "_team_id"], path + "." + side + "_team_id")
        _need(team in teams, "TEAM", path, "Unknown canonical team ID")
        name = row[side + "_team_name_raw"]
        if name is not None:
            _text(name, path + "." + side + "_team_name_raw")
            _need(aliases.get(name) == team, "ALIAS", path, "Raw team name must map explicitly to its ID")
    _need(row["home_team_id"] != row["away_team_id"], "TEAM", path, "Home and away must differ")
    _choice(row["record_type"], {"fixture", "result"}, path + ".record_type")
    _choice(row["status"], _STATUSES, path + ".status")
    finished = row["status"] == "FINISHED"
    _need(not finished or row["record_type"] == "result", "RESULT", path,
          "FINISHED requires record_type=result")
    _need(row["record_type"] != "result" or row["status"] in _RESULT_STATUSES,
          "RESULT", path, "Result observations require a result/exception status")
    if finished:
        _integer(row["home_goals_90"], path + ".home_goals_90")
        _integer(row["away_goals_90"], path + ".away_goals_90")
        _need(row["result_basis"] == "FT90", "RESULT", path, "Finished results require FT90")
    else:
        _need(row["home_goals_90"] is None and row["away_goals_90"] is None
              and row["result_basis"] is None, "RESULT", path, "Nonfinished observations require null scores/basis")
    precision = _choice(row["kickoff_precision"], {"exact", "date_only", "unknown"},
                        path + ".kickoff_precision")
    row["kickoff_utc"] = _timestamp(row["kickoff_utc"], path + ".kickoff_utc", nullable=precision != "exact")
    if row["match_date"] is not None:
        day = _text(row["match_date"], path + ".match_date")
        _need(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day) is not None,
              "DATE", path, "Expected YYYY-MM-DD")
        try:
            row["match_date"] = date.fromisoformat(day)
        except ValueError:
            raise _Invalid("DATE", path, "Invalid date") from None
    if precision == "exact":
        _need(row["match_date"] is None or row["match_date"] == row["kickoff_utc"].date(),
              "PRECISION", path, "Exact match_date must be the UTC kickoff date")
    else:
        _need(row["kickoff_utc"] is None, "PRECISION", path, "Coarse kickoff cannot carry an exact timestamp")
        _need((precision == "date_only") == (row["match_date"] is not None),
              "PRECISION", path, "date_only requires a date; unknown has neither date nor kickoff")
    row["available_at_utc"] = _timestamp(row["available_at_utc"], path + ".available_at_utc", nullable=True)
    row["retrieved_at_utc"] = _timestamp(row["retrieved_at_utc"], path + ".retrieved_at_utc")
    available, retrieved, kickoff = row["available_at_utc"], row["retrieved_at_utc"], row["kickoff_utc"]
    _need(available is None or retrieved >= available, "AVAILABILITY", path,
          "Retrieval cannot precede the declared observation availability")
    if finished and kickoff is not None and available is not None:
        try:
            earliest = kickoff + timedelta(minutes=90)
        except OverflowError:
            raise _Invalid("TIMESTAMP", path, "Kickoff exceeds supported result datetime range") from None
        _need(available >= earliest, "AVAILABILITY", path, "FT90 result cannot be known before kickoff+90min")
    _choice(row["licence_status"], {"CLEARED", "UNKNOWN", "BLOCKED"}, path + ".licence_status")
    key = (row["source_id"], row["source_document_id"])
    _need(key in sources, "PROVENANCE", path, "Source document must be registered")
    source = sources[key]
    for name in ("source_checksum_sha256", "source_terms_id", "licence_status", "is_synthetic"):
        _need(type(row[name]) is type(getattr(source, name)) and row[name] == getattr(source, name),
              "PROVENANCE", path, "Observation provenance must match registered source document")
    return Observation(**row)

def _plain(value):
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value

def _record_content(row: Observation) -> dict:
    result = asdict(row)
    del result["retrieved_at_utc"]
    return _plain(result)

def _issue_order(issues: list[Issue]) -> tuple[Issue, ...]:
    return tuple(sorted(set(issues)))

def _groups(rows: tuple[Observation, ...] | list[Observation]) -> dict[str, list[Observation]]:
    result: dict[str, list[Observation]] = {}
    for row in rows:
        result.setdefault(row.fixture_id, []).append(row)
    return {key: sorted(value, key=lambda r: r.revision) for key, value in sorted(result.items())}

def _chains(rows: list[Observation]) -> None:
    for fixture, versions in _groups(rows).items():
        first = versions[0]
        identity = (first.source_id, first.source_record_id, first.competition_code,
                    first.season_start_year, first.home_team_id, first.away_team_id)
        last_known = None
        for index, row in enumerate(versions):
            _need(row.revision == index and row.supersedes_revision == (None if index == 0 else index - 1),
                  "REVISION_CHAIN", fixture, "Require complete consecutive revisions starting at zero")
            current = (row.source_id, row.source_record_id, row.competition_code,
                       row.season_start_year, row.home_team_id, row.away_team_id)
            _need(identity == current, "REVISION_CHAIN", fixture, "Fixture/source/team/season identity cannot change")
            if row.available_at_utc is not None:
                _need(last_known is None or row.available_at_utc > last_known,
                      "REVISION_CHAIN", fixture, "Known revision availability must increase strictly")
                last_known = row.available_at_utc

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result

def _reject_constant(value):
    raise ValueError("Nonfinite JSON number")

def _json_order(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)

def parse_synthetic_json(data: bytes) -> ImportResult:
    """Parse version-1 UTF8 bytes atomically; invalid input returns issues.

    Unknown fields/duplicate keys fail closed. No network/filesystem/clock
    access occurs. Use require_valid() to raise MatchDataError on errors.
    Directly fabricated output dataclasses are not an alternative import API.
    """
    if not isinstance(data, bytes):
        raise TypeError("data must be UTF8 bytes")
    if len(data) > MAX_INPUT_BYTES:
        return ImportResult(issues=(Issue("error", "SIZE", "input", "Input exceeds 4 MiB"),))
    try:
        raw = json.loads(data.decode("utf8"), object_pairs_hook=_unique_object,
                         parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        return ImportResult(issues=(Issue("error", "JSON", "input", "Invalid UTF8/strict JSON"),))
    issues: list[Issue] = []
    try:
        _shape(raw, {"schema_version", "namespace", "teams", "source_documents", "records"}, set(), "input")
        _need(type(raw["schema_version"]) is int and raw["schema_version"] == SCHEMA_VERSION,
              "VERSION", "input", "schema_version must be integer 1")
        ns = _text(raw["namespace"], "namespace")
        _need(_NAMESPACE.fullmatch(ns) is not None, "NAMESPACE", "namespace", "Expected synthetic:<slug>")
        for name in ("teams", "source_documents", "records"):
            _need(isinstance(raw[name], list), "TYPE", name, "Expected a list")
        _need(len(raw["records"]) <= MAX_RECORDS, "SIZE", "records", "At most 10000 observations")
        teams = tuple(sorted((_team(r, ns) for r in sorted(raw["teams"], key=_json_order)),
                             key=lambda r: r.team_id))
        _need(len({t.team_id for t in teams}) == len(teams), "TEAM", "teams", "Duplicate canonical team")
        aliases: dict[str, str] = {}
        for team in teams:
            for alias in team.aliases:
                _need(alias not in aliases, "ALIAS", "teams", "Alias must identify exactly one team")
                aliases[alias] = team.team_id
        documents = tuple(sorted((_source(r, ns) for r in sorted(raw["source_documents"], key=_json_order)),
                                 key=lambda r: (r.source_id, r.source_document_id)))
        sources = {(s.source_id, s.source_document_id): s for s in documents}
        _need(len(sources) == len(documents), "PROVENANCE", "source_documents", "Duplicate source document")
        rows: list[Observation] = []
        for item in raw["records"]:
            try:
                rows.append(_observation(item, ns, {t.team_id for t in teams}, aliases, sources))
            except _Invalid as error:
                issues.append(error.issue)
        unique: dict[tuple[str, str, int], Observation] = {}
        copies: dict[tuple[str, str, int], int] = {}
        # Stable validation order also makes conflicting-input diagnostics
        # independent of source order, without picking a conflicting winner.
        for row in sorted(rows, key=lambda r: (r.source_id, r.source_record_id,
                                              r.revision, _json_order(_record_content(r)))):
            key = (row.source_id, row.source_record_id, row.revision)
            if key in unique:
                _need(_record_content(row) == _record_content(unique[key]), "CONFLICTING_DUPLICATE",
                      row.fixture_id, "Same source record/revision has different content or provenance")
                copies[key] = copies.get(key, 0) + 1
                unique[key] = replace(row, retrieved_at_utc=min(row.retrieved_at_utc, unique[key].retrieved_at_utc))
            else:
                unique[key] = row
        rows = sorted(unique.values(), key=lambda r: (r.fixture_id, r.revision))
        _chains(rows)
        for key, count in sorted(copies.items()):
            issues.append(Issue("warning", "DUPLICATE_REMOVED", str(key), f"Removed {count} identical copies"))
        for row in rows:
            path = f"{row.fixture_id}@{row.revision}"
            if row.available_at_utc is None:
                issues.append(Issue("warning", "UNKNOWN_AVAILABILITY", path, "Historical availability is unknown"))
            if row.kickoff_precision != "exact":
                issues.append(Issue("warning", "COARSE_KICKOFF", path, "Excluded from exact cutoff selection"))
            if row.licence_status != "CLEARED":
                issues.append(Issue("warning", "LICENCE_NOT_CLEARED", path, "Excluded from eligible outcomes"))
        if any(i.severity == "error" for i in issues):
            return ImportResult(issues=_issue_order(issues))
        result = ImportResult(ns, teams, documents, tuple(rows), _issue_order(issues), sum(copies.values()))
        return replace(result, content_sha256=hashlib.sha256(canonical_content(result)).hexdigest())
    except _Invalid as error:
        issues.append(error.issue)
        return ImportResult(issues=_issue_order(issues))

def _batch(batch: ImportResult) -> ImportResult:
    if not isinstance(batch, ImportResult):
        raise TypeError("Use an ImportResult returned by parse_synthetic_json")
    return batch.require_valid()

def canonical_content(batch: ImportResult) -> bytes:
    """Deterministic normalized content for hashing, excluding retrieval stamps.

    This is a content representation, not a round-trip import document.
    Source registry text/checksums, all revisions, and audit names are included.
    """
    batch = _batch(batch)
    payload = {
        "schema_version": SCHEMA_VERSION, "namespace": batch.namespace,
        "teams": [asdict(t) for t in batch.teams],
        "source_documents": [asdict(s) for s in batch.source_documents],
        "records": [_record_content(r) for r in batch.observations],
    }
    return json.dumps(_plain(payload), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf8")

def snapshot_manifest(batch: ImportResult) -> SnapshotManifest:
    """Keep mutable retrieval provenance separate from the stable content hash."""
    batch = _batch(batch)
    return SnapshotManifest(
        SCHEMA_VERSION, batch.namespace, batch.content_sha256, len(batch.observations),
        tuple(sorted((r.source_id, r.source_record_id, r.revision, r.retrieved_at_utc)
                     for r in batch.observations)),
        tuple((s.source_id, s.source_document_id, s.source_checksum_sha256)
              for s in batch.source_documents),
    )

def _ineligible(row: Observation) -> str | None:
    if row.licence_status != "CLEARED":
        return "LICENCE_NOT_CLEARED"
    if row.record_type != "result" or row.status != "FINISHED" or row.result_basis != "FT90":
        return "NOT_FINISHED_FT90"
    if row.kickoff_precision != "exact":
        return "COARSE_KICKOFF"
    if row.available_at_utc is None:
        return "UNKNOWN_AVAILABILITY"
    return None

def select_as_of(batch: ImportResult, cutoff_utc: datetime, *,
                 include_synthetic: bool = True) -> AsOfSelection:
    """Latest observed revision strictly before cutoff, then eligibility gates.

    A higher unknown-availability revision quarantines the fixture. No fallback
    from a known observed withdrawal/blocked/coarse revision. No synthetic row
    can be returned with include_synthetic=False. Retrieval is never availability.
    """
    batch = _batch(batch)
    if not isinstance(cutoff_utc, datetime):
        raise TypeError("cutoff_utc must be an aware datetime")
    if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
        raise ValueError("cutoff_utc must be timezone-aware")
    if type(include_synthetic) is not bool:
        raise TypeError("include_synthetic must be bool")
    try:
        cutoff = cutoff_utc.astimezone(_UTC)
    except (ValueError, OverflowError) as error:
        raise ValueError("cutoff_utc outside supported UTC range") from error
    selected: list[Observation] = []
    excluded: list[Exclusion] = []
    for fixture, versions in _groups(batch.observations).items():
        known: list[Observation] = []
        unknown: list[Observation] = []
        for row in versions:
            if row.available_at_utc is None:
                unknown.append(row)
                excluded.append(Exclusion(fixture, row.revision, "UNKNOWN_AVAILABILITY"))
            elif row.available_at_utc >= cutoff:
                excluded.append(Exclusion(fixture, row.revision, "NOT_YET_AVAILABLE"))
            else:
                known.append(row)
        if not known:
            continue
        latest = known[-1]
        excluded.extend(Exclusion(fixture, row.revision, "SUPERSEDED") for row in known[:-1])
        reason = ("UNCERTAIN_REVISION" if any(r.revision > latest.revision for r in unknown)
                  else "SYNTHETIC_EXCLUDED" if latest.is_synthetic and not include_synthetic
                  else _ineligible(latest))
        if reason:
            excluded.append(Exclusion(fixture, latest.revision, reason))
        else:
            selected.append(latest)
    return AsOfSelection(cutoff, tuple(selected), tuple(sorted(excluded)))

def _completeness(count: int, expected: int | None) -> str:
    if expected is None:
        return "unknown"
    return "complete" if count == expected else "partial" if count < expected else "exceeds_expected"

def summarize_coverage(batch: ImportResult, *,
                       expected_matches: Mapping[int, int] | None = None) -> tuple[SeasonCoverage, ...]:
    """Latest-present fixture coverage, not a historical training selection.

    Expected counts are optional and explicit; no universal 380-match assumption.
    eligible_results counts current precise/CLEARED/known FT90 observations.
    """
    batch = _batch(batch)
    if expected_matches is not None and not isinstance(expected_matches, Mapping):
        raise TypeError("expected_matches must be a mapping")
    expected = dict(expected_matches or {})
    for year, count in expected.items():
        if type(year) is not int or type(count) is not int:
            raise TypeError("Expected season/count must be integers, excluding bool")
        if not 1992 <= year <= 9998 or count <= 0:
            raise ValueError("Invalid expected season/count")
    years = sorted({r.season_start_year for r in batch.observations} | expected.keys())
    result = []
    for year in years:
        observations = [r for r in batch.observations if r.season_start_year == year]
        latest = [group[-1] for group in _groups(observations).values()]
        statuses: dict[str, int] = {}
        for row in latest:
            statuses[row.status] = statuses.get(row.status, 0) + 1
        eligible = sum(_ineligible(row) is None for row in latest)
        count = expected.get(year)
        result.append(SeasonCoverage(
            year, len(observations), len(latest), eligible,
            sum(r.available_at_utc is None for r in latest),
            sum(r.kickoff_precision != "exact" for r in latest),
            tuple(sorted(statuses.items())), count,
            _completeness(len(latest), count), _completeness(eligible, count),
        ))
    return tuple(result)
