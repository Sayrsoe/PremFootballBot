"""Retrospective EPL summaries from the approved, replayed OpenFootball inputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from .completed_epl import (
    COMMIT, LICENSE_SHA256, CompletedEplError, CompletedMatch, SeasonInput, import_completed_epl,
)
from .openfootball_exploratory import REPOSITORY, OpenFootballError


@dataclass(frozen=True, slots=True)
class MatchResult:
    match_date: date
    fixture_id: str
    opponent: str
    venue: Literal["home", "away"]
    goals_for: int
    goals_against: int
    source_locator: str


@dataclass(frozen=True, slots=True)
class Sample:
    matches: int
    wins: int | None = None
    draws: int | None = None
    losses: int | None = None
    points: int | None = None
    goals_for: int | None = None
    goals_against: int | None = None
    goal_difference: int | None = None
    goals_for_per_match: float | None = None
    goals_against_per_match: float | None = None


@dataclass(frozen=True, slots=True)
class TeamHistory:
    team_id: str
    status: str
    overall: Sample
    home: Sample
    away: Sample
    last_5: tuple[MatchResult, ...]
    last_10: tuple[MatchResult, ...]
    last_eligible_date: date | None
    stale: bool | None


@dataclass(frozen=True, slots=True)
class HistoricalReport:
    home_team: str
    away_team: str
    season_start_year: int
    analysis_date: date
    embargo_days: int
    eligible_through: date | None
    minimum_matches: int
    stale_after_days: int
    source_status: str
    source_detail: str | None = None
    source_path: str | None = None
    source_sha256: str | None = None
    source_git_blob: str | None = None
    included_matches: int | None = None
    exclusions: tuple[tuple[str, int], ...] = ()
    last_eligible_date: date | None = None
    stale: bool | None = None
    home: TeamHistory | None = None
    away: TeamHistory | None = None
    computed_historical_standings: tuple[tuple[str, Sample], ...] = ()
    source_repository: str = REPOSITORY
    source_commit: str = COMMIT
    licence: str = "CC0-1.0"
    licence_sha256: str = LICENSE_SHA256
    record_kind: str = "NON_SYNTHETIC_REAL_ARCHIVE"
    evidence_status: str = "EXPLORATORY_DATE_LEVEL_RECONSTRUCTION"
    historical_availability: str = "UNVERIFIED"
    strict_point_in_time_eligible: Literal[False] = False
    historical_available_at: None = None
    kickoff_utc: None = None
    purpose: str = "RETROSPECTIVE_DESCRIPTIVE_ONLY"


def _sample(results: tuple[MatchResult, ...]) -> Sample:
    count = len(results)
    if not count:
        return Sample(0)
    wins = sum(r.goals_for > r.goals_against for r in results)
    draws = sum(r.goals_for == r.goals_against for r in results)
    scored = sum(r.goals_for for r in results)
    conceded = sum(r.goals_against for r in results)
    return Sample(count, wins, draws, count - wins - draws, 3 * wins + draws,
                  scored, conceded, scored - conceded, scored / count, conceded / count)


def _result(row: CompletedMatch, *, home: bool) -> MatchResult:
    match = row.original
    return MatchResult(
        match.match_date, match.fixture_id,
        row.away_team_id if home else row.home_team_id,
        "home" if home else "away",
        match.home_goals_ft90 if home else match.away_goals_ft90,
        match.away_goals_ft90 if home else match.home_goals_ft90,
        match.source_locator,
    )


def _team(team_id, results, *, absent, analysis_date, minimum_matches, stale_after_days):
    last = results[-1].match_date if results else None
    status = "AVAILABLE" if len(results) >= minimum_matches else "INSUFFICIENT_SAMPLE"
    if absent:
        status = "TEAM_ABSENT"
    return TeamHistory(team_id, status, _sample(results),
                       _sample(tuple(r for r in results if r.venue == "home")),
                       _sample(tuple(r for r in results if r.venue == "away")),
                       results[-5:], results[-10:], last,
                       None if last is None else (analysis_date - last).days > stale_after_days)


def historical_report(
    inputs: tuple[SeasonInput, ...], *, license_bytes: bytes, home_team: str,
    away_team: str, season_start_year: int, analysis_date: date, embargo_days: int = 2,
    minimum_matches: int = 5, stale_after_days: int = 30,
) -> HistoricalReport:
    """Replay both pinned archives, then describe one season through the inclusive cutoff.

    Pass canonical club IDs. Recent results are oldest first within each window.
    The reporting defaults are policy choices independent of match outcomes.
    An archive age over the threshold flags inadequate current-form coverage.
    """
    if type(analysis_date) is not date:
        raise ValueError("analysis_date must be a calendar date")
    if type(season_start_year) is not int:
        raise ValueError("season_start_year must be an integer")
    if any(type(team) is not str or not team or len(team) > 80 for team in (home_team, away_team)):
        raise ValueError("Supply two canonical club IDs")
    if home_team == away_team:
        raise ValueError("Clubs must be distinct")
    if type(embargo_days) is not int or not 2 <= embargo_days <= 366:
        raise ValueError("embargo_days must be an integer from 2 to 366")
    if type(minimum_matches) is not int or minimum_matches < 1:
        raise ValueError("minimum_matches must be a positive integer")
    if type(stale_after_days) is not int or stale_after_days < embargo_days:
        raise ValueError("stale_after_days must be an integer at least as large as the embargo")
    ordinal = analysis_date.toordinal() - embargo_days
    cutoff = date.fromordinal(ordinal) if ordinal > 0 else None
    header = dict(home_team=home_team, away_team=away_team, season_start_year=season_start_year,
                  analysis_date=analysis_date, embargo_days=embargo_days, eligible_through=cutoff,
                  minimum_matches=minimum_matches, stale_after_days=stale_after_days)
    if season_start_year not in (2024, 2025):
        return HistoricalReport(**header, source_status="UNSUPPORTED_SOURCE", source_detail="UNSUPPORTED_SEASON")
    try:
        dataset = import_completed_epl(inputs, license_bytes=license_bytes)
    except (CompletedEplError, OpenFootballError) as exc:
        unsupported = exc.code in {"UNSUPPORTED_SEASON", "SEASONS"}
        return HistoricalReport(**header, source_status="UNSUPPORTED_SOURCE" if unsupported else "INVALID_SOURCE_COVERAGE",
                                source_detail=exc.code)
    season = next(s for s in dataset.seasons if s.season_start_year == season_start_year)
    rows = tuple(r for r in dataset.rows if r.original.season_start_year == season_start_year)
    eligible = sorted((r for r in rows if cutoff is not None and r.original.match_date <= cutoff),
                      key=lambda r: (r.original.match_date, r.original.fixture_id))
    future = sum(r.original.match_date > analysis_date for r in rows)
    last = eligible[-1].original.match_date if eligible else None
    by_team: dict[str, list[MatchResult]] = {}
    for row in eligible:
        by_team.setdefault(row.home_team_id, []).append(_result(row, home=True))
        by_team.setdefault(row.away_team_id, []).append(_result(row, home=False))
    teams = tuple(
        _team(team, tuple(by_team.get(team, ())), absent=bool(eligible) and team not in season.clubs,
              analysis_date=analysis_date, minimum_matches=minimum_matches, stale_after_days=stale_after_days)
        for team in (home_team, away_team)
    )
    # Results-only points, goal difference and goals scored, with an ID tie-break
    # for deterministic presentation. Clubs appear once they have eligible results.
    standings = [(team, _sample(tuple(results))) for team, results in by_team.items()]
    standings.sort(key=lambda entry: (-entry[1].points, -entry[1].goal_difference, -entry[1].goals_for, entry[0]))
    return HistoricalReport(
        **header, source_status="VERIFIED_PINNED_ARCHIVE", source_path=season.source.path,
        source_sha256=season.source.expected_sha256, source_git_blob=season.source.expected_git_blob_sha,
        included_matches=len(eligible), exclusions=(("AFTER_ANALYSIS_DATE", future),
                                                   ("DATE_EMBARGO", len(rows) - len(eligible) - future)),
        last_eligible_date=last, stale=None if last is None else (analysis_date - last).days > stale_after_days,
        home=teams[0], away=teams[1], computed_historical_standings=tuple(standings),
    )
