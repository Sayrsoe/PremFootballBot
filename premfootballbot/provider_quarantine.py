"""C1-C1 offline toy rights/provenance chain; never certifies actual licenses.

An all-toy simulated CLEARED status is not evidence of real-world clearance.
A caller-held expected head is required; self-resealed histories are otherwise
indistinguishable from legitimate chains.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import provider_contracts as c

GENESIS = "0" * 64
STATUSES = frozenset(("UNKNOWN", "BLOCKED", "CLEARED"))


@dataclass(frozen=True, slots=True)
class RightsDecision:
    canonical_bytes: bytes
    sha256: str
    previous_sha256: str
    subject: str
    status: str
    reviewer: str
    reviewed_utc: str


def new_rights_decision(*, subject: str, status: str, purposes: tuple[str, ...],
                        reviewer: str, reviewed_utc: str, effective_utc: str,
                        expires_utc: str, evidence_sha256: str,
                        previous_chain: tuple[RightsDecision, ...] = ()) -> RightsDecision:
    c.toy(subject, "rights subject")
    c.toy(reviewer, "reviewer")
    c.need(type(status) is str and status in STATUSES,
           "RIGHTS_STATUS", "Unknown rights status")
    c.need(type(purposes) is tuple and all(type(p) is str and p in c.PURPOSES for p in purposes)
           and len(purposes) == len(set(purposes)),
           "RIGHTS_PURPOSE", "Use explicit known purposes without duplicates")
    c.need(status == "CLEARED" or not purposes,
           "RIGHTS_PURPOSE", "Uncleared status cannot grant purposes")
    c.utc(reviewed_utc, "reviewed_utc")
    c.utc(effective_utc, "effective_utc")
    c.utc(expires_utc, "expires_utc")
    c.need(c.utc(reviewed_utc) <= c.utc(effective_utc) < c.utc(expires_utc),
           "RIGHTS_TIME", "No backdated clearance or invalid expiry")
    c.digest(evidence_sha256, "evidence_sha256")
    c.need(type(previous_chain) is tuple, "RIGHTS_LINEAGE", "Prior chain must be immutable")
    if previous_chain:
        payload = verify_rights_chain(previous_chain, expected_head=previous_chain[-1].sha256)
        c.need(payload[-1]["subject"] == subject,
               "RIGHTS_LINEAGE", "A chain concerns exactly one subject")
        c.need(c.utc(payload[-1]["reviewed_utc"]) <= c.utc(reviewed_utc) and
               c.utc(payload[-1]["effective_utc"]) <= c.utc(effective_utc),
               "RIGHTS_TIME", "Rights review/effective time cannot go backwards")
    prev_digest = GENESIS if not previous_chain else previous_chain[-1].sha256
    body = dict(protocol=c.VERSION, assurance=c.ASSURANCE, record_kind="RIGHTS_DECISION",
                subject=subject, status=status, purposes=sorted(purposes), reviewer=reviewer,
                reviewed_utc=reviewed_utc, effective_utc=effective_utc,
                expires_utc=expires_utc, evidence_sha256=evidence_sha256,
                previous_sha256=prev_digest)
    raw, sha = c.seal(body)
    return RightsDecision(raw, sha, prev_digest, subject, status, reviewer, reviewed_utc)


def verify_rights_chain(chain: tuple[RightsDecision, ...], *, expected_head: str) -> tuple[dict, ...]:
    c.digest(expected_head, "expected_head")
    c.need(type(chain) is tuple and 1 <= len(chain) <= 100,
           "RIGHTS_LINEAGE", "Bounded nonempty decisions required")
    observed: list[dict] = []
    previous_sha = GENESIS
    subject: str | None = None
    last_review_time = None
    last_effective_time = None
    for item in chain:
        c.need(type(item) is RightsDecision and type(item.canonical_bytes) is bytes,
               "RIGHTS_LINEAGE", "Frozen toy rights decision required")
        decoded = c.decode_invented_json(item.canonical_bytes)
        c.need(set(decoded) == {"protocol", "assurance", "record_kind", "subject", "status",
                "purposes", "reviewer", "reviewed_utc", "effective_utc", "expires_utc",
                "evidence_sha256", "previous_sha256"},
               "RIGHTS_LINEAGE", "Unexpected decision fields")
        c.need(c.canonical(decoded) == item.canonical_bytes and
               c.seal(decoded)[1] == item.sha256 and
               item.previous_sha256 == previous_sha == decoded["previous_sha256"],
               "RIGHTS_LINEAGE", "Corrupt decision bytes or predecessor")
        c.need(decoded["protocol"] == c.VERSION and decoded["assurance"] == c.ASSURANCE and
               decoded["record_kind"] == "RIGHTS_DECISION",
               "RIGHTS_LINEAGE", "Unrecognized decision contract")
        c.toy(decoded["subject"], "subject")
        c.toy(decoded["reviewer"], "reviewer")
        c.digest(decoded["evidence_sha256"], "evidence_sha256")
        c.need(type(decoded["status"]) is str and decoded["status"] in STATUSES, "RIGHTS_STATUS", "Invalid rights state")
        granted = decoded["purposes"]
        c.need(type(granted) is list and all(type(p) is str and p in c.PURPOSES for p in granted) and
               granted == sorted(set(granted)) and
               (decoded["status"] == "CLEARED" or not granted),
               "RIGHTS_PURPOSE", "Invalid purpose grant")
        reviewed = c.utc(decoded["reviewed_utc"])
        effective = c.utc(decoded["effective_utc"])
        expires = c.utc(decoded["expires_utc"])
        c.need(reviewed <= effective < expires and
               (last_review_time is None or reviewed >= last_review_time) and
               (last_effective_time is None or effective >= last_effective_time),
               "RIGHTS_TIME", "Malformed review/effective/expiry chronology")
        c.need(subject is None or decoded["subject"] == subject,
               "RIGHTS_LINEAGE", "Mixed subjects in one chain")
        c.need(item.subject == decoded["subject"] and item.status == decoded["status"] and
               item.reviewer == decoded["reviewer"] and item.reviewed_utc == decoded["reviewed_utc"],
               "RIGHTS_LINEAGE", "Metadata does not match sealed values")
        subject = decoded["subject"]
        last_review_time = reviewed
        last_effective_time = effective
        previous_sha = item.sha256
        observed.append(decoded)
    c.need(previous_sha == expected_head,
           "RIGHTS_LINEAGE", "Chain head does not match external anchor")
    return tuple(observed)


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    status: str  # Only 'SIMULATED_ELIGIBLE_ONLY' is success in invented scenarios.
    purpose: str
    rights_sha256: str
    assurance: str = c.ASSURANCE


def evaluate_rights(*, chain: tuple[RightsDecision, ...], expected_head: str,
                    subject: str, purpose: str, as_of_utc: str) -> EligibilityDecision:
    c.toy(subject, "subject")
    c.need(type(purpose) is str and purpose in c.PURPOSES,
           "RIGHTS_PURPOSE", "Never authorize model training or C0 via this lab")
    as_of = c.utc(as_of_utc)
    history = verify_rights_chain(chain, expected_head=expected_head)
    c.need(history[-1]["subject"] == subject, "RIGHTS_SUBJECT", "Unrelated rights chain")
    # The most recent decision at or before time applies. Later amendments cannot
    # retroactively establish earlier clearance, even if a prior grant expired.
    applicable = [d for d in history if c.utc(d["effective_utc"]) <= as_of]
    c.need(bool(applicable), "RIGHTS_UNKNOWN", "No effective rights decision")
    latest = applicable[-1]
    c.need(as_of < c.utc(latest["expires_utc"]), "RIGHTS_EXPIRED", "Decision expired")
    c.need(latest["status"] != "BLOCKED", "RIGHTS_BLOCKED", "Source blocked")
    c.need(latest["status"] == "CLEARED", "RIGHTS_UNKNOWN", "Uncleared source")
    c.need(purpose in latest["purposes"], "RIGHTS_PURPOSE", "Purpose not granted")
    return EligibilityDecision("SIMULATED_ELIGIBLE_ONLY", purpose, expected_head)
