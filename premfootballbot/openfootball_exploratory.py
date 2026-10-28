"""Pure offline archive staging. No synthetic conversion, training or forecasts.

EXPLORATORY ONLY / NO POINT-IN-TIME CERTIFICATION.
Checksums validate caller-supplied pins, not remote commit ancestry or truth.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re

VERSION = "phase3b-scopea-v1"
REPOSITORY = "https://github.com/openfootball/england"
LICENSE_BLOB = "670154e3538863b2d9891fd5483160fbdfc89164"
RECORD_KIND = "NON_SYNTHETIC_REAL_ARCHIVE"
EVIDENCE_STATUS = "EXPLORATORY_DATE_LEVEL_RECONSTRUCTION"
BANNER = "EXPLORATORY ONLY / NO POINT-IN-TIME CERTIFICATION; NOT VERIFIED EX-ANTE; NO REAL EPL PREDICTIVE VALIDITY CLAIM"
MAX_BYTES = 4 * 1024 * 1024
MAX_LINES = 20_000
MAX_LINE_LENGTH = 2048
_TEAMS_2023 = (
    "AFC Bournemouth", "Arsenal FC", "Aston Villa FC", "Brentford FC",
    "Brighton & Hove Albion FC", "Burnley FC", "Chelsea FC", "Crystal Palace FC",
    "Everton FC", "Fulham FC", "Liverpool FC", "Luton Town FC", "Manchester City FC",
    "Manchester United FC", "Newcastle United FC", "Nottingham Forest FC",
    "Sheffield United FC", "Tottenham Hotspur FC", "West Ham United FC",
    "Wolverhampton Wanderers FC",
)
_TEAMS_2025 = (
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton & Hove Albion",
    "Burnley", "Chelsea FC", "Crystal Palace", "Everton", "Fulham", "Leeds United",
    "Liverpool", "Manchester City", "Manchester United", "Newcastle United",
    "Nottingham Forest", "Sunderland", "Tottenham Hotspur", "West Ham United",
    "Wolverhampton Wanderers",
)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_DATE = r"(?:(Mon|Tue|Wed|Thu|Fri|Sat|Sun) )?([A-Z][a-z]{2})[ /]([0-9]{1,2})(?: ([0-9]{4}))?"
_SCORE = r"([0-9]{1,2})-([0-9]{1,2})(?: \(([0-9]{1,2})-([0-9]{1,2})\))?"
_STATUS = r"\b(?:postponed|ppd|abandoned|abd|awarded|awd|cancelled|canceled|suspended|rescheduled|aet|pen)\b|a\.e\.t\."
_CENTER = r"(.+?) +" + _SCORE + r" +(.+)"
_VERSUS = r"(.+?) +v +(.+?) +" + _SCORE
NORMALIZER_SHA256 = hashlib.sha256(json.dumps(
    (VERSION, _DATE, _SCORE, _STATUS, _CENTER, _VERSUS, _TEAMS_2023, _TEAMS_2025,
     "Jul-Jun;weekday;unknown-context-reset;all-pair-conflicts;no-UTC;embargo>=2;goals<=99;HT<=FT"),
    ensure_ascii=False, separators=(",", ":")).encode("utf8")).hexdigest()


class OpenFootballError(ValueError):
    """Atomic document/provenance or API failure; code is stable."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _need(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise OpenFootballError(code, message)


@dataclass(frozen=True, slots=True)
class OpenFootballSource:
    repository_url: str
    repository_commit_sha: str
    path: str
    expected_git_blob_sha: str
    expected_sha256: str
    licence_id: str
    licence_evidence_url: str
    licence_blob_sha: str
    retrieved_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ExploratoryMatch:
    fixture_id: str
    season_start_year: int
    match_date: date
    raw_clock_text: str | None
    home_team_raw: str
    away_team_raw: str
    home_goals_ft90: int
    away_goals_ft90: int
    halftime_score: tuple[int, int] | None
    source_line_number: int
    source_locator: str
    raw_row: str
    date_header_line: int
    raw_date_header: str
    source_sha256: str
    source_git_blob_sha: str
    licence_id: str = "CC0-1.0"
    record_kind: str = RECORD_KIND
    evidence_status: str = EVIDENCE_STATUS
    evaluation_grade: str = "EXPLORATORY_ONLY"
    date_precision: str = "INFERRED_CALENDAR_DATE"
    clock_timezone_status: str = "UNKNOWN"
    kickoff_utc: None = None
    historical_available_at: None = None
    strict_point_in_time_eligible: bool = False


