"""C1-C1 toy-only, explicit fixture/team identity and schedule revision laboratory."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import provider_contracts as c


@dataclass(frozen=True, slots=True)
class TeamCrosswalk:
    namespace: str
    provider_team_id: str
    canonical_team_id: str
    season: str
    reviewer: str


def make_team_crosswalk(*, namespace: str, provider_team_id: str,
                        canonical_team_id: str, season: str, reviewer: str) -> TeamCrosswalk:
    for label, value in (("namespace", namespace), ("provider team", provider_team_id),
                         ("canonical team", canonical_team_id), ("reviewer", reviewer)):
        c.toy(value, label)
    c.need(season == "2026-27", "FIXTURE_SCOPE", "Only invented 2026-27 EPL fixtures")
    return TeamCrosswalk(namespace, provider_team_id, canonical_team_id, season, reviewer)


@dataclass(frozen=True, slots=True)
class FixtureRevision:
    namespace: str
    provider_fixture_id: str
    canonical_fixture_id: str
    home_team_id: str
    away_team_id: str
    kickoff_utc: str
    status: str
    revision: str
    season: str
    source_sha256: str


def make_fixture_revision(*, namespace: str, provider_fixture_id: str,
                          canonical_fixture_id: str, home_team_id: str,
                          away_team_id: str, kickoff_utc: str, status: str,
                          revision: str, season: str, source_sha256: str) -> FixtureRevision:
    for label, value in (("namespace", namespace), ("provider fixture", provider_fixture_id),
                         ("canonical fixture", canonical_fixture_id), ("home", home_team_id),
                         ("away", away_team_id)):
        c.toy(value, label)
    c.need(home_team_id != away_team_id, "FIXTURE_ORIENTATION", "Duplicate team identity")
    c.utc(kickoff_utc, "kickoff_utc")
    c.need(status in ("TIMED", "SCHEDULED", "POSTPONED", "CANCELLED", "ABANDONED", "AWARDED"),
           "FIXTURE_STATUS", "Unqualified fixture status")
    c.need(type(revision) is str and revision.isascii() and revision.isdecimal() and
           len(revision) <= 6 and 1 <= int(revision) <= 999999 and revision[0] != "0",
           "FIXTURE_REVISION", "Positive revision string required")
    c.need(season == "2026-27", "FIXTURE_SCOPE", "Invented EPL 2026-27 only")
    c.digest(source_sha256, "source_sha256")
    return FixtureRevision(namespace, provider_fixture_id, canonical_fixture_id,
                           home_team_id, away_team_id, kickoff_utc, status,
                           revision, season, source_sha256)


def match_fixture_revisions(left: FixtureRevision, right: FixtureRevision,
                            *, team_crosswalks: tuple[TeamCrosswalk, ...]) -> str:
    """Return only a simulated canonical fixture ID; never real-data eligibility.

    Both providers must explicitly map HOME and AWAY and agree on the kickoff,
    schedule revision, fixture identity, season and qualified TIMED status.
    """
    c.need(type(left) is FixtureRevision and type(right) is FixtureRevision,
           "FIXTURE_TYPE", "Invented fixture revisions only")
    for rev in (left, right):
        make_fixture_revision(namespace=rev.namespace,
                              provider_fixture_id=rev.provider_fixture_id,
                              canonical_fixture_id=rev.canonical_fixture_id,
                              home_team_id=rev.home_team_id, away_team_id=rev.away_team_id,
                              kickoff_utc=rev.kickoff_utc, status=rev.status,
                              revision=rev.revision, season=rev.season,
                              source_sha256=rev.source_sha256)
    c.need(left.namespace != right.namespace, "FIXTURE_SCOPE", "Distinct sources required")
    c.need(type(team_crosswalks) is tuple and 4 <= len(team_crosswalks) <= 100 and
           all(type(t) is TeamCrosswalk for t in team_crosswalks),
           "AMBIGUOUS_CROSSWALK", "At least two explicit teams per source required")
    maps = {}
    reverse = {}
    for entry in team_crosswalks:
        make_team_crosswalk(namespace=entry.namespace,provider_team_id=entry.provider_team_id,
                            canonical_team_id=entry.canonical_team_id,season=entry.season,
                            reviewer=entry.reviewer)
        key = (entry.namespace, entry.provider_team_id, entry.season)
        c.need(key not in maps, "AMBIGUOUS_CROSSWALK", "Repeated provider team identity")
        maps[key] = entry.canonical_team_id
        inverse = (entry.namespace, entry.canonical_team_id, entry.season)
        c.need(inverse not in reverse, "AMBIGUOUS_CROSSWALK", "Noninjective team mapping")
        reverse[inverse] = entry.provider_team_id
    c.need(left.status == right.status == "TIMED",
           "FIXTURE_STATUS", "Only confirmed TIMED fixtures can match")
    c.need(left.season == right.season == "2026-27" and
           left.canonical_fixture_id == right.canonical_fixture_id,
           "FIXTURE_IDENTITY", "Fixture/season mismatch")
    c.need(left.revision == right.revision and left.kickoff_utc == right.kickoff_utc,
           "FIXTURE_REVISION", "Kickoff changed or schedule revision mismatch")
    def mapped(f, side):
        return maps.get((f.namespace, side, f.season))
    lh, la = mapped(left, left.home_team_id), mapped(left, left.away_team_id)
    rh, ra = mapped(right, right.home_team_id), mapped(right, right.away_team_id)
    c.need(all(v is not None for v in (lh, la, rh, ra)),
           "AMBIGUOUS_CROSSWALK", "Missing reviewed team identity")
    c.need(lh == rh and la == ra and lh != la,
           "FIXTURE_ORIENTATION", "HOME/AWAY mismatch or ambiguous orientation")
    return left.canonical_fixture_id


def verify_revision_history(history: tuple[FixtureRevision, ...]) -> None:
    """Preserve every schedule change as a new ordered revision."""
    c.need(type(history) is tuple and 1 <= len(history) <= 100,
           "FIXTURE_REVISION", "Bounded revision history required")
    first = history[0]
    c.need(type(first) is FixtureRevision, "FIXTURE_TYPE", "Wrong revision type")
    seen = set()
    last = 0
    previous = None
    for rev in history:
        c.need(type(rev) is FixtureRevision and
               (rev.namespace, rev.provider_fixture_id, rev.canonical_fixture_id,
                rev.home_team_id, rev.away_team_id, rev.season) ==
               (first.namespace, first.provider_fixture_id, first.canonical_fixture_id,
                first.home_team_id, first.away_team_id, first.season),
               "FIXTURE_IDENTITY", "Different fixture in revision history")
        make_fixture_revision(namespace=rev.namespace,
                              provider_fixture_id=rev.provider_fixture_id,
                              canonical_fixture_id=rev.canonical_fixture_id,
                              home_team_id=rev.home_team_id, away_team_id=rev.away_team_id,
                              kickoff_utc=rev.kickoff_utc, status=rev.status,
                              revision=rev.revision, season=rev.season,
                              source_sha256=rev.source_sha256)
        c.need(rev.revision.isascii() and rev.revision.isdecimal() and
               1 <= int(rev.revision) <= 999999 and int(rev.revision) > last and
               rev.revision not in seen,
               "FIXTURE_REVISION", "Revision numbers must strictly increase")
        if previous is not None:
            c.need(rev.kickoff_utc != previous.kickoff_utc or
                   rev.status != previous.status or
                   rev.source_sha256 != previous.source_sha256,
                   "FIXTURE_REVISION", "Duplicate revision without new evidence")
        last = int(rev.revision)
        previous = rev
        seen.add(rev.revision)


@dataclass(frozen=True, slots=True)
class ReviewedFixtureBinding:
    """Sealed, explicitly crosswalk-reviewed *invented* fixture identity.

    The expected SHA must be independently pinned by the caller. Creating a new
    binding by simply hashing forged fixture metadata does NOT grant approval.
    """
    canonical_bytes: bytes
    sha256: str
    provider: str
    provider_fixture_id: str
    canonical_fixture_id: str


def make_reviewed_fixture_binding(*, primary: FixtureRevision,
                                  corroborating: FixtureRevision,
                                  team_crosswalks: tuple[TeamCrosswalk, ...],
                                  reviewer: str) -> ReviewedFixtureBinding:
    c.toy(reviewer, "binding reviewer")
    match_fixture_revisions(primary, corroborating, team_crosswalks=team_crosswalks)
    # Canonical ordered crosswalk rows prevent set-order variation. Replay must
    # re-run the same two-source matching contract, not just trust a hash.
    rows = sorted((asdict(t) for t in team_crosswalks),
                  key=lambda t: (t["namespace"], t["provider_team_id"]))
    content = dict(protocol=c.VERSION, assurance=c.ASSURANCE,
                   kind="REVIEWED_FIXTURE_BINDING", reviewer=reviewer,
                   primary=asdict(primary), corroborating=asdict(corroborating),
                   team_crosswalks=rows)
    raw, sha = c.seal(content)
    return ReviewedFixtureBinding(raw, sha, primary.namespace,
                                  primary.provider_fixture_id,
                                  primary.canonical_fixture_id)


def verify_reviewed_fixture_binding(binding: ReviewedFixtureBinding, *,
                                    expected_sha256: str,
                                    primary: FixtureRevision) -> dict:
    c.digest(expected_sha256, "externally pinned fixture binding")
    c.need(type(binding) is ReviewedFixtureBinding and
           type(binding.canonical_bytes) is bytes,
           "FIXTURE_BINDING", "Expected reviewed fixture binding")
    decoded = c.decode_invented_json(binding.canonical_bytes)
    c.fields(decoded, {"protocol", "assurance", "kind", "reviewer",
                       "primary", "corroborating", "team_crosswalks"})
    c.need(decoded["protocol"] == c.VERSION and
           decoded["assurance"] == c.ASSURANCE and
           decoded["kind"] == "REVIEWED_FIXTURE_BINDING" and
           c.canonical(decoded) == binding.canonical_bytes and
           c.seal(decoded)[1] == binding.sha256 == expected_sha256,
           "FIXTURE_BINDING", "Unpinned or forged binding")
    c.toy(decoded["reviewer"], "binding reviewer")
    names = set(FixtureRevision.__dataclass_fields__)
    c.fields(decoded["primary"], names)
    c.fields(decoded["corroborating"], names)
    left = make_fixture_revision(**decoded["primary"])
    right = make_fixture_revision(**decoded["corroborating"])
    rows = decoded["team_crosswalks"]
    c.need(type(rows) is list and 4 <= len(rows) <= 100,
           "FIXTURE_BINDING", "Incomplete crosswalk")
    names = set(TeamCrosswalk.__dataclass_fields__)
    crosswalks = []
    for row in rows:
        c.fields(row, names)
        crosswalks.append(make_team_crosswalk(**row))
    c.need(rows == sorted(rows, key=lambda t: (t["namespace"], t["provider_team_id"])),
           "FIXTURE_BINDING", "Noncanonical crosswalk order")
    match_fixture_revisions(left, right, team_crosswalks=tuple(crosswalks))
    c.need(type(primary) is FixtureRevision and primary == left and
           binding.provider == left.namespace and
           binding.provider_fixture_id == left.provider_fixture_id and
           binding.canonical_fixture_id == left.canonical_fixture_id,
           "FIXTURE_BINDING", "Market fixture differs from externally reviewed identity")
    return decoded
