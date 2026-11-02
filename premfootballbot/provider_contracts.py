"""C1-C1 invented-only, offline provider contract primitives.

All identities and URLs deliberately belong to fake ``toy:`` / ``example.invalid``
namespace. These contracts DO NOT validate actual data rights or timestamps and
cannot turn a provider record into C0 evidence or model input.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlsplit

VERSION = "c1c1-invented-provider-contract-v1"
ASSURANCE = "INVENTED_OFFLINE_UNVERIFIED"
DOMAIN = b"PremFootballBot C1-C1 invented contracts v1\0"
MAX_BYTES = 32768
MAX_NESTING = 32
_ID = re.compile(r"toy:[a-z0-9][a-z0-9_-]{0,70}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z")
_PRICE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,12})?\Z")
_LINE = re.compile(r"[+-]?(?:0|[1-9][0-9]*)(?:\.(?:0|00|25|5|50|75))?\Z")
PURPOSES = frozenset(("SCHEMA_RESEARCH", "FIXTURE_MAPPING", "MARKET_QUALIFICATION"))


class ProviderContractError(ValueError):
    """Stable code for rejected untrusted synthetic data."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


def need(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise ProviderContractError(code, detail)


def toy(value: Any, field: str = "identity") -> str:
    need(type(value) is str and _ID.fullmatch(value) is not None,
         "NON_SYNTHETIC_ID", f"{field} must be a toy: identifier")
    return value


def digest(value: Any, field: str = "digest") -> str:
    need(type(value) is str and _SHA.fullmatch(value) is not None,
         "INVALID_DIGEST", f"{field} must be a lowercase SHA-256 hex digest")
    return value


def utc(value: Any, field: str = "time") -> datetime:
    need(type(value) is str and _UTC.fullmatch(value) is not None,
         "INVALID_UTC", f"{field} must be strict UTC with Z")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProviderContractError("INVALID_UTC", f"Invalid {field}") from exc
    need(timestamp.utcoffset().total_seconds() == 0 and timestamp.tzinfo is not None,
         "INVALID_UTC", f"Invalid {field}")
    return timestamp


def invented_url(value: Any) -> str:
    need(type(value) is str and 1 <= len(value) <= 300,
         "SOURCE_URL", "Invented URL required")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ProviderContractError("SOURCE_URL", "Malformed URL") from exc
    need(parsed.scheme == "https" and parsed.netloc == "example.invalid" and
         parsed.hostname == "example.invalid" and parsed.path.startswith("/") and
         parsed.path != "/" and not parsed.query and not parsed.fragment and
         not parsed.username and not parsed.password and parsed.port is None,
         "SOURCE_URL", "Only https://example.invalid/<path> is supported")
    return value


def fields(raw: Any, required: set[str], optional: set[str] = frozenset()) -> dict:
    need(type(raw) is dict, "INPUT_TYPE", "Expected a plain JSON-like object")
    need(set(raw) >= required, "MISSING_FIELD", "Missing required keys")
    need(set(raw) <= required | optional, "FORBIDDEN_FIELD", "Unexpected keys")
    return raw


def _pairs(entries):
    result = {}
    for k, v in entries:
        if k in result:
            raise ValueError("Duplicate JSON key")
        result[k] = v
    return result


def _bad_token(token):
    # This lab's invented provider examples use string-form numeric data only.
    raise ValueError("Numeric/nonfinite JSON token prohibited")


def _depth(value: Any, limit: int = MAX_NESTING) -> None:
    # Bounded recursion: if untrusted data exceeds limit, reject immediately.
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        need(depth <= limit, "MALFORMED_JSON", "Excessive JSON nesting")
        if type(item) is dict:
            for k, v in item.items():
                need(type(k) is str, "MALFORMED_JSON", "Object key must be text")
                stack.append((v, depth + 1))
        elif type(item) is list:
            stack.extend((v, depth + 1) for v in item)
        else:
            need(type(item) in (str, bool, type(None)),
                 "MALFORMED_JSON", "Unsupported JSON value type")


def decode_invented_json(raw: bytes) -> dict:
    need(type(raw) is bytes and 1 <= len(raw) <= MAX_BYTES,
         "MALFORMED_JSON", "Bounded bytes required")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_bad_token, parse_int=_bad_token,
                           parse_float=_bad_token)
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ProviderContractError("MALFORMED_JSON", "Unable to decode invented JSON") from exc
    _depth(value)
    need(type(value) is dict, "MALFORMED_JSON", "Expected JSON object root")
    return value


def canonical(value: dict) -> bytes:
    _depth(value)
    try:
        result = json.dumps(value, ensure_ascii=True, sort_keys=True,
                            allow_nan=False, separators=(",", ":")).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ProviderContractError("MALFORMED_JSON", "Unable to serialize invented JSON") from exc
    need(len(result) <= MAX_BYTES, "OVERSIZE", "Invented JSON exceeds size cap")
    return result


def seal(value: dict) -> tuple[bytes, str]:
    raw = canonical(value)
    return raw, hashlib.sha256(DOMAIN + raw).hexdigest()


