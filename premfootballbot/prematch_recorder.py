"""Offline C0: append-only LOCAL_ONLY pre-match abstention evidence.

No model execution, result labels, external feeds, clock, schedule or network.
Caller-supplied timestamps and hashes are NOT trusted time / provenance proof.
Older ledger files remain immutable; a caller must preserve/pin prior heads.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from . import prospective_evidence as pe
from . import odds_observations as oo

VERSION = "pmb-prematch-recorder/v1"
DOMAIN = b"PremFootballBot offline C0 record v1\0"
ASSURANCE = "LOCAL_ONLY_EXTERNAL_AUDIT_REQUIRED"
REASONS = ("NO_AUTHORIZED_MODEL", "MISSING_PERMITTED_INPUTS", "UNKNOWN_FIXTURE", "OTHER_ABSTENTION")
MAX_RECORDS = 1024
MAX_ODDS = 32
MAX_LEDGER_BYTES = 8 * 1024 * 1024
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class RecorderError(ValueError):
    """Invalid local evidence, chain, or persistence boundary."""


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise RecorderError(message)


def _plain(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _bad_constant(value):
    raise RecorderError("Non-finite JSON constant: " + value)


def _load_json(raw: bytes):
    _need(type(raw) is bytes and len(raw) <= MAX_LEDGER_BYTES,
          "Bounded UTF-8 ledger bytes required")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_bad_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RecorderError("Invalid UTF-8 JSON") from exc


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    canonical_bytes: bytes
    sha256: str
    fixture_id: str
    kickoff_utc: str
    cutoff_utc: str
    previous_sha256: str | None
    assurance: str = ASSURANCE


def capture_abstention(packet: pe.FrozenEvidence, *, repo_commit: str,
                       repo_tree: str, reason: str,
                       odds: tuple[oo.FrozenRecord, ...] = (),
                       previous_sha256: str | None = None) -> CaptureRecord:
    """Freeze an EXISTING no-forecast packet; never synthesize a model output.

    Only explicitly CLEARED manually captured odds records can be attached.
    A local record is not proof of historical publication, API rights or time.
    """
    _need(type(packet) is pe.FrozenEvidence and pe.freeze_packet(packet.canonical_bytes) == packet,
          "Untrusted or modified frozen packet")
    _need(packet.forecast_kind == "NO_FORECAST", "C0 forbids forecasts or model output")
    _need(type(reason) is str and reason in REASONS, "Unknown abstention reason")
    _need(type(repo_commit) is str and _HEX40.fullmatch(repo_commit)
          and type(repo_tree) is str and _HEX40.fullmatch(repo_tree),
          "Full exact Git commit and tree SHAs required")
    _need(previous_sha256 is None or
          (type(previous_sha256) is str and _HEX64.fullmatch(previous_sha256)),
          "Invalid previous head")
    _need(type(odds) is tuple and len(odds) <= MAX_ODDS,
          "Bounded odds tuple required")

    p = _load_json(packet.canonical_bytes)
    _need(p["forecast"] == {"kind": "NO_FORECAST"} and p["model"] is None,
          "No model or probabilities are authorized in C0")
    # The existing evidence validator checks input timestamps before cutoff.
    _need(p["cutoff_utc"] < p["fixture"]["kickoff_utc"], "Invalid cutoff")
    sources = p["inputs"]
    _need(all(x["license_status"] != "BLOCKED" for x in sources),
          "Blocked provider inputs are not recorded")
    quotes = []
    seen_hashes, seen_keys, snapshot_metadata = set(), set(), {}
    for q in odds:
        _need(type(q) is oo.FrozenRecord and q.protocol == oo.PROTOCOL,
              "Only frozen odds evidence is allowed")
        raw = oo.checked(q)  # Reparse/reseal via existing source validator.
        _need(q.sha256 not in seen_hashes, "Duplicate odds digest")
        _need(all(raw[k] == p["fixture"][k] for k in
                  ("fixture_id", "home", "away", "kickoff_utc")), "Odds/fixture mismatch")
        _need(raw["rights_status"] == "CLEARED" and
              raw["timing_status"] == "PREMATCH_CAPTURE", "Late or uncleared odds")
        _need(raw["captured_at_utc"] <= p["capture"]["captured_at_utc"]
              and raw["captured_at_utc"] <= p["cutoff_utc"],
              "Odds captured after the freeze/cutoff")
        _need(raw["independent_observed_at_utc"] is None or
              (raw["independent_observed_at_utc"] <= p["capture"]["captured_at_utc"]
               and raw["independent_observed_at_utc"] <= p["cutoff_utc"]),
              "External observation claimed after packet capture or cutoff")
        matching = [x for x in sources if (x["source_url"], x["content_sha256"])
                    == (raw["source_url"], raw["source_content_sha256"])]
        _need(len(matching) == 1 and matching[0]["license_status"] == "CLEARED"
              and matching[0]["acquired_at_utc"] <= raw["captured_at_utc"],
              "Cleared timestamped source reference not linked to quote")
        # One snapshot/bookmaker has one capture time and source identity.
        # A genuinely later quote requires a different snapshot ID.
        snapshot_key = (raw["snapshot_id"], raw["bookmaker"])
        metadata = (raw["captured_at_utc"], raw["source_url"],
                    raw["source_content_sha256"])
        _need(snapshot_key not in snapshot_metadata
              or snapshot_metadata[snapshot_key] == metadata,
              "Inconsistent capture time or source within one snapshot")
        snapshot_metadata[snapshot_key] = metadata
        key = (raw["snapshot_id"], raw["bookmaker"], raw["market"],
               raw["selection"], raw["handicap_q"])
        _need(key not in seen_keys, "Repeated quote selection in one snapshot")
        seen_keys.add(key)
        seen_hashes.add(q.sha256)
        quotes.append(raw)

    payload = {
        "protocol": VERSION, "assurance": ASSURANCE,
        "repo_commit": repo_commit, "repo_tree": repo_tree,
        "reason": reason, "previous_sha256": previous_sha256,
        "evidence_packet": p, "odds": quotes,
        "result_data": None, "forecast_status": "NO_FORECAST",
        "timing_assurance": "SELF_REPORTED_UNVERIFIED",
        "source_rights": "ALL_CLEARED_CLAIMED" if p["inputs"] and all(
            x["license_status"] == "CLEARED" for x in p["inputs"])
            else "UNCLEARED_OR_EMPTY_REFERENCE_ONLY",
    }
    encoded = _plain(payload)
    _need(len(encoded) <= pe.MAX_JSON_BYTES * 2,
          "Bounded record required")
    return CaptureRecord(encoded, hashlib.sha256(DOMAIN + encoded).hexdigest(),
                         packet.fixture_id, packet.kickoff_utc, packet.cutoff_utc,
                         previous_sha256)


def checked_capture(record: CaptureRecord) -> dict:
    """Replay validated source schemas. Re-sealing alone does not certify truth."""
    _need(type(record) is CaptureRecord and record.assurance == ASSURANCE,
          "Untrusted capture type or assurance")
    p = _load_json(record.canonical_bytes)
    _need(type(p) is dict and set(p) == {
        "protocol", "assurance", "repo_commit", "repo_tree", "reason",
        "previous_sha256", "evidence_packet", "odds", "result_data",
        "forecast_status", "timing_assurance", "source_rights"},
        "Invalid record schema")
    _need(p["protocol"] == VERSION and p["assurance"] == ASSURANCE
          and p["result_data"] is None and p["forecast_status"] == "NO_FORECAST"
          and p["timing_assurance"] == "SELF_REPORTED_UNVERIFIED",
          "Record authorization or result boundary altered")
    _need(type(p["odds"]) is list, "Invalid odds record list")
    replay = capture_abstention(
        pe.freeze_packet(p["evidence_packet"]),
        repo_commit=p["repo_commit"], repo_tree=p["repo_tree"],
        reason=p["reason"],
        odds=tuple(oo.freeze_odds(q) for q in p["odds"]),
        previous_sha256=p["previous_sha256"])
    _need(record == replay, "Capture/rights/seal mismatch")
    return p


def verify_ledger(records: tuple[CaptureRecord, ...], *, expected_head: str | None = None) -> bool:
    _need(type(records) is tuple and len(records) <= MAX_RECORDS,
          "Bounded immutable ledger required")
    _need(expected_head is None or (type(expected_head) is str and _HEX64.fullmatch(expected_head)),
          "Invalid external head")
    previous = None
    seen, identity = set(), set()
    for record in records:
        p = checked_capture(record)
        _need(record.previous_sha256 == previous and record.sha256 not in seen,
              "Broken hash chain or duplicate capture")
        key = (record.fixture_id, record.kickoff_utc, record.cutoff_utc,
               p["repo_commit"])
        _need(key not in identity, "Duplicate fixture/model/cutoff record")
        identity.add(key)
        seen.add(record.sha256)
        previous = record.sha256
    _need(expected_head is None or previous == expected_head,
          "Ledger differs from externally pinned head")
    return True


def append_capture(records: tuple[CaptureRecord, ...], packet: pe.FrozenEvidence, *,
                   repo_commit: str, repo_tree: str, reason: str,
                   odds: tuple[oo.FrozenRecord, ...] = (),
                   expected_head: str | None = None) -> tuple[CaptureRecord, ...]:
    verify_ledger(records, expected_head=expected_head)
    _need(len(records) < MAX_RECORDS, "Ledger full")
    record = capture_abstention(packet, repo_commit=repo_commit, repo_tree=repo_tree,
                               reason=reason, odds=odds,
                               previous_sha256=records[-1].sha256 if records else None)
    candidate = records + (record,)
    verify_ledger(candidate)
    return candidate


def ledger_json(records: tuple[CaptureRecord, ...]) -> bytes:
    verify_ledger(records)
    raw = _plain({"protocol": VERSION, "assurance": ASSURANCE,
                  "entries": [_load_json(r.canonical_bytes) for r in records],
                  "head_sha256": records[-1].sha256 if records else None})
    _need(len(raw) <= MAX_LEDGER_BYTES, "Ledger too large")
    return raw


def load_ledger(raw: bytes, *, expected_head: str | None = None) -> tuple[CaptureRecord, ...]:
    data = _load_json(raw)
    _need(type(data) is dict and set(data) == {"protocol", "assurance", "entries", "head_sha256"}
          and data["protocol"] == VERSION and data["assurance"] == ASSURANCE
          and type(data["entries"]) is list and len(data["entries"]) <= MAX_RECORDS,
          "Unknown ledger format")
    result = []
    for item in data["entries"]:
        _need(type(item) is dict, "Nonobject capture in ledger")
        # Reconstruct from the full original object, then replay every field.
        result.append(checked_capture_payload(item))
    records = tuple(result)
    verify_ledger(records, expected_head=expected_head)
    _need(data["head_sha256"] == (records[-1].sha256 if records else None),
          "Ledger head corrupted")
    _need(ledger_json(records) == raw, "Noncanonical ledger, ambiguous bytes")
    return records


def checked_capture_payload(payload: dict) -> CaptureRecord:
    """Accept only full validated canonical payloads, never hashes alone."""
    _need(type(payload) is dict, "Capture payload required")
    _need(type(payload.get("odds")) is list, "Quote list required")
    packet = pe.freeze_packet(payload["evidence_packet"])
    quotes = tuple(oo.freeze_odds(q) for q in payload["odds"])
    candidate = capture_abstention(packet, repo_commit=payload["repo_commit"],
                                   repo_tree=payload["repo_tree"], reason=payload["reason"],
                                   odds=quotes, previous_sha256=payload["previous_sha256"])
    _need(candidate.canonical_bytes == _plain(payload), "Noncanonical record or altered flags")
    return candidate


def _save_exclusive(filename: Path, raw: bytes) -> None:
    """Never overwrite prior histories; do not write into the public repository."""
    root = Path(__file__).resolve().parent.parent
    location = filename.resolve()
    _need(location != root and root not in location.parents,
          "Output must be outside the source repository")
    _need(filename.parent.is_dir(), "Output parent directory must exist")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    created = False
    try:
        descriptor = os.open(filename, flags, 0o600)
        created = True
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        if created:
            filename.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline C0 abstention and odds evidence recorder; no forecasts")
    commands = parser.add_subparsers(dest="command", required=True)
    write = commands.add_parser("record", help="Create a NEW immutable local ledger file")
    write.add_argument("--packet", type=Path, required=True)
    write.add_argument("--odds", type=Path, action="append", default=[])
    write.add_argument("--previous", type=Path)
    write.add_argument("--expected-head", type=str)
    write.add_argument("--out", type=Path, required=True)
    write.add_argument("--repo-commit", required=True)
    write.add_argument("--repo-tree", required=True)
    write.add_argument("--reason", choices=REASONS, required=True)
    check = commands.add_parser("verify", help="Verify canonical chain and optional external head")
    check.add_argument("--ledger", type=Path, required=True)
    check.add_argument("--expected-head", type=str)
    options = parser.parse_args(argv)
    if options.command == "verify":
        records = load_ledger(options.ledger.read_bytes(), expected_head=options.expected_head)
    else:
        _need(options.previous is not None or options.expected_head is None,
              "Expected head requires an existing ledger")
        prior = (load_ledger(options.previous.read_bytes(),
                             expected_head=options.expected_head) if options.previous else ())
        packet = pe.freeze_packet(options.packet.read_bytes())
        odds = tuple(oo.freeze_odds(p.read_bytes()) for p in options.odds)
        records = append_capture(prior, packet, repo_commit=options.repo_commit,
                                 repo_tree=options.repo_tree, reason=options.reason,
                                 odds=odds, expected_head=options.expected_head)
        _save_exclusive(options.out, ledger_json(records))
    print(json.dumps({"records": len(records), "head_sha256": records[-1].sha256 if records else None,
                      "assurance": ASSURANCE}, sort_keys=True))
    return 0


if __name__ == "__main__":  # Explicit local CLI only; no import-time side effects.
    raise SystemExit(main())
