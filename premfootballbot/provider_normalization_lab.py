"""C1-A synthetic-only, offline fixture/1X2/AH normalization laboratory.

This is NOT an adapter for any real bookmaker or provider. It only accepts
invented `toy:` identifiers and example.invalid source URLs; it produces no
C0 evidence, cleared licensing, forecasts, real-data fits, scoring or bets.
All timestamps are operator-supplied and unverified. No network, file or clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

VERSION = "phase-c1a-synthetic-normalization-v1"
STATUS = "INVENTED_SYNTHETIC_TEST_ONLY"
ASSURANCE = "SYNTHETIC_LOCAL_UNVERIFIED"
DOMAIN = b"PremFootballBot C1A synthetic normalization v1\0"
MAX_QUOTES = 3
MAX_STALENESS_SECONDS = 900
_MAX_BYTES = 32768
_ID = re.compile(r"toy:[a-z0-9][a-z0-9_-]{0,70}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,12})?\Z")
_SIGNED_QUARTER = re.compile(r"[+-]?(?:0|[1-9][0-9]*)(?:\.(?:00?|25|50?|75))?\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z")


class NormalizationError(ValueError):
    """Fail-closed structured denial with one stable, machine-readable code."""
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


def _need(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise NormalizationError(code, message)


def _fields(value: Any, required: set[str], optional: set[str] = frozenset()) -> dict:
    _need(type(value) is dict, "INPUT_TYPE", "Expected plain object")
    _need(required <= set(value), "MISSING_FIELD", "Required fields are missing")
    _need(set(value) <= required | optional, "FORBIDDEN_FIELD", "Unexpected fields (possibly results or future information)")
    return value


def _toy(value: Any, field: str) -> str:
    _need(type(value) is str and _ID.fullmatch(value) is not None,
          "NON_SYNTHETIC_ID", f"{field} must be a lowercase toy: identity")
    return value


def _utc(value: Any, field: str) -> str:
    _need(type(value) is str and _UTC.fullmatch(value) is not None,
          "INVALID_UTC", f"{field} must be exact UTC text ending Z")
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NormalizationError("INVALID_UTC", f"Invalid {field}") from exc
    _need(ts.utcoffset().total_seconds() == 0, "INVALID_UTC", f"Invalid {field}")
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _digest(value: Any) -> str:
    _need(type(value) is str and _DIGEST.fullmatch(value) is not None,
          "INVALID_DIGEST", "Need a lowercase SHA-256 label")
    return value


def _url(value: Any) -> str:
    _need(type(value) is str and 1 <= len(value) <= 300,
          "SOURCE_URL", "Bounded invented source URL required")
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise NormalizationError("SOURCE_URL", "Malformed invented source URL") from exc
    _need(parts.scheme == "https" and parts.netloc == "example.invalid" and
          bool(parts.path) and not parts.username and not parts.password and
          not parts.query and not parts.fragment, "SOURCE_URL",
          "Only https://example.invalid/... without credentials or query is supported")
    return value


def _alias(value: Any) -> str:
    _need(type(value) is str and 1 <= len(value) <= 90 and value == value.strip() and
          value.isascii() and value.isprintable() and "  " not in value,
          "AMBIGUOUS_ALIAS", "Alias must be explicit, printable ASCII without boundary spaces")
    return value.casefold()


def _aliases(values: Mapping[str, str]) -> dict[str, str]:
    _need(type(values) is dict and 2 <= len(values) <= 60,
          "AMBIGUOUS_ALIAS", "Explicit bounded provider-name to canonical-ID map required")
    normalized: dict[str, str] = {}
    for raw, canonical in values.items():
        key = _alias(raw)
        _need(key not in normalized, "AMBIGUOUS_ALIAS", "Case-insensitive duplicate alias")
        normalized[key] = _toy(canonical, "canonical_team")
    return normalized


def _rights(raw: dict) -> str:
    status = raw.get("rights_status", "UNKNOWN")
    _need(type(status) is str and status in ("UNKNOWN", "BLOCKED", "CLEARED"),
          "RIGHTS_UNKNOWN", "Invalid rights status")
    _need(status != "BLOCKED", "RIGHTS_BLOCKED", "Blocked source cannot be used")
    _need(status != "CLEARED", "RIGHTS_UNVERIFIED", "Synthetic lab cannot certify rights")
    return status


def _canon(obj: dict) -> bytes:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=True, allow_nan=False,
                     separators=(",", ":")).encode("ascii")
    _need(len(raw) <= _MAX_BYTES, "OVERSIZE", "Bounded synthetic payload only")
    return raw


@dataclass(frozen=True, slots=True)
class InventedFixture:
    canonical_bytes: bytes
    sha256: str
    fixture_id: str
    kickoff_utc: str


@dataclass(frozen=True, slots=True)
class InventedMarket:
    canonical_bytes: bytes
    sha256: str
    fixture_sha256: str
    market: str


def _reject_nonfinite_constant(token: str) -> None:
    """JSON's NaN/Infinity extensions are never valid frozen fixture data."""
    raise ValueError(f"Nonfinite JSON constant: {token}")