@dataclass(frozen=True, slots=True)
class QuarantinedRow:
    source_line_number: int
    raw_row: str
    reason: str
    date_header_line: int | None
    raw_date_header: str | None
    match_date: date | None
    home_team_raw: str | None = None
    away_team_raw: str | None = None


@dataclass(frozen=True, slots=True)
class ExploratoryImport:
    source: OpenFootballSource
    season_start_year: int
    rows: tuple[ExploratoryMatch, ...]
    quarantined: tuple[QuarantinedRow, ...]
    header_issues: tuple[QuarantinedRow, ...]
    total_lines: int
    ignored_lines: int
    total_match_like_lines: int
    printed_clocks: int
    semantic_sha256: str
    diagnostics: tuple[str, ...]
    version: str = VERSION
    normalizer_sha256: str = NORMALIZER_SHA256
    record_kind: str = RECORD_KIND
    evidence_status: str = EVIDENCE_STATUS
    evaluation_grade: str = "EXPLORATORY_ONLY"
    banner: str = BANNER
    historical_available_at: None = None
    strict_point_in_time_eligible: bool = False
    sha256: str = ""


@dataclass(frozen=True, slots=True)
class ExploratoryCoverage:
    source: OpenFootballSource
    season_start_year: int
    total_lines: int
    ignored_lines: int
    total_match_like_lines: int
    accepted_rows: int
    quarantined_rows: int
    reason_counts: tuple[tuple[str, int], ...]
    header_reason_counts: tuple[tuple[str, int], ...]
    printed_clocks: int
    missing_clocks: int
    accepted_printed_clocks: int
    accepted_missing_clocks: int
    import_sha256: str
    semantic_sha256: str
    diagnostics: tuple[str, ...]
    version: str = VERSION
    normalizer_sha256: str = NORMALIZER_SHA256
    banner: str = BANNER
    record_kind: str = RECORD_KIND
    evidence_status: str = EVIDENCE_STATUS
    evaluation_grade: str = "EXPLORATORY_ONLY"
    date_precision: str = "INFERRED_CALENDAR_DATE"
    historical_availability: str = "UNKNOWN"
    clock_timezone_status: str = "UNKNOWN"
    strict_point_in_time_eligible_count: int = 0
    sha256: str = ""


@dataclass(frozen=True, slots=True)
class ExploratoryCandidate:
    """Semantic row facts only; audit locators remain in the source import."""
    fixture_id: str
    match_date: date
    home_team_raw: str
    away_team_raw: str
    home_goals_ft90: int
    away_goals_ft90: int
    raw_clock_text: str | None
    halftime_score: tuple[int, int] | None
    record_kind: str = RECORD_KIND
    evidence_status: str = EVIDENCE_STATUS
    strict_point_in_time_eligible: bool = False
    kickoff_utc: None = None
    historical_available_at: None = None


@dataclass(frozen=True, slots=True)
class ExploratoryDateCandidates:
    stable_source_identity: tuple[str, ...]
    target_date: date
    embargo_calendar_days: int
    target_fixture_id: str | None
    rows: tuple[ExploratoryCandidate, ...]
    version: str = VERSION
    normalizer_sha256: str = NORMALIZER_SHA256
    record_kind: str = RECORD_KIND
    evidence_status: str = EVIDENCE_STATUS
    evaluation_grade: str = "EXPLORATORY_ONLY"
    banner: str = BANNER
    policy: str = "HYPOTHETICAL retrospective candidates only; date embargo is NOT observed availability"
    strict_point_in_time_eligible: bool = False
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


def _hash(value) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _seal(value):
    data = asdict(value)
    data.pop("sha256")
    return replace(value, sha256=_hash(data))


def exploratory_json(value) -> bytes:
    """Verify and encode a sealed import/coverage/candidate snapshot as UTF8 JSON."""
    _need(type(value) in (ExploratoryImport, ExploratoryCoverage, ExploratoryDateCandidates),
          "INPUT_TYPE", "Expected an exploratory snapshot")
    _need(value.sha256 == _seal(value).sha256, "SNAPSHOT_TAMPERED", "Digest mismatch")
    return _json(value)


