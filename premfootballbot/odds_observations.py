"""Pure offline LOCAL_ONLY odds records. Hashes are integrity, not source proof."""
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import re

from . import prospective_evidence as pe

PROTOCOL = "pmb-odds-observation/v1"


class OddsError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise OddsError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf8")


def fields(value, required, optional=()):
    need(type(value) is dict and set(required) <= set(value)
         and set(value) <= set(required) | set(optional), "Unexpected/missing fields")


def price(raw: str, price_format: str) -> Fraction:
    """Exact decimal gross return per unit; never infer the notation."""
    need(type(raw) is str and len(raw) <= 32 and re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]{1,18})?", raw), "Invalid raw price text")
    need(price_format in ("DECIMAL", "AMERICAN", "HONG_KONG", "MALAY", "INDONESIAN"), "Explicit supported price format required")
    x = Fraction(raw)
    need(Fraction(1, 10**12) <= abs(x) <= 10**12, "Price outside supported bounds")
    if price_format == "DECIMAL":
        need(x > 1 and not raw.startswith("-"), "Decimal must exceed one")
        return x
    if price_format == "AMERICAN":
        need(re.fullmatch(r"[+-][0-9]+", raw) and abs(x) >= 100, "American requires signed integer magnitude>=100")
        return 1 + (x / 100 if x > 0 else 100 / abs(x))
    if price_format == "HONG_KONG":
        need(x > 0, "Hong Kong must be positive")
        return 1 + x
    need((0 < abs(x) <= 1) if price_format == "MALAY" else abs(x) >= 1,
         "Malay magnitude<=1; Indonesian magnitude>=1")
    return 1 + (x if x > 0 else 1 / abs(x))


def decimal_display(x: Fraction) -> str:
    with localcontext() as ctx:
        ctx.prec = 100
        return format(Decimal(x.numerator) / Decimal(x.denominator), ".30f").rstrip("0").rstrip(".")


@dataclass(frozen=True, slots=True)
class FrozenRecord:
    canonical_bytes: bytes
    sha256: str
    protocol: str


def seal(payload):
    raw = canonical(payload)
    need(len(raw) <= 65536, "Record too large")
    return FrozenRecord(raw, hashlib.sha256(b"PMB offline record v1\0" + raw).hexdigest(), payload["protocol"])


def fixture_fields(p):
    need(p["league"] == "EPL" and p["period"] == "REGULATION_90", "Only EPL regulation90")
    pe._id(p["fixture_id"], "fixture")
    for k in ("home", "away"):
        pe._text(p[k], k, length=90, ascii_only=True)
    need(p["home"].casefold() != p["away"].casefold(), "Teams must differ")
    p["kickoff_utc"] = pe._utc(p["kickoff_utc"], "kickoff")
    if p["previous_entry_sha256"] is not None:
        pe._digest(p["previous_entry_sha256"], "previous")


def freeze_odds(value, *, source_bytes: bytes | None = None) -> FrozenRecord:
    p = pe._load(value)
    required = {"protocol", "league", "fixture_id", "home", "away", "kickoff_utc", "bookmaker", "market", "period",
                "selection", "handicap_q", "price_format", "raw_price", "source_url", "source_kind", "rights_status",
                "source_content_sha256", "captured_at_utc", "claimed_observed_at_utc", "independent_observed_at_utc",
                "operator", "provenance_assurance", "previous_entry_sha256", "snapshot_id"}
    fields(p, required, {"decimal_price", "decimal_price_exact", "price_display_policy", "timing_status"})
    need(p["protocol"] == PROTOCOL and p["provenance_assurance"] == "LOCAL_ONLY", "Local odds protocol required")
    fixture_fields(p)
    pe._text(p["bookmaker"], "bookmaker", length=90, ascii_only=True)
    pe._id(p["snapshot_id"], "snapshot_id")
    pe._id(p["operator"], "operator")
    pe._url(p["source_url"], "source_url")
    need(p["source_kind"] in ("MANUAL_TRANSCRIPTION", "RETAINED_SNAPSHOT"), "Unsupported source kind")
    need(p["rights_status"] in ("CLEARED", "UNKNOWN", "BLOCKED"), "Explicit rights status")
    need(p["market"] in ("1X2", "AH"), "Unsupported market")
    if p["market"] == "1X2":
        need(p["selection"] in ("HOME", "DRAW", "AWAY") and p["handicap_q"] is None, "1X2 selection/line")
    else:
        need(p["selection"] in ("HOME", "AWAY") and type(p["handicap_q"]) is int
             and -80 <= p["handicap_q"] <= 80, "AH requires explicit quarter units in[-80,80]")
    d = price(p["raw_price"], p["price_format"])
    calculated = {"decimal_price": decimal_display(d), "decimal_price_exact": str(d),
                  "price_display_policy": "30dp_display_only_exact_rational_authoritative"}
    for key, val in calculated.items():
        need(key not in p or p[key] == val, "Contradictory calculated price")
        p[key] = val
    for k in ("captured_at_utc", "claimed_observed_at_utc", "independent_observed_at_utc"):
        p[k] = pe._optional_utc(p[k], k) if k != "captured_at_utc" else pe._utc(p[k], k)
    need(p["claimed_observed_at_utc"] is None or p["claimed_observed_at_utc"] <= p["captured_at_utc"], "Claim cannot postdate capture")
    need(p["independent_observed_at_utc"] is None or p["independent_observed_at_utc"] >= p["captured_at_utc"], "Independent review cannot precede capture")
    status = "PREMATCH_CAPTURE" if p["captured_at_utc"] < p["kickoff_utc"] else "LATE_UNSUITABLE_FOR_PREMATCH"
    need("timing_status" not in p or p["timing_status"] == status, "Contradictory timing")
    p["timing_status"] = status
    if source_bytes is not None:
        need(type(source_bytes) is bytes and len(source_bytes) <= 4*1024*1024, "Source bytes invalid")
        digest = hashlib.sha256(source_bytes).hexdigest()
        need(p["source_content_sha256"] in (None, digest), "Source bytes/hash mismatch")
        p["source_content_sha256"] = digest
    if p["source_content_sha256"] is not None:
        pe._digest(p["source_content_sha256"], "source hash")
    return seal(p)


def checked(record: FrozenRecord):
    need(type(record) is FrozenRecord, "Expected frozen record")
    if record.protocol == PROTOCOL:
        replay = freeze_odds(record.canonical_bytes)
    else:
        from .result_evaluation import freeze_result
        replay = freeze_result(record.canonical_bytes)
    need(replay == record, "Record integrity mismatch")
    return json.loads(record.canonical_bytes)


def validate_chain(entries: tuple[FrozenRecord, ...], *, expected_head=None) -> bool:
    need(type(entries) is tuple, "Immutable complete chain required")
    previous, seen = None, set()
    for entry in entries:
        p = checked(entry)
        need(p["previous_entry_sha256"] == previous and entry.sha256 not in seen, "Missing root, broken link or duplicate")
        seen.add(entry.sha256)
        previous = entry.sha256
    need(expected_head is None or previous == expected_head, "External head mismatch")
    return True


def append_record(entries: tuple[FrozenRecord, ...], entry: FrozenRecord):
    candidate = entries + (entry,)
    validate_chain(candidate)
    return candidate