def _reject_fixture_number(token: str) -> None:
    """Frozen fixture fields are strings; reject all JSON number tokens exactly.

    Default json.parse_float would convert a valid number such as 1e999 to
    float infinity. Refusing number tokens at the parser boundary prevents
    ambient floating-point overflow before canonicalization or schema checks.
    """
    raise ValueError(f"Numeric JSON token prohibited in a frozen fixture: {token}")


def _decimal_text(value: Decimal) -> str:
    """Format an exact input decimal; never call context-sensitive normalize()."""
    raw = format(value, "f")
    return raw.rstrip("0").rstrip(".") if "." in raw else raw


def _seal(payload: dict) -> tuple[bytes, str]:
    raw = _canon(payload)
    return raw, hashlib.sha256(DOMAIN + raw).hexdigest()


def normalize_fixture(raw: dict, *, team_aliases: Mapping[str, str]) -> InventedFixture:
    """Map invented scheduled fixture; all evidence remains self-reported."""
    p = _fields(raw, {"record_kind", "fixture_id", "league", "home", "away",
                      "kickoff_utc", "status", "provider", "source_url",
                      "source_content_sha256", "locally_observed_at_utc"},
                {"rights_status"})
    _need(p["record_kind"] == STATUS and p["league"] == "EPL", "SCOPE", "Invented EPL only")
    _need(p["status"] == "SCHEDULED", "UNSUPPORTED_STATUS", "Only scheduled invented fixtures can be normalized")
    fid = _toy(p["fixture_id"], "fixture_id")
    provider = _toy(p["provider"], "provider")
    aliases = _aliases(team_aliases)
    home = aliases.get(_alias(p["home"]))
    away = aliases.get(_alias(p["away"]))
    _need(home is not None and away is not None and home != away,
          "AMBIGUOUS_FIXTURE", "Missing, duplicate, or reversed fixture identity")
    kickoff = _utc(p["kickoff_utc"], "kickoff_utc")
    observed = _utc(p["locally_observed_at_utc"], "locally_observed_at_utc")
    _need(observed < kickoff, "FUTURE_INFORMATION", "Fixture acquired after kickoff")
    payload = {"protocol": VERSION, "record_kind": STATUS, "assurance": ASSURANCE,
               "fixture_id": fid, "league": "EPL", "home": home, "away": away,
               "kickoff_utc": kickoff, "status": "SCHEDULED", "provider": provider,
               "source_url": _url(p["source_url"]),
               "source_content_sha256": _digest(p["source_content_sha256"]),
               "locally_observed_at_utc": observed, "rights_status": _rights(p),
               "rights_assurance": "UNVERIFIED_CLAIM_ONLY"}
    encoded, sha = _seal(payload)
    return InventedFixture(encoded, sha, fid, kickoff)


