"""Pinned offline completed EPL seasons. EXPLORATORY, not point-in-time data.

No training, forecasts, I/O or trusted time. Source acquisition is never match
availability. The original parser and its model-authorized fingerprint are intact.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import re

from . import openfootball_exploratory as archive

VERSION = "phase4a-completed-epl-v1"
ALIAS_VERSION = "epl-reviewed-aliases-2024-2025-v1"
COMMIT = "9ee7a0c351805c99cc334478a9bf04b7d0432fec"
LICENSE_SHA256 = "36ffd9dc085d529a7e60e1276d73ae5a030b020313e6c5408593a6ae2af39673"
PINS = (
    (2024, "2024-25/1-premierleague.txt", "ca0fe4923f0164d0f879f796ab0759253e13bc06",
     "e39716b01af0c8654a9fae7b5555e6b02f506ea05239e0d0eef41936ba80e1e3"),
    (2025, "2025-26/1-premierleague.txt", "918adf1c0af4f613c73530cb528ab0df72461cfb",
     "38c1de56c9e9b6662c7efc1420b7e1fe00dddbb502fe72d8f759e773ba3c093b"),
)
ALIASES_2024 = (
    ("AFC Bournemouth", "bournemouth"), ("Arsenal FC", "arsenal"), ("Aston Villa FC", "aston-villa"),
    ("Brentford FC", "brentford"), ("Brighton & Hove Albion FC", "brighton"), ("Chelsea FC", "chelsea"),
    ("Crystal Palace FC", "crystal-palace"), ("Everton FC", "everton"), ("Fulham FC", "fulham"),
    ("Ipswich Town FC", "ipswich"), ("Leicester City FC", "leicester"), ("Liverpool FC", "liverpool"),
    ("Manchester City FC", "manchester-city"), ("Manchester United FC", "manchester-united"),
    ("Newcastle United FC", "newcastle"), ("Nottingham Forest FC", "nottingham-forest"),
    ("Southampton FC", "southampton"), ("Tottenham Hotspur FC", "tottenham"),
    ("West Ham United FC", "west-ham"), ("Wolverhampton Wanderers FC", "wolves"),
)
ALIASES_2025 = (
    ("Arsenal", "arsenal"), ("Aston Villa", "aston-villa"), ("Bournemouth", "bournemouth"),
    ("Brentford", "brentford"), ("Brighton & Hove Albion", "brighton"), ("Burnley", "burnley"),
    ("Chelsea FC", "chelsea"), ("Crystal Palace", "crystal-palace"), ("Everton", "everton"),
    ("Fulham", "fulham"), ("Leeds United", "leeds"), ("Liverpool", "liverpool"),
    ("Manchester City", "manchester-city"), ("Manchester United", "manchester-united"),
    ("Newcastle United", "newcastle"), ("Nottingham Forest", "nottingham-forest"),
    ("Sunderland", "sunderland"), ("Tottenham Hotspur", "tottenham"),
    ("West Ham United", "west-ham"), ("Wolverhampton Wanderers", "wolves"),
)
PROFILE_SHA256 = archive._hash((VERSION, ALIAS_VERSION, PINS, ALIASES_2024, ALIASES_2025,
                              archive.NORMALIZER_SHA256, "strict-v24;no-UTC;380-pairs;round10"))


@dataclass(frozen=True, slots=True)
class ImportIssue:
    line: int
    reason: str
    raw: str


class CompletedEplError(ValueError):
    def __init__(self, code, message, issues=()):
        self.code, self.issues = code, tuple(issues)
        super().__init__(f"{code}: {message}; issues={self.issues}")


def _need(condition, code, message):
    if not condition:
        raise CompletedEplError(code, message)


@dataclass(frozen=True, slots=True)
class SeasonInput:
    raw_bytes: bytes
    source: archive.OpenFootballSource


@dataclass(frozen=True, slots=True)
class CompletedMatch:
    original: archive.ExploratoryMatch
    home_team_id: str
    away_team_id: str
    nominal_round: int


@dataclass(frozen=True, slots=True)
class SeasonCoverage:
    source: archive.OpenFootballSource
    season_start_year: int
    accepted_results: int
    clubs: tuple[str, ...]
    appearances: tuple[tuple[str, int, int], ...]
    round_counts: tuple[tuple[int, int], ...]
    missing_halftime: int
    missing_printed_clock: int
    earliest_date: str
    latest_date: str
    home_goals: int
    away_goals: int
    issues: tuple[ImportIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class ExploratoryMultiSeasonDataset:
    rows: tuple[CompletedMatch, ...]
    seasons: tuple[SeasonCoverage, ...]
    aliases: tuple[tuple[int, tuple[tuple[str, str], ...]], ...]
    license_sha256: str = LICENSE_SHA256
    version: str = VERSION
    alias_version: str = ALIAS_VERSION
    profile_sha256: str = PROFILE_SHA256
    inherited_parser_sha256: str = archive.NORMALIZER_SHA256
    record_kind: str = "NON_SYNTHETIC_REAL_ARCHIVE"
    evidence_status: str = "EXPLORATORY_DATE_LEVEL_RECONSTRUCTION"
    evaluation_grade: str = "EXPLORATORY_ONLY"
    strict_point_in_time_eligible: bool = False
    historical_available_at: None = None
    kickoff_utc: None = None
    diagnostics: tuple[str, ...] = (
        "PINNED_CONTENT_NOT_REMOTE_TRUTH_OR_HISTORICAL_AVAILABILITY",
        "ACQUISITION_IS_NOT_FIRST_PUBLICATION", "PRINTED_CLOCK_TIMEZONE_UNKNOWN",
        "COMPLETE_RESULTS_NOT_PREDICTIVE_VALIDATION", "NO_TRAINING_OR_FORECAST_API",
    )
    sha256: str = ""


def _seal(dataset):
    payload = asdict(dataset)
    payload.pop("sha256")
    return replace(dataset, sha256=archive._hash(payload))


def completed_json(dataset: ExploratoryMultiSeasonDataset) -> bytes:
    _need(type(dataset) is ExploratoryMultiSeasonDataset, "INPUT_TYPE", "Expected completed dataset")
    _need(dataset.sha256 == _seal(dataset).sha256, "TAMPERED", "Dataset digest mismatch")
    _need(dataset.record_kind == "NON_SYNTHETIC_REAL_ARCHIVE"
          and dataset.evidence_status == "EXPLORATORY_DATE_LEVEL_RECONSTRUCTION"
          and dataset.evaluation_grade == "EXPLORATORY_ONLY"
          and dataset.strict_point_in_time_eligible is False
          and dataset.historical_available_at is None and dataset.kickoff_utc is None,
          "RESTRICTIONS", "Retrospective/date-level restrictions required")
    _need(all(r.original.strict_point_in_time_eligible is False
              and r.original.historical_available_at is None and r.original.kickoff_utc is None
              and r.original.clock_timezone_status == "UNKNOWN"
              and r.original.record_kind == dataset.record_kind
              and r.original.evidence_status == dataset.evidence_status for r in dataset.rows),
          "RESTRICTIONS", "Rows cannot acquire retrospective timing certification")
    return archive._json(dataset)


def _aliases(pairs):
    mapping = dict(pairs)
    _need(len(mapping) == len(pairs) == 20 and len(set(mapping.values())) == 20,
          "ALIASES", "Require explicit bijective20-team season roster")
    return mapping


def _source(item):
    _need(type(item) is SeasonInput and type(item.raw_bytes) is bytes
          and type(item.source) is archive.OpenFootballSource, "INPUT_TYPE", "SeasonInput bytes/source required")
    s = item.source
    pin = next((p for p in PINS if p[1] == s.path), None)
    _need(pin is not None, "UNSUPPORTED_SEASON", "Only completed2024-25 and2025-26 authorized")
    _need(s.repository_url == archive.REPOSITORY and s.repository_commit_sha == COMMIT
          and s.expected_git_blob_sha == pin[2] and s.expected_sha256 == pin[3],
          "SOURCE_IDENTITY", "Exact approved repo/revision/path/blob/SHA256 required")
    _need(s.licence_id == "CC0-1.0" and s.licence_blob_sha == archive.LICENSE_BLOB
          and s.licence_evidence_url == f"{archive.REPOSITORY}/blob/{COMMIT}/LICENSE.md",
          "LICENCE", "Exact pinned CC0 evidence required")
    _need(type(s.retrieved_at_utc) is datetime and s.retrieved_at_utc.utcoffset() is not None,
          "ACQUISITION", "Aware acquisition timestamp required")
    s = replace(s, retrieved_at_utc=s.retrieved_at_utc.astimezone(timezone.utc))
    _need(s.retrieved_at_utc >= datetime(2026,10,15,14,42,31,tzinfo=timezone.utc),
          "ACQUISITION", "Acquisition cannot precede pinned revision")
    raw = item.raw_bytes
    _need(0 < len(raw) <= archive.MAX_BYTES, "INPUT_SIZE", "Bounded source bytes required")
    _need(hashlib.sha256(raw).hexdigest() == pin[3], "SOURCE_SHA256", "Source bytes differ")
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    _need(blob == pin[2], "SOURCE_BLOB", "Git source blob mismatch")
    return s, pin[0]


def _parse_2024(raw, source):
    """Narrow new v-layout profile, reusing original date/score/row semantics."""
    lines = raw.decode("utf8").splitlines()
    _need(bool(lines) and lines[0] == "= English Premier League 2024/25"
          and sum(l.startswith("=") for l in lines) == 1, "TITLE", "2024-25 EPL title required")
    _need(len(lines) <= archive.MAX_LINES and all(len(l) <= archive.MAX_LINE_LENGTH for l in lines),
          "TEXT_BOUNDS", "Source line limits")
    teams = _aliases(ALIASES_2024)
    rows, issues = [], []
    current, header_line, header = None, None, None
    for number, raw_row in enumerate(lines, 1):
        line = raw_row.strip()
        if not line or line.startswith(("#", "=")):
            continue
        if line.startswith("▪"):
            if not re.fullmatch(r"▪ Matchday (?:[1-9]|[12][0-9]|3[0-8])", line):
                issues.append(ImportIssue(number, "ROUND_HEADER", raw_row))
            current = None
            continue
        if re.match(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|" + "|".join(archive._MONTHS) + r")\b", line):
            current, error = archive._date_header(line, 2024)
            header_line, header = number, raw_row
            if error:
                issues.append(ImportIssue(number, error, raw_row))
            continue
        clock = None
        m = re.match(r"([0-9]{2}:[0-9]{2}) +", line)
        if m:
            clock, line = m[1], line[m.end():]
        parsed = archive._parts(line) if re.fullmatch(archive._VERSUS, line) else None
        reason = None
        if re.search(archive._STATUS, line, re.I): reason = "NOT_FINISHED_FT90"
        elif parsed is None: reason = "UNRECOGNIZED_ROW"
        elif parsed[0] not in teams or parsed[1] not in teams or parsed[0] == parsed[1]: reason = "TEAM_IDENTITY"
        elif current is None: reason = "MISSING_VALID_DATE"
        elif clock and (int(clock[:2]) > 23 or int(clock[3:]) > 59): reason = "INVALID_CLOCK"
        elif parsed[4] and (parsed[4][0] > parsed[2] or parsed[4][1] > parsed[3]): reason = "HALFTIME_EXCEEDS_FT90"
        if reason:
            issues.append(ImportIssue(number, reason, raw_row))
            if parsed is None: current = None
            continue
        h, a, hg, ag, ht = parsed
        identity = "openfootball:epl:2024:" + archive._hash((h,a))
        locator = f"{source.repository_url}/blob/{source.repository_commit_sha}/{source.path}#L{number}"
        rows.append(archive.ExploratoryMatch(identity,2024,current,clock,h,a,hg,ag,ht,
                    number,locator,raw_row,header_line,header,source.expected_sha256,source.expected_git_blob_sha))
    if issues:
        raise CompletedEplError("ROWS_REJECTED", "No partial completed season returned", issues)
    return tuple(rows)


def _normalize(rows, source, year, raw):
    mapping = _aliases(ALIASES_2024 if year == 2024 else ALIASES_2025)
    nominal, round_by_line = None, {}
    for i, line in enumerate(raw.decode("utf8").splitlines(),1):
        m = re.fullmatch(r"▪ (?:Matchday|Regular Season -) ([0-9]+)", line.strip())
        if m: nominal = int(m[1])
        round_by_line[i] = nominal
    normalized, issues = [], []
    pairs = Counter((r.home_team_raw, r.away_team_raw) for r in rows)
    for row in rows:
        if row.home_team_raw not in mapping or row.away_team_raw not in mapping:
            issues.append(ImportIssue(row.source_line_number,"UNKNOWN_ALIAS",row.raw_row)); continue
        if pairs[(row.home_team_raw,row.away_team_raw)] != 1:
            issues.append(ImportIssue(row.source_line_number,"DUPLICATE_ORDERED_PAIR",row.raw_row))
        round_number = round_by_line.get(row.source_line_number)
        if round_number is None or not 1 <= round_number <= 38:
            issues.append(ImportIssue(row.source_line_number,"MISSING_ROUND",row.raw_row)); continue
        normalized.append(CompletedMatch(row,mapping[row.home_team_raw],mapping[row.away_team_raw],round_number))
    expected = {(h,a) for h in mapping for a in mapping if h != a}
    if len(rows) != 380 or set(pairs) != expected:
        missing = tuple(sorted(expected-set(pairs)))
        issues.append(ImportIssue(0,"INCOMPLETE_SCHEDULE",f"count={len(rows)} missing={missing}"))
    home = Counter(r.home_team_id for r in normalized)
    away = Counter(r.away_team_id for r in normalized)
    rounds = Counter(r.nominal_round for r in normalized)
    if set(rounds) != set(range(1,39)) or any(n != 10 for n in rounds.values()):
        issues.append(ImportIssue(0,"ROUND_COVERAGE",str(sorted(rounds.items()))))
    if any(home[t] != 19 or away[t] != 19 for t in mapping.values()):
        issues.append(ImportIssue(0,"TEAM_APPEARANCES",str((home,away))))
    if issues:
        raise CompletedEplError("COVERAGE", "Incomplete/contradictory schedule", issues)
    normalized = tuple(sorted(normalized,key=lambda r:(r.original.match_date,r.home_team_id,r.away_team_id)))
    coverage = SeasonCoverage(source,year,len(normalized),tuple(sorted(mapping.values())),
        tuple((t,home[t],away[t]) for t in sorted(mapping.values())), tuple(sorted(rounds.items())),
        sum(r.halftime_score is None for r in rows),sum(r.raw_clock_text is None for r in rows),
        min(r.match_date for r in rows).isoformat(),max(r.match_date for r in rows).isoformat(),
        sum(r.home_goals_ft90 for r in rows),sum(r.away_goals_ft90 for r in rows))
    return normalized, coverage


def import_completed_epl(inputs: tuple[SeasonInput, ...], *, license_bytes: bytes) -> ExploratoryMultiSeasonDataset:
    """Import precisely two approved completed seasons, never fit/evaluate a model."""
    _need(type(inputs) is tuple and len(inputs) == 2, "SEASONS", "Exactly two immutable season inputs")
    _need(type(license_bytes) is bytes and 0 < len(license_bytes) <= 20000
          and hashlib.sha256(license_bytes).hexdigest() == LICENSE_SHA256,
          "LICENCE", "Exact audited license bytes required")
    _need(hashlib.sha1(b"blob "+str(len(license_bytes)).encode()+b"\0"+license_bytes).hexdigest() == archive.LICENSE_BLOB,
          "LICENCE", "License blob mismatch")
    prepared = [(_source(item),item.raw_bytes) for item in inputs]
    _need({s[0][1] for s in prepared} == {2024,2025}, "SEASONS", "No duplicate/missing season")
    all_rows, coverages = [], []
    for (source,year),raw in sorted(prepared,key=lambda x:x[0][1]):
        if year == 2024:
            rows = _parse_2024(raw,source)
        else:
            parsed = archive.parse_openfootball_epl(raw,source=source)
            issues = tuple(ImportIssue(r.source_line_number,r.reason,r.raw_row) for r in (*parsed.quarantined,*parsed.header_issues))
            if issues: raise CompletedEplError("ROWS_REJECTED", "No partial season returned", issues)
            rows = parsed.rows
        normalized, coverage = _normalize(rows,source,year,raw)
        all_rows.extend(normalized); coverages.append(coverage)
    return _seal(ExploratoryMultiSeasonDataset(tuple(all_rows),tuple(coverages),((2024,ALIASES_2024),(2025,ALIASES_2025))))


def verify_completed_dataset(dataset, inputs, *, license_bytes):
    original = completed_json(dataset)
    replay = import_completed_epl(inputs,license_bytes=license_bytes)
    _need(original == completed_json(replay), "REPLAY_MISMATCH", "Dataset differs from pinned-source replay")
    return True
