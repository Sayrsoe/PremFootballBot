"""Read-only adapter for the two repository-pinned OpenFootball seasons."""
from datetime import date, datetime
from functools import lru_cache
import json
from pathlib import Path

from premfootballbot.completed_epl import PINS, SeasonInput
from premfootballbot.historical_stats import HistoricalReport, historical_report
from premfootballbot.openfootball_exploratory import MAX_BYTES, OpenFootballSource

ARCHIVE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "completed_epl"
SEASONS = tuple(pin[0] for pin in PINS)


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Archive input exceeds its byte limit.")
    return data


@lru_cache(maxsize=24)
def _report(archives, license_bytes, home, away, season, analysis_date):
    # Immutable source bytes, source metadata, license and all query fields
    # participate in cache identity. The historical API still verifies the pins.
    return historical_report(archives, license_bytes=license_bytes, home_team=home,
                             away_team=away, season_start_year=season, analysis_date=analysis_date)


def load_report(home: str, away: str, season: int, analysis_date: date,
                *, folder: Path = ARCHIVE) -> HistoricalReport:
    try:
        metadata = json.loads(_read(folder / "SOURCES.json", 16_384))
        if type(metadata) is not list or len(metadata) != len(SEASONS):
            raise ValueError("Expected the two pinned source records.")
        archives = []
        for item in metadata:
            source = OpenFootballSource(**dict(item, retrieved_at_utc=datetime.fromisoformat(item["retrieved_at_utc"])))
            filename = next(path.split("/")[0] + ".txt" for _, path, _, _ in PINS if path == source.path)
            archives.append(SeasonInput(_read(folder / filename, MAX_BYTES), source))
        return _report(tuple(archives), _read(folder / "LICENSE.md", 20_000), home, away, season, analysis_date)
    except (OSError, TypeError, ValueError, OverflowError, KeyError, StopIteration):
        return HistoricalReport(home, away, season, analysis_date, 2, None, 5, 30,
                                "INVALID_SOURCE_COVERAGE", "ARCHIVE_LOAD_FAILED")


def report_statuses(report: HistoricalReport) -> tuple[str, ...]:
    if report.source_status != "VERIFIED_PINNED_ARCHIVE":
        return ("SOURCE_INVALID",)
    statuses = []
    if report.stale or report.home.stale or report.away.stale:
        statuses.append("STALE_HISTORICAL_DATA")
    for team in (report.home, report.away):
        if team.status != "AVAILABLE" and team.status not in statuses:
            statuses.append(team.status)
    return tuple(statuses) or ("HISTORICAL_DATA_AVAILABLE",)