def _decimal(raw: Any, name: str, *, price: bool) -> Decimal:
    _need(type(raw) is str and len(raw) <= 24, "PRICE_FORMAT" if price else "HANDICAP_LINE",
          f"{name} needs exact ASCII decimal text")
    expression = _DECIMAL if price else _SIGNED_QUARTER
    _need(expression.fullmatch(raw) is not None, "PRICE_FORMAT" if price else "HANDICAP_LINE",
          f"Invalid {name} decimal format")
    try:
        d = Decimal(raw)
    except InvalidOperation as exc:
        raise NormalizationError("PRICE_FORMAT" if price else "HANDICAP_LINE", "Malformed decimal") from exc
    # Fraction(Decimal) and its integer operations are independent of the
    # caller's thread-local decimal precision, rounding and trap settings.
    exact = Fraction(d)
    if price:
        _need(Fraction(1) < exact <= Fraction(10000), "PRICE_FORMAT",
              "Gross decimal prices must exceed 1")
    else:
        quarter = exact * 4
        _need(abs(exact) <= 20 and quarter.denominator == 1,
              "HANDICAP_LINE", "Signed quarter-goal line required within +/-20")
    if not price:
        _need(not (d == 0 and raw.startswith("-")), "HANDICAP_LINE", "Negative zero is ambiguous")
    return d


def _fixture_verified(fixture: InventedFixture) -> dict:
    _need(type(fixture) is InventedFixture and type(fixture.canonical_bytes) is bytes,
          "FORGED_FIXTURE", "Frozen invented fixture required")
    _need(len(fixture.canonical_bytes) <= _MAX_BYTES,
          "FORGED_FIXTURE", "Oversized frozen fixture")
    try:
        p = json.loads(fixture.canonical_bytes, parse_constant=_reject_nonfinite_constant,
                       parse_int=_reject_fixture_number, parse_float=_reject_fixture_number)
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        # A small JSON document can still have thousands of nested containers.
        # Decoding recursion is malformed fixture input, not an uncoded runtime error.
        raise NormalizationError("FORGED_FIXTURE", "Invalid fixture bytes") from exc
    _need(type(p) is dict and set(p) == {
          "protocol", "record_kind", "assurance", "fixture_id", "league", "home",
          "away", "kickoff_utc", "status", "provider", "source_url",
          "source_content_sha256", "locally_observed_at_utc", "rights_status",
          "rights_assurance"}, "FORGED_FIXTURE", "Unexpected fixture schema")
    _need(p["protocol"] == VERSION and
          p["fixture_id"] == _toy(p["fixture_id"], "fixture_id") and
          p["provider"] == _toy(p["provider"], "provider") and
          p["home"] == _toy(p["home"], "home") and
          p["away"] == _toy(p["away"], "away") and
          p["home"] != p["away"] and
          _url(p["source_url"]) == p["source_url"] and
          _digest(p["source_content_sha256"]) == p["source_content_sha256"] and
          _utc(p["locally_observed_at_utc"], "locally_observed_at_utc") <
             _utc(p["kickoff_utc"], "kickoff_utc"),
          "FORGED_FIXTURE", "Fixture content is not synthetic or chronologically valid")
    try:
        canonical = _canon(p)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        # Valid parsing does not prove serialization is safe; high nesting can
        # overflow the encoder on a different Python runtime/recursion setting.
        raise NormalizationError("FORGED_FIXTURE", "Invalid canonical fixture") from exc
    _need(canonical == fixture.canonical_bytes and
          hashlib.sha256(DOMAIN + fixture.canonical_bytes).hexdigest() == fixture.sha256 and
          p.get("record_kind") == STATUS and p.get("assurance") == ASSURANCE and
          p.get("rights_status") == "UNKNOWN" and
          p.get("rights_assurance") == "UNVERIFIED_CLAIM_ONLY" and
          p.get("fixture_id") == fixture.fixture_id and
          p.get("kickoff_utc") == fixture.kickoff_utc and
          p.get("status") == "SCHEDULED" and p.get("league") == "EPL",
          "FORGED_FIXTURE", "Bad fixture seal or forged assurance")
    return p


