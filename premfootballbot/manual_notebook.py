"""Versioned local fixture notes and append-only, unverified AH observations."""
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from .odds_observations import price
from .settlement import parse_handicap

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_STATUS = "MANUAL_FIXTURE_UNVERIFIED"
ODDS_STATUS = "MANUAL_ODDS_UNVERIFIED"
_SCHEMA = (
    """CREATE TABLE fixtures (
        id TEXT NOT NULL, revision INTEGER NOT NULL, active INTEGER NOT NULL,
        home TEXT NOT NULL, away TEXT NOT NULL, season INTEGER NOT NULL,
        match_date TEXT NOT NULL, kickoff TEXT NOT NULL, saved TEXT NOT NULL,
        PRIMARY KEY (id, revision)
    )""",
    "CREATE UNIQUE INDEX active_id ON fixtures(id) WHERE active = 1",
    "CREATE UNIQUE INDEX active_identity ON fixtures(home, away, season, match_date) WHERE active = 1",
    """CREATE TABLE observations (
        id INTEGER PRIMARY KEY, fixture_id TEXT NOT NULL, revision INTEGER NOT NULL,
        bookmaker TEXT NOT NULL, side TEXT NOT NULL, raw_line TEXT NOT NULL,
        quarters INTEGER NOT NULL, raw_odds TEXT NOT NULL, exact_odds TEXT NOT NULL,
        source TEXT NOT NULL, claimed TEXT NOT NULL, captured TEXT NOT NULL,
        invented INTEGER NOT NULL, replaces INTEGER UNIQUE REFERENCES observations(id),
        FOREIGN KEY (fixture_id, revision) REFERENCES fixtures(id, revision)
    )""",
    "CREATE INDEX observations_by_fixture ON observations(fixture_id, revision, id)",
)


class NotebookError(ValueError):
    """A validation or local storage error safe to show in the UI."""


def database_path() -> Path:
    override = os.environ.get("PREMFOOTBALLBOT_NOTEBOOK_PATH")
    if override:
        return Path(override)
    appdata = os.environ.get("LOCALAPPDATA")
    return (Path(appdata) if appdata else Path.home() / ".local" / "share") / "PremFootballBot" / "notebook.sqlite3"


def _text(value: str, label: str, limit: int, *, optional=False) -> str:
    if type(value) is not str or len(value) > limit or (value and not value.isprintable()):
        raise NotebookError(f"{label} must be plain text of at most {limit} characters.")
    value = value.strip()
    if not value and not optional:
        raise NotebookError(f"Enter {label.lower()}.")
    return value


def team_id(value: str) -> str:
    value = re.sub(r" +", "-", _text(value, "Club ID", 80).lower())
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise NotebookError("Use a club ID such as manchester-united.")
    return value


def _utc(value: str) -> str:
    if value == "":
        return value
    if type(value) is not str or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value
    ):
        raise NotebookError("Use UTC format YYYY-MM-DDTHH:MM:SSZ.")
    try:
        return datetime.fromisoformat(value[:-1]).isoformat(timespec="microseconds") + "Z"
    except ValueError as exc:
        raise NotebookError("Enter a valid UTC date and time.") from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Fixture:
    id: str
    revision: int
    home: str
    away: str
    season: int
    match_date: date
    kickoff: str
    saved: str
    observation_count: int
    last_capture: str | None


def _fixture_values(home, away, season, match_date, kickoff):
    home, away = team_id(home), team_id(away)
    if home == away:
        raise NotebookError("Choose two distinct clubs.")
    if type(season) is not int or not 1992 <= season <= 2099:
        raise NotebookError("Enter the EPL season start year from 1992 to 2099.")
    if type(match_date) is not date or not date(season, 7, 1) <= match_date < date(season + 1, 7, 1):
        raise NotebookError("The match date must fall within the selected July–June season.")
    kickoff = _utc(kickoff)
    if kickoff and kickoff[:10] != match_date.isoformat():
        raise NotebookError("The claimed UTC kickoff must match the fixture date.")
    return home, away, season, match_date.isoformat(), kickoff


