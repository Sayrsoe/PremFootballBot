"""Offline C1-C1 vendor-*like* toy 1X2 / Asian Handicap schema experiments.

Not a real provider parser, ingestion client, C0 bridge or model. Rights CLEARED
here represents SIMULATED permission for toy data only, never actual licensing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import fixture_crosswalk as f
from . import provider_contracts as c
from . import provider_quarantine as q


@dataclass(frozen=True, slots=True)
class MarketProfile:
    canonical_bytes: bytes
    sha256: str
    provider: str
    bookmaker: str
    market: str
    outcome_map: tuple[tuple[str, str], ...]


def make_market_profile(*, provider: str, bookmaker: str,
                        market: str, market_id: str, period: str,
                        outcomes: dict[str, str], reviewer: str) -> MarketProfile:
    for name, value in (("provider", provider), ("bookmaker", bookmaker),
                        ("market_id", market_id), ("reviewer", reviewer)):
        c.toy(value, name)
    c.need(market in ("1X2", "AH") and period == "REGULATION_90",
           "MARKET_SCOPE", "Only invented FT90 1X2 or AH")
    c.need(type(outcomes) is dict and len(outcomes) == (3 if market == "1X2" else 2),
           "AMBIGUOUS_OUTCOME", "Provide every distinct outcome explicitly")
    for vendor_id in outcomes:
        c.toy(vendor_id, "vendor outcome")
    expected = {"HOME", "DRAW", "AWAY"} if market == "1X2" else {"HOME", "AWAY"}
    c.need(all(type(v) is str for v in outcomes.values()) and
           set(outcomes.values()) == expected and len(outcomes.values()) == len(expected),
           "AMBIGUOUS_OUTCOME", "Complete, unique selection mapping required")
    ordered = tuple(sorted(outcomes.items()))
    body = dict(protocol=c.VERSION, assurance=c.ASSURANCE, kind="MARKET_PROFILE",
                provider=provider, bookmaker=bookmaker, market=market,
                market_id=market_id, period=period, reviewer=reviewer,
                outcome_map=[{"id": k, "selection": v} for k, v in ordered])
    raw, sha = c.seal(body)
    return MarketProfile(raw, sha, provider, bookmaker, market, ordered)


def verify_market_profile(profile: MarketProfile) -> dict:
    c.need(type(profile) is MarketProfile and type(profile.canonical_bytes) is bytes,
           "FORGED_PROFILE", "Market profile required")
    p = c.decode_invented_json(profile.canonical_bytes)
    c.need(set(p) == {"protocol", "assurance", "kind", "provider", "bookmaker",
           "market", "market_id", "period", "reviewer", "outcome_map"},
           "FORGED_PROFILE", "Unknown market profile fields")
    c.need(p["protocol"] == c.VERSION and p["assurance"] == c.ASSURANCE and
           p["kind"] == "MARKET_PROFILE" and
           c.canonical(p) == profile.canonical_bytes and c.seal(p)[1] == profile.sha256,
           "FORGED_PROFILE", "Profile seal or assurance mismatch")
    c.toy(p["provider"], "provider")
    c.toy(p["bookmaker"], "bookmaker")
    c.toy(p["market_id"], "market_id")
    c.toy(p["reviewer"], "reviewer")
    c.need(p["market"] in ("1X2", "AH") and p["period"] == "REGULATION_90",
           "MARKET_SCOPE", "Unsupported profile market")
    outcomes = p["outcome_map"]
    c.need(type(outcomes) is list and len(outcomes) == (3 if p["market"] == "1X2" else 2),
           "AMBIGUOUS_OUTCOME", "Malformed profile outcome mapping")
    mapped = {}
    for row in outcomes:
        c.fields(row, {"id", "selection"})
        k = c.toy(row["id"], "outcome_id")
        c.need(k not in mapped and type(row["selection"]) is str,
               "AMBIGUOUS_OUTCOME", "Duplicate or malformed outcome")
        mapped[k] = row["selection"]
    expected = {"HOME", "DRAW", "AWAY"} if p["market"] == "1X2" else {"HOME", "AWAY"}
    c.need(set(mapped.values()) == expected and
           list(mapped) == sorted(mapped), "AMBIGUOUS_OUTCOME", "Incomplete or unsorted mapping")
    c.need(p["provider"] == profile.provider and p["bookmaker"] == profile.bookmaker and
           p["market"] == profile.market and tuple(mapped.items()) == profile.outcome_map,
           "FORGED_PROFILE", "Profile dataclass differs from source seal")
    return p


@dataclass(frozen=True, slots=True)
class NormalizedToyMarket:
    canonical_bytes: bytes
    sha256: str
    fixture_id: str
    source_sha256: str
    rights_sha256: str
    assurance: str = c.ASSURANCE


def normalize_invented_market(raw_bytes: bytes, *, source: c.SourceEnvelope,
                              profile: MarketProfile, fixture: f.FixtureRevision,
                              rights_chain: tuple[q.RightsDecision, ...],
                              pinned_rights_head: str) -> NormalizedToyMarket:
    """Fail-closed pure transformation. The output is NEVER C0-eligible."""
    c.need(type(fixture) is f.FixtureRevision, "FIXTURE_TYPE", "Toy fixture only")
    p = c.decode_invented_json(raw_bytes)
    envelope = c.verify_source_envelope(source, raw_bytes)
    market = verify_market_profile(profile)
    c.need(source.profile_sha256 == profile.sha256 and
           source.rights_sha256 == pinned_rights_head,
           "SOURCE_MISMATCH", "Pinned profile or rights identity mismatch")
    c.need(fixture.status == "TIMED" and fixture.season == "2026-27",
           "FIXTURE_STATUS", "Only confirmed invented fixture revisions")
    c.need(fixture.provider_fixture_id == source.fixture_id and
           fixture.namespace == source.provider,
           "FIXTURE_IDENTITY", "Fixture/source namespace mismatch")
    c.need(type(fixture.revision) is str and fixture.revision.isascii() and
           fixture.revision.isdecimal() and 1 <= int(fixture.revision) <= 999999,
           "FIXTURE_REVISION", "Invalid schedule revision")
    c.need(c.utc(fixture.kickoff_utc) is not None, "INVALID_UTC", "Missing kickoff")
    q.evaluate_rights(chain=rights_chain, expected_head=pinned_rights_head,
                      subject=source.provider, purpose="MARKET_QUALIFICATION",
                      as_of_utc=source.acquisition_utc)
    required = {"protocol", "assurance", "provider", "fixture_id", "fixture_revision",
                "bookmaker", "market", "market_id", "period", "snapshot_id", "kickoff_utc",
                "locally_acquired_at_utc", "snapshot_captured_at_utc", "source_observed_at_utc",
                "snapshot_reviewed_at_utc", "cutoff_utc", "provider_updated_claim_utc",
                "bookmaker_published_claim_utc", "historical_created_claim_utc", "quotes"}
    c.fields(p, required)
    c.need(p["protocol"] == c.VERSION and p["assurance"] == c.ASSURANCE,
           "NON_SYNTHETIC_SOURCE", "Only invented payloads supported")
    for name in ("provider", "fixture_id", "bookmaker", "market_id", "snapshot_id"):
        c.toy(p[name], name)
    c.need(p["provider"] == source.provider == profile.provider and
           p["fixture_id"] == source.fixture_id and
           p["bookmaker"] == profile.bookmaker and p["bookmaker"] != p["provider"] and
           p["market"] == profile.market == market["market"] and
           p["market_id"] == market["market_id"] and
           p["period"] == market["period"] and p["period"] == "REGULATION_90",
           "MARKET_SCOPE", "Bookmaker/market/period/profile mismatch")
    c.need(p["fixture_revision"] == fixture.revision and
           p["kickoff_utc"] == fixture.kickoff_utc,
           "FIXTURE_REVISION", "Scheduled kickoff/revision mismatch")
    times = {name: c.utc(p[name], name) for name in (
        "locally_acquired_at_utc", "snapshot_captured_at_utc",
        "source_observed_at_utc", "snapshot_reviewed_at_utc", "cutoff_utc",
        "kickoff_utc")}
    c.need(p["locally_acquired_at_utc"] == source.acquisition_utc,
           "SOURCE_MISMATCH", "Acquisition and source record disagree")
    c.need(times["locally_acquired_at_utc"] <= times["snapshot_captured_at_utc"] <=
           times["snapshot_reviewed_at_utc"] <= times["cutoff_utc"] < times["kickoff_utc"],
           "TEMPORAL_LEAKAGE", "Acquisition, capture, review, cutoff, kickoff ordering")
    c.need(times["source_observed_at_utc"] <= times["snapshot_captured_at_utc"],
           "TEMPORAL_LEAKAGE", "Source observation cannot follow capture")
    claims = {}
    for name in ("provider_updated_claim_utc", "bookmaker_published_claim_utc",
                 "historical_created_claim_utc"):
        claim = p[name]
        c.need(type(claim) is str, "INVALID_UTC", "Timestamp claim must be string")
        claims[name] = None if claim == "" else c.utc(claim, name)
        c.need(claims[name] is None or claims[name] <= times["locally_acquired_at_utc"],
               "TEMPORAL_LEAKAGE", "Provider/publication claim after acquisition")
    rows = p["quotes"]
    expected = {"HOME", "DRAW", "AWAY"} if profile.market == "1X2" else {"HOME", "AWAY"}
    c.need(type(rows) is list and len(rows) == len(expected),
           "INCOMPLETE_MARKET", "Exactly one side per selection required")
    selection_map = dict(profile.outcome_map)
    seen = set()
    out = []
    for quote in rows:
        c.fields(quote, {"outcome_id", "bookmaker", "market_id", "period",
                         "snapshot_id", "price", "line"})
        outcome = c.toy(quote["outcome_id"], "outcome_id")
        selection = selection_map.get(outcome)
        c.need(selection in expected and selection not in seen,
               "AMBIGUOUS_OUTCOME", "Unknown or repeated selection")
        seen.add(selection)
        c.need(quote["bookmaker"] == profile.bookmaker and
               quote["market_id"] == market["market_id"] and
               quote["period"] == "REGULATION_90" and
               quote["snapshot_id"] == p["snapshot_id"],
               "MIXED_SNAPSHOT", "Sides must use identical bookmaker/period/snapshot")
        price = c.exact_price(quote["price"])
        if profile.market == "AH":
            line_q = c.quarter_units(quote["line"])
        else:
            c.need(quote["line"] is None, "HANDICAP_LINE", "1X2 must have null line")
            line_q = None
        out.append(dict(selection=selection, decimal_price=price, line_q=(str(line_q) if line_q is not None else "")))
    c.need(seen == expected, "INCOMPLETE_MARKET", "Missing selection")
    out.sort(key=lambda x: x["selection"])
    if profile.market == "AH":
        lines = {x["selection"]: int(x["line_q"]) for x in out}
        c.need(lines["HOME"] == -lines["AWAY"],
               "HANDICAP_SIGN", "Paired AH signs must oppose")
    normalized = dict(protocol=c.VERSION, assurance=c.ASSURANCE,
                      eligibility="SIMULATED_ONLY_NOT_C0_OR_MODEL",
                      fixture_id=fixture.canonical_fixture_id,
                      fixture_revision=fixture.revision,
                      source_sha256=source.sha256, raw_sha256=source.raw_sha256,
                      rights_sha256=pinned_rights_head, profile_sha256=profile.sha256,
                      provider=profile.provider, bookmaker=profile.bookmaker,
                      market=profile.market, period="REGULATION_90", snapshot_id=p["snapshot_id"],
                      kickoff_utc=fixture.kickoff_utc, cutoff_utc=p["cutoff_utc"],
                      locally_acquired_at_utc=p["locally_acquired_at_utc"],
                      snapshot_captured_at_utc=p["snapshot_captured_at_utc"],
                      source_observed_at_utc=p["source_observed_at_utc"],
                      snapshot_reviewed_at_utc=p["snapshot_reviewed_at_utc"],
                      provider_updated_claim_utc=p["provider_updated_claim_utc"],
                      bookmaker_published_claim_utc=p["bookmaker_published_claim_utc"],
                      historical_created_claim_utc=p["historical_created_claim_utc"],
                      quotes=out)
    canonical, sha = c.seal(normalized)
    return NormalizedToyMarket(canonical, sha, fixture.canonical_fixture_id,
                               source.sha256, pinned_rights_head)