def normalize_market(raw: dict, *, fixture: InventedFixture,
                     outcome_map: Mapping[str, str],
                     max_staleness_seconds: int = MAX_STALENESS_SECONDS) -> InventedMarket:
    """Normalize complete 1X2 or AH market for invented scheduled fixture only.

    Explicit outcome_map is mandatory; '1' is never implicitly HOME.
    These self-reported time fields are not proof of prospective publication.
    """
    f = _fixture_verified(fixture)
    p = _fields(raw, {"record_kind", "fixture_id", "home", "away", "kickoff_utc",
                      "provider", "bookmaker", "snapshot_id", "market", "period",
                      "price_format", "quotes", "source_url", "source_content_sha256",
                      "provider_ingested_at_utc", "bookmaker_claimed_updated_at_utc",
                      "locally_acquired_at_utc", "snapshot_captured_at_utc",
                      "independent_observed_at_utc", "cutoff_utc"}, {"rights_status"})
    _need(p["record_kind"] == STATUS and p["market"] in ("1X2", "AH") and
          p["period"] == "REGULATION_90", "SCOPE", "Only invented EPL regulation-90 1X2/AH")
    _need(p["price_format"] == "DECIMAL", "PRICE_FORMAT", "Explicit exact DECIMAL price format required")
    _need(type(max_staleness_seconds) is int and 1 <= max_staleness_seconds <= MAX_STALENESS_SECONDS,
          "STALE_SNAPSHOT", "Staleness ceiling must be <= 900 seconds")
    _need(p["fixture_id"] == f["fixture_id"] and p["home"] == f["home"]
          and p["away"] == f["away"] and
          _utc(p["kickoff_utc"], "kickoff_utc") == f["kickoff_utc"] and
          p["provider"] == f["provider"],
          "FIXTURE_MISMATCH", "Exact invented fixture binding required; never swap HOME and AWAY")
    bookmaker = _toy(p["bookmaker"], "bookmaker")
    snapshot = _toy(p["snapshot_id"], "snapshot_id")
    url = _url(p["source_url"])
    digest = _digest(p["source_content_sha256"])
    rights = _rights(p)
    observed = _utc(p["provider_ingested_at_utc"], "provider_ingested_at_utc")
    bookmaker_at = None if p["bookmaker_claimed_updated_at_utc"] is None else _utc(
        p["bookmaker_claimed_updated_at_utc"], "bookmaker_claimed_updated_at_utc")
    acquired = _utc(p["locally_acquired_at_utc"], "locally_acquired_at_utc")
    captured = _utc(p["snapshot_captured_at_utc"], "snapshot_captured_at_utc")
    cutoff = _utc(p["cutoff_utc"], "cutoff_utc")
    independently_observed = None if p["independent_observed_at_utc"] is None else _utc(
        p["independent_observed_at_utc"], "independent_observed_at_utc")
    _need(f["locally_observed_at_utc"] <= captured <= cutoff < f["kickoff_utc"] and
          observed <= acquired <= captured and
          (bookmaker_at is None or bookmaker_at <= observed) and
          (independently_observed is None or independently_observed <= captured),
          "FUTURE_INFORMATION", "Time ordering violates pre-match capture/cutoff")
    _need(0 <= (_timestamp(captured) - _timestamp(observed)).total_seconds() <= max_staleness_seconds,
          "STALE_SNAPSHOT", "Provider observation is too stale for the requested capture")
    if bookmaker_at is not None:
        _need(0 <= (_timestamp(captured) - _timestamp(bookmaker_at)).total_seconds()
              <= max_staleness_seconds, "STALE_SNAPSHOT",
              "Claimed bookmaker update is too stale for the requested capture")
    _need(type(outcome_map) is dict and 2 <= len(outcome_map) <= 3,
          "AMBIGUOUS_OUTCOME", "Explicit outcome ID to HOME/DRAW/AWAY mapping required")
    mapping: dict[str, str] = {}
    for label, selection in outcome_map.items():
        _toy(label, "outcome_id")
        _need(type(selection) is str and selection in ("HOME", "DRAW", "AWAY")
              and selection not in mapping.values(), "AMBIGUOUS_OUTCOME", "Duplicate/invalid outcome mapping")
        mapping[label] = selection
    needed = {"HOME", "DRAW", "AWAY"} if p["market"] == "1X2" else {"HOME", "AWAY"}
    _need(set(mapping.values()) == needed, "AMBIGUOUS_OUTCOME", "Full exact market mapping required")
    q = p["quotes"]
    _need(type(q) is list and len(q) == len(needed) <= MAX_QUOTES,
          "INCOMPLETE_MARKET", "Both AH sides or all 1X2 selections required")
    prices: dict[str, dict] = {}
    for quote in q:
        quote = _fields(quote, {"outcome_id", "line", "price"})
        outcome_id = _toy(quote["outcome_id"], "outcome_id")
        selection = mapping.get(outcome_id)
        _need(selection is not None and selection not in prices,
              "AMBIGUOUS_OUTCOME", "Missing, duplicate or unmapped selection")
        price = _decimal(quote["price"], "price", price=True)
        line_q = None
        if p["market"] == "AH":
            line = _decimal(quote["line"], "line", price=False)
            line_q = int(Fraction(line) * 4)
        else:
            _need(quote["line"] is None, "HANDICAP_LINE", "1X2 does not carry a handicap")
        prices[selection] = {"selection": selection, "line_q": line_q,
                             "decimal_price": _decimal_text(price)}
    _need(set(prices) == needed, "INCOMPLETE_MARKET", "Exact selection set required")
    if p["market"] == "AH":
        _need(prices["HOME"]["line_q"] == -prices["AWAY"]["line_q"],
              "HANDICAP_SIGN", "AH HOME and AWAY lines must be explicit opposites")
    payload = {"protocol": VERSION, "record_kind": STATUS, "assurance": ASSURANCE,
               "fixture_sha256": fixture.sha256, "fixture_id": fixture.fixture_id,
               "home": f["home"], "away": f["away"], "kickoff_utc": fixture.kickoff_utc,
               "provider": f["provider"], "bookmaker": bookmaker, "snapshot_id": snapshot,
               "market": p["market"], "period": "REGULATION_90",
               "price_format": "DECIMAL", "quotes": [prices[k] for k in sorted(prices)],
               "source_url": url, "source_content_sha256": digest,
               "rights_status": rights, "rights_assurance": "UNVERIFIED_CLAIM_ONLY",
               "provider_ingested_at_utc": observed,
               "bookmaker_claimed_updated_at_utc": bookmaker_at,
               "locally_acquired_at_utc": acquired,
               "snapshot_captured_at_utc": captured,
               "independent_observed_at_utc": independently_observed,
               "independent_timestamp_assurance": "UNVERIFIED_CLAIM_ONLY",
               "cutoff_utc": cutoff, "coverage": "SYNTHETIC_NO_FORECAST_OR_MODEL"}
    encoded, sha = _seal(payload)
    return InventedMarket(encoded, sha, fixture.sha256, p["market"])


def normalize_fixture_set(raws: tuple[dict, ...], *,
                          team_aliases: Mapping[str, str]) -> tuple[InventedFixture, ...]:
    """Require unambiguous invented fixture identities across a small batch."""
    _need(type(raws) is tuple and 1 <= len(raws) <= 20,
          "INPUT_TYPE", "One to twenty invented fixtures required")
    fixtures = tuple(normalize_fixture(r, team_aliases=team_aliases) for r in raws)
    ids, matchups = set(), set()
    for fixture in fixtures:
        p = _fixture_verified(fixture)
        key = (p["kickoff_utc"], frozenset((p["home"], p["away"])))
        _need(fixture.fixture_id not in ids and key not in matchups,
              "DUPLICATE_FIXTURE", "Fixture ID or kickoff/team pair reused")
        ids.add(fixture.fixture_id)
        matchups.add(key)
    return fixtures