def _market_values(bookmaker, side, line, odds, source, claimed, invented):
    bookmaker = _text(bookmaker, "Bookmaker", 100)
    source = _text(source, "Source reference", 240, optional=True)
    if side not in ("HOME", "AWAY") or type(invented) is not bool:
        raise NotebookError("Select HOME or AWAY and specify whether the entry is invented.")
    if type(line) is not str or len(line) > 24:
        raise NotebookError("Enter a signed AH line in quarter-goal increments.")
    try:
        quarters = parse_handicap(line)
        exact = str(price(odds, "DECIMAL"))
    except (TypeError, ValueError) as exc:
        raise NotebookError("Use an exact quarter-goal line and decimal odds greater than 1.") from exc
    if abs(quarters) > 80:
        raise NotebookError("Enter an AH line within ±20 goals.")
    return bookmaker, side, line, quarters, odds, exact, source, _utc(claimed), int(invented)


class Notebook:
    def __init__(self, path: Path | None = None):
        path = database_path() if path is None else Path(path)
        if str(path).startswith(("\\\\", "//")):
            raise NotebookError("Choose a private local database path outside the repository.")
        try:
            self.path = path.resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise NotebookError("Choose a valid local notebook path.") from exc
        if (self.path.is_relative_to(ROOT) or str(self.path).startswith(("\\\\", "//"))
                or any((parent / ".git").exists() for parent in self.path.parents)):
            raise NotebookError("Choose a private local database path outside the repository.")

    @contextmanager
    def _db(self, *, write=False):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=3)) as db, db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys = ON")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if write or version == 0:
                    db.execute("BEGIN IMMEDIATE")
                    version = db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone():
                        raise NotebookError("Choose an empty file or an existing PremFootballBot notebook.")
                    for statement in _SCHEMA:
                        db.execute(statement)
                    db.execute("PRAGMA user_version = 1")
                elif version != 1:
                    raise NotebookError("This notebook uses an unsupported database version.")
                yield db
        except sqlite3.IntegrityError as exc:
            raise NotebookError("That fixture identity or correction already exists.") from exc
        except (sqlite3.Error, OSError) as exc:
            raise NotebookError("The local notebook could not be read or saved. Check the file and permissions.") from exc

    def fixtures(self) -> tuple[Fixture, ...]:
        with self._db() as db:
            rows = db.execute("""
                SELECT f.*, count(o.id) AS observation_count, max(o.captured) AS last_capture
                FROM fixtures f LEFT JOIN observations o ON o.fixture_id = f.id
                WHERE f.active = 1 GROUP BY f.id, f.revision ORDER BY f.match_date DESC, f.home, f.away
            """).fetchall()
        try:
            for row in rows:
                _fixture_values(row["home"], row["away"], row["season"],
                                date.fromisoformat(row["match_date"]), row["kickoff"])
                if not _utc(row["saved"]):
                    raise NotebookError("Missing save time.")
            return tuple(Fixture(r["id"], r["revision"], r["home"], r["away"], r["season"],
                                 date.fromisoformat(r["match_date"]), r["kickoff"], r["saved"],
                                 r["observation_count"], r["last_capture"]) for r in rows)
        except (ValueError, TypeError) as exc:
            raise NotebookError("The notebook contains an invalid fixture record.") from exc

    def save_fixture(self, *, home, away, season, match_date, kickoff="", previous: Fixture | None = None) -> str:
        values = _fixture_values(home, away, season, match_date, kickoff)
        with self._db(write=True) as db:
            if previous is None:
                existing = db.execute("""SELECT id FROM fixtures
                    WHERE active = 1 AND (home, away, season, match_date) = (?, ?, ?, ?)""", values[:4]).fetchone()
                if existing:
                    return existing["id"]
                identity, revision = uuid4().hex, 1
            else:
                identity, revision = previous.id, previous.revision + 1
                changed = db.execute("UPDATE fixtures SET active = 0 WHERE id = ? AND revision = ? AND active = 1",
                                     (identity, previous.revision)).rowcount
                if changed != 1:
                    raise NotebookError("This fixture was corrected elsewhere. Reload it before saving.")
            db.execute("INSERT INTO fixtures VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)",
                       (identity, revision, *values, _now()))
            return identity

    def save_observation(self, fixture: Fixture, *, bookmaker, side, line, odds, source="",
                         claimed="", invented=False, replaces: int | None = None) -> int:
        bookmaker, side, line, quarters, odds, exact, source, claimed, invented = _market_values(
            bookmaker, side, line, odds, source, claimed, invented)
        captured = _now()
        if claimed and claimed > captured:
            raise NotebookError("Claimed observation time cannot be later than local capture.")
        with self._db(write=True) as db:
            if not db.execute("SELECT 1 FROM fixtures WHERE id = ? AND revision = ? AND active = 1",
                              (fixture.id, fixture.revision)).fetchone():
                raise NotebookError("Select the current fixture revision before saving.")
            existing = db.execute("""
                SELECT id FROM observations WHERE fixture_id = ? AND revision = ?
                AND bookmaker = ? COLLATE NOCASE AND side = ? AND quarters = ? AND exact_odds = ?
                AND source = ? AND claimed = ? AND invented = ? AND replaces IS ?
                AND NOT EXISTS (SELECT 1 FROM observations next WHERE next.replaces = observations.id)
            """, (fixture.id, fixture.revision, bookmaker, side, quarters, exact, source,
                  claimed, invented, replaces)).fetchone()
            if existing:
                return existing["id"]
            if replaces is not None and not db.execute("""
                SELECT 1 FROM observations WHERE id = ? AND fixture_id = ? AND revision = ?
                AND NOT EXISTS (SELECT 1 FROM observations next WHERE next.replaces = observations.id)
            """, (replaces, fixture.id, fixture.revision)).fetchone():
                raise NotebookError("Choose an unsuperseded observation from this revision.")
            return db.execute("""
                INSERT INTO observations (fixture_id, revision, bookmaker, side, raw_line,
                    quarters, raw_odds, exact_odds, source, claimed, captured, invented, replaces)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (fixture.id, fixture.revision, bookmaker, side, line, quarters, odds, exact,
                  source, claimed, captured, invented, replaces)).lastrowid

    def observations(self, fixture_id: str) -> tuple[dict, ...]:
        with self._db() as db:
            rows = db.execute("""
                SELECT o.*, f.kickoff, f.home, f.away, f.match_date,
                    EXISTS(SELECT 1 FROM observations next WHERE next.replaces = o.id) AS superseded
                FROM observations o JOIN fixtures f ON (f.id, f.revision) = (o.fixture_id, o.revision)
                WHERE o.fixture_id = ? ORDER BY o.id DESC
            """, (fixture_id,)).fetchall()
        result = []
        try:
            for row in rows:
                if row["invented"] not in (0, 1):
                    raise NotebookError("Invalid demonstration label.")
                values = _market_values(row["bookmaker"], row["side"], row["raw_line"],
                                        row["raw_odds"], row["source"], row["claimed"], bool(row["invented"]))
                if (values[3], values[5]) != (row["quarters"], row["exact_odds"]):
                    raise NotebookError("Stored odds do not match the raw quote.")
                kickoff, claimed, captured = (_utc(row[key]) for key in ("kickoff", "claimed", "captured"))
                if not captured or claimed > captured:
                    raise NotebookError("Invalid stored observation time.")
                timing = "TIMING_UNKNOWN"
                if kickoff:
                    timing = ("LATE_FOR_PREMATCH_RESEARCH" if max(captured, claimed) >= kickoff
                              else "BEFORE_CLAIMED_KICKOFF_UNVERIFIED")
                result.append(dict(row, timing=timing, assurance=ODDS_STATUS, format="MANUAL_UNVERIFIED"))
        except (ValueError, TypeError) as exc:
            raise NotebookError("The notebook contains an invalid observation record.") from exc
        return tuple(result)
