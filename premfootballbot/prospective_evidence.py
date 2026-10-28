"""Local-only, deterministic pre-kickoff evidence commitments. No I/O or clocks.

This module neither verifies source first-publication nor obtains trusted time.
GitHub comment metadata supplied by a caller is untrusted, even when plausible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit
import unicodedata

VERSION = "pmb-prospective-evidence/v1"
DOMAIN = b"PremFootballBot prospective evidence v1\x00"
MAX_JSON_BYTES = 65536
MAX_INPUTS = 32
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,79}\Z")
_DEC = re.compile(r"(?:0|1)(?:\.\d{1,18})?|0?\.\d{1,18}\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_FORBIDDEN_KEY = re.compile(r"(^|_)(?:score|outcome|result|final_goals|settlement|profit|roi)(?:_|$)", re.I)


class EvidenceError(ValueError):
    """Rejected provenance, temporal, or protocol input."""


@dataclass(frozen=True)
class FrozenEvidence:
    canonical_bytes: bytes
    commitment_sha256: str
    protocol: str
    fixture_id: str
    kickoff_utc: str
    cutoff_utc: str
    forecast_kind: str
    assurance: str = "LOCAL_ONLY"


@dataclass(frozen=True)
class CommentAssessment:
    status: str  # REJECTED or PLAUSIBLE_CLAIM_UNVERIFIED, never independently verified
    issues: tuple[str, ...]
    external_audit_required: bool = True


def _reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise EvidenceError(f"duplicate JSON field: {key}")
        obj[key] = value
    return obj


def _reject_constant(value: str) -> None:
    raise EvidenceError(f"unsupported JSON constant: {value}")


def _load(value: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    if isinstance(value, Mapping):
        # round-trip to detach mutable caller objects and reject non-JSON values
        try:
            raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise EvidenceError("packet must contain valid JSON values") from exc
    elif isinstance(value, (str, bytes)):
        try:
            raw = value.encode("utf-8") if isinstance(value, str) else value
        except UnicodeError as exc:
            raise EvidenceError("packet must be UTF-8") from exc
    else:
        raise EvidenceError("packet must be a JSON object or UTF-8 JSON")
    if len(raw) > MAX_JSON_BYTES:
        raise EvidenceError("packet exceeds maximum JSON bytes")
    try:
        parsed = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_reject_duplicate,
                            parse_constant=_reject_constant,
                            parse_float=lambda x: (_ for _ in ()).throw(EvidenceError("JSON floats are not supported")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceError("invalid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise EvidenceError("packet root must be an object")
    return parsed


def _fields(obj: Any, required: set[str], optional: set[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise EvidenceError(f"{where} must be an object")
    keys = set(obj)
    if any(not isinstance(k, str) for k in keys):
        raise EvidenceError(f"{where} contains non-string field")
    if any(_FORBIDDEN_KEY.search(k) for k in keys):
        raise EvidenceError(f"{where}: postmatch field forbidden")
    missing, extra = required - keys, keys - required - optional
    if missing or extra:
        raise EvidenceError(f"{where}: missing={sorted(missing)} unexpected={sorted(extra)}")
    return obj


def _text(value: Any, where: str, *, length: int = 200, ascii_only: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > length:
        raise EvidenceError(f"{where} must be nonempty bounded text")
    if any(unicodedata.category(ch).startswith("C") or ch in "\u2028\u2029" for ch in value):
        raise EvidenceError(f"{where} contains control/format characters")
    if ascii_only and not value.isascii():
        raise EvidenceError(f"{where} must be ASCII to prevent confusables")
    if value != value.strip() or value != unicodedata.normalize("NFC", value):
        raise EvidenceError(f"{where} must be trimmed and NFC normalized")
    return value


def _id(value: Any, where: str) -> str:
    s = _text(value, where, length=80, ascii_only=True)
    if not _ID.fullmatch(s):
        raise EvidenceError(f"{where} must be a stable identifier")
    return s


def _digest(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise EvidenceError(f"{where} must be lowercase SHA-256 hex")
    return value


def _utc(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise EvidenceError(f"{where} must use exact UTC timestamp ending Z")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{where} is invalid UTC timestamp") from exc
    if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
        raise EvidenceError(f"{where} must be UTC aware")
    return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _url(value: Any, where: str, *, allow_local: bool = False) -> str:
    s = _text(value, where, length=2048, ascii_only=True)
    p = urlsplit(s)
    if p.username or p.password or p.fragment or not p.netloc or (p.scheme != "https" and not (allow_local and p.scheme == "local")):
        raise EvidenceError(f"{where} must be an HTTPS reference without embedded credentials/fragment")
    if re.search(r"(?:token|secret|password|api[_-]?key|authorization)\s*=", p.query, re.I):
        raise EvidenceError(f"{where} must not contain credential query parameters")
    return s


def _optional_utc(value: Any, where: str) -> str | None:
    return None if value is None else _utc(value, where)


def _normalized(packet: dict[str, Any]) -> dict[str, Any]:
    _fields(packet, {"protocol", "league", "fixture", "cutoff_utc", "inputs", "forecast", "model", "capture", "assurance"}, set(), "packet")
    if packet["protocol"] != VERSION or packet["league"] != "EPL" or packet["assurance"] != "LOCAL_ONLY":
        raise EvidenceError("protocol/league/assurance must be v1/EPL/LOCAL_ONLY")
    f = _fields(packet["fixture"], {"fixture_id", "home", "away", "kickoff_utc", "kickoff_source_url", "kickoff_observed_at_utc"}, set(), "fixture")
    fixture_id = _id(f["fixture_id"], "fixture_id")
    home = _text(f["home"], "home team", length=90, ascii_only=True)
    away = _text(f["away"], "away team", length=90, ascii_only=True)
    if home.casefold() == away.casefold():
        raise EvidenceError("home and away must differ")
    kickoff = _utc(f["kickoff_utc"], "kickoff_utc")
    cutoff = _utc(packet["cutoff_utc"], "cutoff_utc")
    if cutoff >= kickoff:
        raise EvidenceError("cutoff_utc must be strictly before kickoff_utc")
    kickoff_observed = _optional_utc(f["kickoff_observed_at_utc"], "kickoff_observed_at_utc")
    if kickoff_observed is not None and kickoff_observed > cutoff:
        raise EvidenceError("kickoff cannot first be observed after cutoff")
    source = _url(f["kickoff_source_url"], "kickoff_source_url")
    if not isinstance(packet["inputs"], list) or len(packet["inputs"]) > MAX_INPUTS:
        raise EvidenceError("inputs must be a list with <=32 references")
    ids: set[str] = set()
    inputs = []
    for i, obj in enumerate(packet["inputs"]):
        r = _fields(obj, {"source_id", "source_url", "content_sha256", "license_status", "license_reference", "acquired_at_utc", "source_available_at_utc", "verified_by_external_observer_at_utc"}, set(), f"inputs[{i}]")
        source_id = _id(r["source_id"], f"inputs[{i}].source_id")
        if source_id in ids:
            raise EvidenceError("duplicate source_id")
        ids.add(source_id)
        rights = r["license_status"]
        if rights not in ("CLEARED", "UNKNOWN", "BLOCKED"):
            raise EvidenceError("license_status must be explicitly CLEARED/UNKNOWN/BLOCKED")
        acquired = _utc(r["acquired_at_utc"], "acquired_at_utc")
        availability = _optional_utc(r["source_available_at_utc"], "source_available_at_utc")
        externally_observed = _optional_utc(r["verified_by_external_observer_at_utc"], "verified_by_external_observer_at_utc")
        if acquired > cutoff or (availability is not None and availability > acquired):
            raise EvidenceError("source acquisition must precede cutoff and source availability must precede acquisition")
        if externally_observed is not None and externally_observed > cutoff:
            raise EvidenceError("external observation cannot occur after cutoff in prematch packet")
        inputs.append({"source_id": source_id,
                       "source_url": _url(r["source_url"], "source_url", allow_local=True),
                       "content_sha256": _digest(r["content_sha256"], "content_sha256"),
                       "license_status": rights,
                       "license_reference": _url(r["license_reference"], "license_reference") if r["license_reference"] is not None else None,
                       "acquired_at_utc": acquired,
                       "source_available_at_utc": availability,
                       "verified_by_external_observer_at_utc": externally_observed})
    forecast = _fields(packet["forecast"], {"kind"}, {"probabilities"}, "forecast")
    model = packet["model"]
    if forecast["kind"] == "NO_FORECAST":
        if "probabilities" in forecast or model is not None:
            raise EvidenceError("NO_FORECAST cannot contain probabilities or a model")
        forecast_value: dict[str, Any] = {"kind": "NO_FORECAST"}
    elif forecast["kind"] == "ONE_X_TWO":
        if not isinstance(model, dict):
            raise EvidenceError("ONE_X_TWO requires a real, identified model")
        probs = _fields(forecast.get("probabilities"), {"home", "draw", "away"}, set(), "probabilities")
        values: dict[str, str] = {}
        total = Decimal(0)
        for key in ("home", "draw", "away"):
            raw = probs[key]
            if not isinstance(raw, str) or not _DEC.fullmatch(raw):
                raise EvidenceError(f"probabilities.{key} must be exact decimal text in [0,1]")
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise EvidenceError("invalid decimal probability") from exc
            if not (Decimal(0) <= value <= Decimal(1)):
                raise EvidenceError("probability out of range")
            total += value
            values[key] = format(value.normalize(), "f")
        if total != 1:
            raise EvidenceError("probabilities must total exactly 1")
        forecast_value = {"kind": "ONE_X_TWO", "probabilities": values}
    else:
        raise EvidenceError("unknown forecast kind")
    if model is not None:
        m = _fields(model, {"name", "version", "config_sha256"}, set(), "model")
        model = {"name": _id(m["name"], "model.name"),
                 "version": _id(m["version"], "model.version"),
                 "config_sha256": _digest(m["config_sha256"], "model.config_sha256")}
    capture = _fields(packet["capture"], {"captured_at_utc", "operator", "method", "local_only"}, set(), "capture")
    captured_at = _utc(capture["captured_at_utc"], "captured_at_utc")
    if capture["local_only"] is not True or capture["method"] not in ("manual", "offline_file"):
        raise EvidenceError("capture must explicitly be local_only manual/offline_file")
    operator = _id(capture["operator"], "capture.operator")
    # Captured after cutoff or fixture is not a credible pre-match local capture.
    if captured_at > cutoff:
        raise EvidenceError("captured_at_utc must not exceed cutoff_utc")
    if kickoff_observed is not None and kickoff_observed > captured_at:
        raise EvidenceError("kickoff was not observed before capture")
    if any(item["acquired_at_utc"] > captured_at or
           (item["verified_by_external_observer_at_utc"] is not None and
            item["verified_by_external_observer_at_utc"] > captured_at)
           for item in inputs):
        raise EvidenceError("input timestamps cannot exceed captured_at_utc")
    return {
        "protocol": VERSION, "league": "EPL", "assurance": "LOCAL_ONLY",
        "fixture": {"fixture_id": fixture_id, "home": home, "away": away,
                    "kickoff_utc": kickoff, "kickoff_source_url": source,
                    "kickoff_observed_at_utc": kickoff_observed},
        "cutoff_utc": cutoff,
        "inputs": sorted(inputs, key=lambda r: r["source_id"]),
        "forecast": forecast_value, "model": model,
        "capture": {"captured_at_utc": captured_at, "operator": operator,
                    "method": capture["method"], "local_only": True},
    }


def freeze_packet(packet: Mapping[str, Any] | str | bytes) -> FrozenEvidence:
    """Validate and canonically freeze a local-only pre-match evidence packet.

    This function never reads files, sends network requests or consults a clock.
    The returned digest does NOT certify timestamps or source availability.
    """
    p = _normalized(_load(packet))
    canonical = json.dumps(p, sort_keys=True, ensure_ascii=False, allow_nan=False,
                           separators=(",", ":")).encode("utf-8")
    if len(canonical) > MAX_JSON_BYTES:
        raise EvidenceError("canonical packet exceeds limit")
    digest = hashlib.sha256(DOMAIN + canonical).hexdigest()
    return FrozenEvidence(canonical, digest, VERSION, p["fixture"]["fixture_id"],
                          p["fixture"]["kickoff_utc"], p["cutoff_utc"],
                          p["forecast"]["kind"])


def manual_comment_template(frozen: FrozenEvidence) -> str:
    """Return copyable, unposted GitHub issue-comment text (never an action)."""
    if not isinstance(frozen, FrozenEvidence):
        raise EvidenceError("expected FrozenEvidence")
    return ("PREMATCH EVIDENCE COMMITMENT — NOT INDEPENDENTLY CERTIFIED\n"
            f"protocol: {frozen.protocol}\n"
            f"fixture: {frozen.fixture_id}\n"
            f"kickoff_utc: {frozen.kickoff_utc}\n"
            f"cutoff_utc: {frozen.cutoff_utc}\n"
            f"sha256: {frozen.commitment_sha256}\n"
            "status: LOCAL_ONLY until independently checked; a posted hash is not source verification")


def assess_untrusted_comment_metadata(frozen: FrozenEvidence, metadata: Mapping[str, Any],
                                      *, fixture_status: str = "UNKNOWN") -> CommentAssessment:
    """Assess *claimed* comment metadata without granting independent trust.

    Metadata may be fabricated. A live independent server fetch and external
    validation of original kickoff and source provenance are still required.
    """
    problems: list[str] = []
    if not isinstance(frozen, FrozenEvidence):
        raise EvidenceError("expected FrozenEvidence")
    try:
        m = _fields(dict(metadata), {"id", "html_url", "body", "created_at", "updated_at"}, set(), "comment")
        if isinstance(m["id"], bool) or not isinstance(m["id"], int) or m["id"] <= 0:
            problems.append("invalid GitHub comment ID")
        url = _text(m["html_url"], "comment html_url", length=2048, ascii_only=True)
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/\d+#issuecomment-\d+", url):
            problems.append("comment URL is not a GitHub issue comment permalink")
        elif url.rsplit("#issuecomment-", 1)[1] != str(m["id"]):
            problems.append("comment permalink ID mismatches comment ID")
        if m["body"] != manual_comment_template(frozen):
            problems.append("comment body does not exactly match commitment")
        created = _utc(m["created_at"], "comment.created_at")
        updated = _utc(m["updated_at"], "comment.updated_at")
        if created >= frozen.cutoff_utc or created >= frozen.kickoff_utc:
            problems.append("comment was not created before cutoff and kickoff")
        if updated != created:
            problems.append("comment was edited or updated")
        if fixture_status in ("CANCELLED", "RESCHEDULED", "POSTPONED"):
            problems.append("fixture no longer matches scheduled kickoff")
        elif fixture_status not in ("UNKNOWN", "SCHEDULED"):
            problems.append("unknown fixture_status")
    except (EvidenceError, ValueError, TypeError) as exc:
        problems.append(f"invalid comment metadata: {exc}")
    return CommentAssessment("REJECTED" if problems else "PLAUSIBLE_CLAIM_UNVERIFIED",
                             tuple(problems))


def manual_external_audit_worksheet(frozen: FrozenEvidence) -> str:
    """Produce a human-readable checklist, with no claims of external evidence."""
    return (f"Protocol: {frozen.protocol}\nFixture: {frozen.fixture_id}\n"
            f"Frozen SHA-256: {frozen.commitment_sha256}\n"
            "Independent audit required: YES\n"
            "[ ] Fetch live GitHub comment ID, URL, body, created_at and updated_at independently.\n"
            "[ ] Confirm body/digest, independently check edit history and deletion risk.\n"
            "[ ] Verify original fixture kickoff/cutoff and changes from reliable external sources.\n"
            "[ ] Verify original input publication times and licence/rights separately.\n"
            "[ ] Do not infer real prediction performance or backdated input availability.\n")