def _source(source: OpenFootballSource) -> tuple[OpenFootballSource, int]:
    _need(type(source) is OpenFootballSource, "SOURCE_TYPE", "Explicit source provenance is required")
    _need(source.repository_url == REPOSITORY, "REPOSITORY", "Only OpenFootball England is supported")
    for field, size in (("repository_commit_sha", 40), ("expected_git_blob_sha", 40), ("expected_sha256", 64)):
        value = getattr(source, field)
        _need(type(value) is str and re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is not None
              and value != "0" * size, "SOURCE_HASH", "Expected full lowercase immutable hash: " + field)
    _need(type(source.path) is str, "SOURCE_PATH", "Expected a supported EPL season path")
    m = re.fullmatch(r"(2023-24|2025-26)/1-premierleague\.txt", source.path)
    _need(m is not None, "SOURCE_PATH", "Only inspected EPL 2023-24 and 2025-26 profiles are supported")
    _need(source.licence_id == "CC0-1.0" and source.licence_blob_sha == LICENSE_BLOB
          and source.licence_evidence_url == f"{REPOSITORY}/blob/{source.repository_commit_sha}/LICENSE.md",
          "LICENCE", "Require checked CC0 evidence pinned to the same immutable source revision")
    stamp = source.retrieved_at_utc
    _need(type(stamp) is datetime and stamp.tzinfo is not None and stamp.utcoffset() is not None,
          "RETRIEVAL", "Require an explicit aware caller retrieval timestamp")
    try:
        stamp = stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise OpenFootballError("RETRIEVAL", "Retrieval timestamp outside UTC range") from error
    return replace(source, retrieved_at_utc=stamp), int(m[1][:4])


def _stable(source: OpenFootballSource) -> tuple[str, ...]:
    return (source.repository_url, source.path, source.licence_id, source.licence_blob_sha)


def _candidate(row: ExploratoryMatch) -> ExploratoryCandidate:
    return ExploratoryCandidate(row.fixture_id, row.match_date, row.home_team_raw,
                                row.away_team_raw, row.home_goals_ft90, row.away_goals_ft90,
                                row.raw_clock_text, row.halftime_score)


def _date_header(text: str, season: int) -> tuple[date | None, str | None]:
    m = re.fullmatch(_DATE, text)
    if m is None or m[2] not in _MONTHS:
        return None, "AMBIGUOUS_DATE"
    month = _MONTHS.index(m[2]) + 1
    year = season if month >= 7 else season + 1
    if m[4] is not None and int(m[4]) != year:
        return None, "SEASON_DATE"
    try:
        result = date(year, month, int(m[3]))
    except ValueError:
        return None, "INVALID_DATE"
    if m[1] is not None and _WEEKDAYS[result.weekday()] != m[1]:
        return None, "WEEKDAY_MISMATCH"
    return result, None


def _parts(text: str):
    # Anchored alternatives, not a search for any numeric token in a scorer line.
    for pattern, versus in ((_VERSUS, True), (_CENTER, False)):
        m = re.fullmatch(pattern, text)
        if m:
            if versus:
                home, away, h, a, hh, ha = m.groups()
            else:
                home, h, a, hh, ha, away = m.groups()
            return home, away, int(h), int(a), (None if hh is None else (int(hh), int(ha)))
    return None