def exact_price(text: Any) -> str:
    need(type(text) is str and len(text) <= 24 and _PRICE.fullmatch(text) is not None,
         "PRICE_FORMAT", "String-form ASCII decimal price required")
    number = Fraction(Decimal(text))
    need(Fraction(1) < number <= Fraction(10000), "PRICE_FORMAT", "Price out of bounds")
    # Input lexical form remains recoverable from source bytes; output is exact.
    fraction = Decimal(text)
    result = format(fraction, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def quarter_units(value: Any) -> int:
    need(type(value) is str and len(value) <= 24 and _LINE.fullmatch(value) is not None,
         "HANDICAP_LINE", "Exact signed quarter-goal text required")
    need(not (value.startswith("-") and Decimal(value) == 0),
         "HANDICAP_LINE", "Negative zero is ambiguous")
    exact = Fraction(Decimal(value))
    q = exact * 4
    need(abs(exact) <= 20 and q.denominator == 1,
         "HANDICAP_LINE", "Quarter-goal increment and +/-20 bound required")
    return q.numerator


@dataclass(frozen=True, slots=True)
class SourceEnvelope:
    canonical_bytes: bytes
    sha256: str
    raw_sha256: str
    provider: str
    fixture_id: str
    acquisition_utc: str
    rights_sha256: str
    profile_sha256: str
    fixture_binding_sha256: str


def make_source_envelope(*, invented_bytes: bytes, provider: str, fixture_id: str,
                         request_id: str, source_url: str, acquisition_utc: str,
                         rights_sha256: str, profile_sha256: str,
                         fixture_binding_sha256: str) -> SourceEnvelope:
    # Source bytes must be invented, not arbitrary real response data.
    payload = decode_invented_json(invented_bytes)
    need(payload.get("protocol") == VERSION and payload.get("assurance") == ASSURANCE,
         "NON_SYNTHETIC_SOURCE", "Invented protocol and assurance required")
    toy(provider, "provider")
    toy(fixture_id, "fixture_id")
    toy(request_id, "request_id")
    invented_url(source_url)
    utc(acquisition_utc, "acquisition_utc")
    digest(rights_sha256, "rights_sha256")
    digest(profile_sha256, "profile_sha256")
    digest(fixture_binding_sha256, "fixture_binding_sha256")
    need(payload.get("provider") == provider and payload.get("fixture_id") == fixture_id,
         "SOURCE_MISMATCH", "Source identity mismatch")
    raw_digest = hashlib.sha256(invented_bytes).hexdigest()
    info = dict(protocol=VERSION, assurance=ASSURANCE, provider=provider,
                fixture_id=fixture_id, request_id=request_id, source_url=source_url,
                raw_sha256=raw_digest, raw_length=str(len(invented_bytes)),
                acquisition_utc=acquisition_utc, rights_sha256=rights_sha256,
                profile_sha256=profile_sha256,
                fixture_binding_sha256=fixture_binding_sha256)
    encoded, sha = seal(info)
    return SourceEnvelope(encoded, sha, raw_digest, provider, fixture_id,
                          acquisition_utc, rights_sha256, profile_sha256,
                          fixture_binding_sha256)


def verify_source_envelope(envelope: SourceEnvelope, invented_bytes: bytes) -> dict:
    need(type(envelope) is SourceEnvelope and type(envelope.canonical_bytes) is bytes,
         "FORGED_ENVELOPE", "Expected immutable envelope")
    raw = decode_invented_json(envelope.canonical_bytes)
    need(canonical(raw) == envelope.canonical_bytes and
         hashlib.sha256(DOMAIN + envelope.canonical_bytes).hexdigest() == envelope.sha256,
         "FORGED_ENVELOPE", "Envelope does not replay")
    need(set(raw) == {"protocol", "assurance", "provider", "fixture_id", "request_id",
                            "source_url", "raw_sha256", "raw_length", "acquisition_utc",
                            "rights_sha256", "profile_sha256", "fixture_binding_sha256"},
         "FORGED_ENVELOPE", "Envelope has unexpected fields")
    need(raw.get("protocol") == VERSION and raw.get("assurance") == ASSURANCE,
         "FORGED_ENVELOPE", "Wrong assurance")
    toy(raw.get("provider"), "provider")
    toy(raw.get("fixture_id"), "fixture_id")
    toy(raw.get("request_id"), "request_id")
    invented_url(raw.get("source_url"))
    utc(raw.get("acquisition_utc"), "acquisition_utc")
    digest(raw.get("rights_sha256"), "rights_sha256")
    digest(raw.get("profile_sha256"), "profile_sha256")
    digest(raw.get("raw_sha256"), "raw_sha256")
    digest(raw.get("fixture_binding_sha256"), "fixture_binding_sha256")
    # Validate the untrusted length lexeme *before* int() to avoid CPython's
    # 4,300-digit conversion ValueError escaping the structured-denial API.
    length_text = raw.get("raw_length")
    need(type(length_text) is str and 1 <= len(length_text) <= len(str(MAX_BYTES)) and
         length_text.isascii() and length_text.isdecimal() and
         length_text[0] != "0", "FORGED_ENVELOPE", "Invalid length syntax")
    raw_length = int(length_text)
    need(1 <= raw_length <= MAX_BYTES, "FORGED_ENVELOPE", "Invalid length")
    need(type(invented_bytes) is bytes and len(invented_bytes) == raw_length and
         hashlib.sha256(invented_bytes).hexdigest() == raw["raw_sha256"],
         "SOURCE_MISMATCH", "Payload does not match sealed envelope")
    need(raw["provider"] == envelope.provider and raw["fixture_id"] == envelope.fixture_id and
         raw["raw_sha256"] == envelope.raw_sha256 and
         raw["acquisition_utc"] == envelope.acquisition_utc and
         raw["rights_sha256"] == envelope.rights_sha256 and
         raw["profile_sha256"] == envelope.profile_sha256 and
         raw["fixture_binding_sha256"] == envelope.fixture_binding_sha256,
         "FORGED_ENVELOPE", "Dataclass metadata differs from sealed bytes")
    return raw