def _hint(text: str, teams: tuple[str, ...]) -> tuple[str | None, str | None]:
    homes = [t for t in teams if text.startswith(t + " ")]
    if len(homes) != 1:
        return None, None
    home = homes[0]
    tail = text[len(home):]
    aways = [t for t in teams if t != home and re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", tail)]
    return (home, aways[0]) if len(aways) == 1 else (home, None)


def parse_openfootball_epl(raw_bytes: bytes, *, source: OpenFootballSource) -> ExploratoryImport:
    """Parse supplied archive bytes, failing atomically on document/provenance errors.

    Source pins are caller assertions. Verify them against the remote tree before
    calling. No online authentication, historical availability or model use occurs.
    Supported dates lie in July1..June30 of the specified inspected season profile.
    """
    source, season = _source(source)
    _need(type(raw_bytes) is bytes, "INPUT_TYPE", "Supply exact UTF8 bytes")
    _need(0 < len(raw_bytes) <= MAX_BYTES, "INPUT_SIZE", "Input must be 1 byte..4MiB")
    _need(hashlib.sha256(raw_bytes).hexdigest() == source.expected_sha256,
          "SHA256_MISMATCH", "Raw bytes do not match supplied SHA256")
    blob = hashlib.sha1(b"blob " + str(len(raw_bytes)).encode("ascii") + b"\0" + raw_bytes).hexdigest()
    _need(blob == source.expected_git_blob_sha, "GIT_BLOB_MISMATCH", "Exact Git blob mismatch")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise OpenFootballError("ENCODING", "Input is not strict UTF8") from error
    _need(not any(ord(c) < 32 and c not in "\t\r\n" for c in text)
          and not any(c in text for c in ("\ufeff", "\u2028", "\u2029", "\x7f")),
          "TEXT_CONTROL", "Unexpected control characters or embedded BOM")
    lines = text.splitlines()
    _need(len(lines) <= MAX_LINES and all(len(s) <= MAX_LINE_LENGTH for s in lines),
          "TEXT_BOUNDS", "Too many/too long lines")
    title = f"= English Premier League {season}/{str(season+1)[2:]}" if season == 2023 else "= England | Premier League 2025/26"
    _need(bool(lines) and lines[0] == title and sum(s.startswith("=") for s in lines) == 1,
          "DOCUMENT_TITLE", "Require one matching EPL title at document start")
    teams = _TEAMS_2023 if season == 2023 else _TEAMS_2025
    rows, quarantine, headers = [], [], []
    current_date, header_line, raw_header = None, None, None
    date_reason = "MISSING_DATE"
    ignored, printed, count = 0, 0, 0
    # Each observed pairing, including malformed/status rows, participates in
    # conservative duplicate detection; an unknown result never resurrects one.
    observed: dict[tuple[str, str], list[int]] = {}
    annotation_depth = 0
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith(("#", "=")):
            ignored += 1
            continue
        if line.startswith("▪"):
            _need(re.fullmatch(r"▪ (?:Matchday|Regular Season -) (?:[1-9]|[12][0-9]|3[0-8])", line) is not None,
                  "SECTION_HEADER", "Unsupported competition/round header")
            current_date, header_line, raw_header = None, None, None
            date_reason = "MISSING_DATE"
            annotation_depth = 0
            ignored += 1
            continue
        if re.match(r"\[?(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|" + "|".join(_MONTHS) + r")\b", line):
            current_date, date_reason = _date_header(line, season)
            header_line, raw_header = number, raw
            if date_reason:
                headers.append(QuarantinedRow(number, raw, date_reason, number, raw, None))
            ignored += 1
            annotation_depth = 0
            continue
        # Only indented scorer parenthesis blocks with minute markers may be
        # skipped. Status-bearing annotations instead quarantine the prior row.
        indent = len(raw) - len(raw.lstrip())
        if indent >= 16 and (annotation_depth > 0 or line.startswith("(")):
            if re.search(_STATUS, line, re.IGNORECASE) or "'" not in line:
                if rows:
                    prev = rows.pop()
                    quarantine.append(QuarantinedRow(prev.source_line_number, prev.raw_row,
                        "UNVERIFIED_ANNOTATION", prev.date_header_line, prev.raw_date_header,
                        prev.match_date, prev.home_team_raw, prev.away_team_raw))
                headers.append(QuarantinedRow(number, raw, "UNVERIFIED_ANNOTATION", header_line, raw_header, current_date))
            annotation_depth = max(0, annotation_depth + line.count("(") - line.count(")"))
            ignored += 1
            continue
        annotation_depth = 0
        count += 1
        clock = None
        clock_match = re.match(r"([0-9]{2}:[0-9]{2}) +", line)
        if clock_match:
            clock = clock_match[1]
            line = line[clock_match.end():]
            printed += 1
        parsed = _parts(line)
        home, away = (parsed[:2] if parsed else _hint(line, teams))
        if home in teams and away in teams:
            observed.setdefault((home, away), []).append(number)
        reason = None
        if re.search(_STATUS, line, re.IGNORECASE):
            reason = "NOT_FINISHED_FT90"
        elif parsed is None:
            reason = "UNRECOGNIZED_ROW"
        elif home not in teams or away not in teams or home == away:
            reason = "TEAM_IDENTITY"
        elif clock and (int(clock[:2]) > 23 or int(clock[3:]) > 59):
            reason = "INVALID_CLOCK"
        elif current_date is None:
            reason = date_reason
        elif parsed[4] and (parsed[4][0] > parsed[2] or parsed[4][1] > parsed[3]):
            reason = "HALFTIME_EXCEEDS_FT90"
        if reason:
            quarantine.append(QuarantinedRow(number, raw, reason, header_line, raw_header, current_date, home, away))
            # An unfamiliar heading cannot leave the previous date active for
            # subsequent matches. A standalone status note also invalidates the
            # last parsed match rather than silently certifying its FT90 score.
            if home is None and parsed is None:
                if reason == "NOT_FINISHED_FT90" and rows:
                    previous = rows.pop()
                    quarantine.append(QuarantinedRow(previous.source_line_number, previous.raw_row,
                        "UNVERIFIED_ANNOTATION", previous.date_header_line, previous.raw_date_header,
                        previous.match_date, previous.home_team_raw, previous.away_team_raw))
                current_date, date_reason = None, "UNRECOGNIZED_DATE_CONTEXT"
            continue
        identity = "openfootball:epl:" + str(season) + ":" + _hash((home, away))
        locator = f"{source.repository_url}/blob/{source.repository_commit_sha}/{source.path}#L{number}"
        rows.append(ExploratoryMatch(identity, season, current_date, clock, home, away,
                    parsed[2], parsed[3], parsed[4], number, locator, raw, header_line,
                    raw_header, source.expected_sha256, source.expected_git_blob_sha))
    conflicts = {pair for pair, locators in observed.items() if len(locators) > 1}
    accepted = []
    for row in rows:
        if (row.home_team_raw, row.away_team_raw) in conflicts:
            quarantine.append(QuarantinedRow(row.source_line_number, row.raw_row,
                "REPEATED_PAIR_IDENTITY", row.date_header_line, row.raw_date_header,
                row.match_date, row.home_team_raw, row.away_team_raw))
        else:
            accepted.append(row)
    accepted = tuple(sorted(accepted, key=lambda r: (r.match_date, r.fixture_id)))
    diagnostics = ["CALLER_PINS_NOT_REMOTE_AUTHENTICATION", "HISTORICAL_AVAILABILITY_UNKNOWN",
                   "YEAR_INFERRED_FROM_JULY_JUNE_SEASON_WINDOW", "NO_ALIAS_CONFLATION"]
    if len(accepted) != 380:
        diagnostics.append("ACCEPTED_COUNT_DIFFERS_FROM_EPL_380")
    if len({t for r in accepted for t in (r.home_team_raw, r.away_team_raw)}) != 20:
        diagnostics.append("ACCEPTED_TEAM_COUNT_DIFFERS_FROM_EPL_20")
    return _seal(ExploratoryImport(source, season, accepted,
        tuple(sorted(quarantine, key=lambda r: (r.source_line_number, r.reason))), tuple(headers),
        len(lines), ignored, count, printed, _hash((_stable(source), tuple(_candidate(r) for r in accepted))),
        tuple(diagnostics)))


def _checked(imported) -> ExploratoryImport:
    _need(type(imported) is ExploratoryImport, "INPUT_TYPE", "Use parse_openfootball_epl")
    exploratory_json(imported)
    return imported


def summarize_exploratory_coverage(imported: ExploratoryImport) -> ExploratoryCoverage:
    """Explicit denominator/reason inventory, never a performance score."""
    imported = _checked(imported)
    clocks = sum(r.raw_clock_text is not None for r in imported.rows)
    return _seal(ExploratoryCoverage(imported.source, imported.season_start_year,
        imported.total_lines, imported.ignored_lines, imported.total_match_like_lines,
        len(imported.rows), len(imported.quarantined),
        tuple(sorted(Counter(r.reason for r in imported.quarantined).items())),
        tuple(sorted(Counter(r.reason for r in imported.header_issues).items())),
        imported.printed_clocks, imported.total_match_like_lines - imported.printed_clocks,
        clocks, len(imported.rows) - clocks, imported.sha256, imported.semantic_sha256, imported.diagnostics))


def select_exploratory_prior_dates(imported: ExploratoryImport, target_date: date, *,
        embargo_calendar_days: int = 2, target_fixture_id: str | None = None) -> ExploratoryDateCandidates:
    """Hypothetical archive candidates only; date embargo is not availability proof.

    Purely future nonconflicting additions preserve this digest. A changed earlier
    fixture or newly observed duplicate/correction can invalidate it, as intended.
    """
    imported = _checked(imported)
    _need(type(target_date) is date, "TARGET_DATE", "Require a known calendar date, not a datetime")
    _need(type(embargo_calendar_days) is int and 2 <= embargo_calendar_days <= 36600,
          "EMBARGO", "Require 2..36600 whole calendar days, excluding bool")
    _need(target_fixture_id is None or (type(target_fixture_id) is str
          and re.fullmatch(r"openfootball:epl:(2023|2025):[0-9a-f]{64}", target_fixture_id) is not None),
          "TARGET_ID", "Expected an adapter fixture identity or None")
    try:
        limit = target_date - timedelta(days=embargo_calendar_days)
    except OverflowError as error:
        raise OpenFootballError("TARGET_DATE", "Embargo outside calendar range") from error
    rows = tuple(_candidate(r) for r in imported.rows if r.match_date <= limit and r.fixture_id != target_fixture_id)
    return _seal(ExploratoryDateCandidates(_stable(imported.source), target_date,
                 embargo_calendar_days, target_fixture_id, rows))
