"""Offline prospective shadow adapter. LOCAL_ONLY, unvalidated, no publication.

Trust pins are supplied by the owner AFTER independent external review. This
module checks consistency with those pins; it cannot authenticate human review,
source truth or time. Never derive trusted pins automatically from received data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext, ROUND_FLOOR
import hashlib
import json
import math

from . import prospective_evidence as evidence
from .poisson import poisson_distribution
from .real_epl_training import (
    RealFitConfig, RetrospectiveFit, retrospective_json, verify_retrospective_fit,
)

VERSION = "phase3da-shadow-v2"
# Fixed authorization reference extracted from reviewed artifact e8a2ec2b...;
# never populated from the incoming model or a runtime-generated allowlist.
MODEL_AUTHORIZATION_VERSION = "semantic-replay-v1"
APPROVED_MODEL_SEMANTIC_SHA256 = "ec38297fd59fd07c2a17e8731c24d4afd01ea6c0b723910ff1de22b4e9f62b6e"
PARAMETER_ABSOLUTE_TOLERANCE = 1e-10
# mu, home advantage, then attack/vulnerability pairs in exact approved team order.
APPROVED_PARAMETERS = (
    0.3279383736516415,
    0.19645606772885943,
    -0.09861759881618003,
    0.09261504298211536,
    0.37105629242144816,
    -0.6282267021039395,
    0.2202811553168286,
    0.020398088350135356,
    -0.06631518125442817,
    0.06533406257557185,
    -0.08529758443835615,
    0.019930571452037405,
    -0.34041257886426857,
    0.22857207551663222,
    0.2344171774887096,
    0.051629323192751826,
    -0.05499624154622818,
    -0.04120321302760128,
    -0.3815668776978394,
    -0.17251841954978536,
    -0.08603544612158733,
    0.004619423276712955,
    0.3248223995144698,
    -0.3361856518169696,
    -0.11998784042762727,
    0.3199757983113809,
    0.4269374299162588,
    -0.49168040868462976,
    -0.05499624154622813,
    -0.04120321302760129,
    0.32941226532404616,
    0.04267787887154333,
    -0.18803422511128287,
    0.08891754427932076,
    -0.45929423093414457,
    0.5044586513804096,
    0.19461920145367975,
    0.018871441467081744,
    0.005030408366965267,
    0.19211967228509388,
    -0.17102228304423178,
    0.0608980342697444,
)
TAIL_TOLERANCE = 1e-10
ROUNDOFF_LIMIT = 5e-12
MAX_REVIEW_AGE = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class ShadowDecision:
    status: str
    reason: str
    report_bytes: bytes
    report_sha256: str
    packet: evidence.FrozenEvidence | None


class _Abstain(ValueError):
    pass


def _need(condition, reason):
    if not condition:
        raise _Abstain(reason)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _approved_model_semantics(model):
    """Additional fixed approval gate AFTER exact local artifact replay.

    Only runtime/optimizer diagnostics may vary freely across runtimes; exact
    replay still authenticates those fields. Parameter drift is bounded against
    a fixed reviewed reference, never accepted by rounded-hash self-approval.
    """
    payload = json.loads(retrospective_json(model))
    parameters = [payload["intercept"], payload["home_advantage"]]
    for key in ("sha256", "runtime", "diagnostics", "intercept", "home_advantage"):
        payload.pop(key)
    for team in payload["teams"]:
        parameters.extend((team.pop("attack"), team.pop("defense_vulnerability")))
    return (_sha(_json(payload)) == APPROVED_MODEL_SEMANTIC_SHA256
            and len(parameters) == len(APPROVED_PARAMETERS)
            and all(type(x) in (int, float) and math.isfinite(x)
                    and abs(x - reference) <= PARAMETER_ABSOLUTE_TOLERANCE
                    for x, reference in zip(parameters, APPROVED_PARAMETERS)))


def _time(value):
    return datetime.fromisoformat(evidence._utc(value, "UTC time").replace("Z", "+00:00"))


def _quantize(raw):
    # Explicit conditioning, never silently change the underlying Poisson module.
    with localcontext() as ctx:
        ctx.prec = 60
        values = [Decimal(str(x)) for x in raw]
        total = sum(values)
        units = [x / total * 10**15 for x in values]
        floors = [int(x.to_integral_value(rounding=ROUND_FLOOR)) for x in units]
        remainder = 10**15 - sum(floors)
        _need(0 <= remainder <= 2, "NUMERICAL_MASS")
        order = sorted(range(3), key=lambda i: (-(units[i] - floors[i]), i))
        for i in order[:remainder]:
            floors[i] += 1
        return tuple(format(Decimal(x) / 10**15, ".15f") for x in floors)


def forecast_shadow(model: RetrospectiveFit, raw_bytes: bytes, *, license_bytes: bytes,
                    snapshot_bytes: bytes, review_bytes: bytes,
                    approved_review_sha256: tuple[str, ...] = (),
                    team_mapping: tuple[tuple[str, str], ...], cutoff_utc: str,
                    model_acquired_at_utc: str, operator: str) -> ShadowDecision:
    """Return a forecast or fail-closed abstention, without reading files/clock.

snapshot_bytes is a manually checked JSON fixture transcription. review_bytes
binds its SHA256, fixture, source, rights, reviewer and expiry. Trusted review
digests must arrive separately from an independently reviewed owner registry.
No registry is bundled. Receipt assurance always remains LOCAL_ONLY.
"""
    report = {"version": VERSION, "assurance": "LOCAL_ONLY",
              "model_status_preserved": "RETROSPECTIVE_DESCRIPTIVE_ONLY",
              "predictive_validity": "UNESTABLISHED", "external_audit_required": True,
              "training_season": "2023-24", "model_warning": "Stale season baseline; not validated for future EPL fixtures",
              "probability_policy": "conditional_retained_mass_largest_remainder_15dp",
              "tail_tolerance": TAIL_TOLERANCE,
              "model_authorization": MODEL_AUTHORIZATION_VERSION,
              "approved_semantic_sha256": APPROVED_MODEL_SEMANTIC_SHA256}
    fixture = review = None
    forecast = {"kind": "NO_FORECAST"}
    model_meta = None
    try:
        cutoff = _time(cutoff_utc)
        evidence._id(operator, "operator")
        _need(type(snapshot_bytes) is bytes and type(review_bytes) is bytes, "EVIDENCE_TYPE")
        report.update(snapshot_sha256=_sha(snapshot_bytes), review_sha256=_sha(review_bytes))
        _need(type(approved_review_sha256) is tuple and len(approved_review_sha256) <= 1000,
              "TRUST_REGISTRY")
        for pin in approved_review_sha256:
            evidence._digest(pin, "trusted review pin")
        _need(report["review_sha256"] in approved_review_sha256, "UNAPPROVED_REVIEW")
        r = evidence._load(review_bytes)
        evidence._fields(r, {"fixture", "snapshot_sha256", "source_url", "license_status",
                             "license_reference", "acquired_at_utc", "reviewed_at_utc",
                             "valid_until_utc", "reviewer"}, set(), "review")
        evidence._digest(r["snapshot_sha256"], "snapshot hash")
        _need(r["snapshot_sha256"] == report["snapshot_sha256"], "SNAPSHOT_MISMATCH")
        f = evidence._load(snapshot_bytes)
        evidence._fields(f, {"fixture_id", "league", "home", "away", "kickoff_utc", "status"}, set(), "fixture snapshot")
        _need(f == r["fixture"], "FIXTURE_MISMATCH")
        _need(f["league"] == "EPL" and f["status"] == "SCHEDULED", "UNSUPPORTED_FIXTURE")
        evidence._id(f["fixture_id"], "fixture_id")
        for key in ("home", "away"):
            evidence._text(f[key], key, length=90, ascii_only=True)
        _need(f["home"].casefold() != f["away"].casefold(), "TEAM_IDENTITY")
        kickoff = _time(f["kickoff_utc"])
        acquired, reviewed, expiry = (_time(r[k]) for k in
                                      ("acquired_at_utc", "reviewed_at_utc", "valid_until_utc"))
        _need(acquired <= reviewed <= cutoff < expiry <= kickoff and cutoff < kickoff,
              "EVIDENCE_TIMING")
        _need(cutoff - reviewed <= MAX_REVIEW_AGE, "STALE_REVIEW")
        reviewer = evidence._id(r["reviewer"], "reviewer")
        _need(reviewer.casefold() != operator.casefold(), "INDEPENDENT_REVIEW_REQUIRED")
        evidence._url(r["source_url"], "source_url")
        evidence._url(r["license_reference"], "license_reference")
        _need(r["license_status"] == "CLEARED", "RIGHTS_NOT_CLEARED")
        # Only after evidence is valid can a trustworthy local fixture envelope
        # be emitted, including NO_FORECAST on downstream failure.
        fixture, review = f, r
        report["cutoff_utc"] = evidence._utc(cutoff_utc, "cutoff")
        _need(type(model) is RetrospectiveFit, "MODEL_TYPE")
        verify_retrospective_fit(model, raw_bytes, license_bytes=license_bytes)
        _need(model.config == RealFitConfig(), "UNAPPROVED_MODEL_CONFIG")
        _need(_approved_model_semantics(model), "UNAPPROVED_MODEL_ARTIFACT")
        model_time = _time(model_acquired_at_utc)
        _need(model.source_import.source.retrieved_at_utc <= model_time <= cutoff,
              "MODEL_ACQUISITION")
        last_training_date = max(row.match_date for row in model.source_import.rows)
        _need(last_training_date < model_time.date() and last_training_date < cutoff.date(),
              "HISTORICAL_TARGET")
        report.update(model_sha256=model.sha256, model_bytes_sha256=_sha(retrospective_json(model)),
                      model_acquired_at_utc=evidence._utc(model_acquired_at_utc, "model acquisition"))
        _need(type(team_mapping) is tuple and 2 <= len(team_mapping) <= 20, "TEAM_MAPPING")
        mapping = {}
        for item in team_mapping:
            _need(type(item) is tuple and len(item) == 2, "TEAM_MAPPING")
            name, trained = item
            evidence._text(name, "mapped team", length=90, ascii_only=True)
            evidence._text(trained, "training team", length=90, ascii_only=True)
            _need(name.casefold() not in {n.casefold() for n in mapping}
                  and trained not in mapping.values(), "TEAM_MAPPING")
            mapping[name] = trained
        teams = {t.team: t for t in model.teams}
        _need(all(t in teams for t in mapping.values()), "UNSUPPORTED_TEAM")
        _need(f["home"] in mapping and f["away"] in mapping, "UNSUPPORTED_TEAM")
        report["team_mapping"] = sorted(mapping.items())
        h, a = teams[mapping[f["home"]]], teams[mapping[f["away"]]]
        rates = (math.exp(model.intercept + model.home_advantage + h.attack + a.defense_vulnerability),
                 math.exp(model.intercept + a.attack + h.defense_vulnerability))
        _need(all(math.isfinite(x) and 0 < x <= 100 for x in rates), "NUMERICAL_RATE")
        distribution = poisson_distribution(*rates, tolerance=TAIL_TOLERANCE, max_goals=512)
        p = distribution.one_x_two()
        raw = (p.home_win, p.draw, p.away_win)
        mass = p.mass
        _need(all(math.isfinite(x) for x in (*raw, *asdict(mass).values())), "NUMERICAL_MASS")
        _need(all(0 <= x <= 1 for x in raw) and 0 < mass.retained_mass <= 1 + ROUNDOFF_LIMIT
              and 0 <= mass.omitted_mass <= mass.omitted_mass_bound <= TAIL_TOLERANCE
              and abs(mass.mass_roundoff) <= ROUNDOFF_LIMIT
              and abs(math.fsum(raw) - mass.retained_mass) <= ROUNDOFF_LIMIT
              and abs(mass.retained_mass + mass.omitted_mass - 1) <= ROUNDOFF_LIMIT,
              "NUMERICAL_MASS")
        probabilities = _quantize(raw)
        report.update(rates=rates, raw_one_x_two=raw, mass=asdict(mass),
                      goal_caps=(distribution.home_cap, distribution.away_cap),
                      emitted_probabilities=probabilities,
                      maximum_adjustment=max(abs(float(q) - v) for q, v in zip(probabilities, raw)))
        config_digest = _sha(_json({"model_sha256": model.sha256, "mapping": sorted(mapping.items()),
                                    "version": VERSION, "tail_tolerance": TAIL_TOLERANCE,
              "model_authorization": MODEL_AUTHORIZATION_VERSION,
              "approved_semantic_sha256": APPROVED_MODEL_SEMANTIC_SHA256}))
        model_meta = {"name": "offline-epl-shadow", "version": VERSION, "config_sha256": config_digest}
        forecast = {"kind": "ONE_X_TWO", "probabilities": dict(zip(("home", "draw", "away"), probabilities))}
        reason = "ELIGIBLE_LOCAL_SHADOW"
    except _Abstain as error:
        reason = str(error)
    except (ValueError, TypeError, OverflowError, KeyError, AttributeError) as error:
        reason = "INVALID_INPUT_OR_MODEL:" + type(error).__name__
    success = forecast["kind"] == "ONE_X_TWO"
    report.update(status="SHADOW_FORECAST" if success else "ABSTAIN", reason=reason)
    report_bytes = _json(report)
    digest = _sha(report_bytes)
    packet = None
    if fixture is not None:
        def ref(source_id, url, sha, acquired, rights="UNKNOWN", license_ref=None, observed=None):
            return {"source_id": source_id, "source_url": url, "content_sha256": sha,
                    "license_status": rights, "license_reference": license_ref,
                    "acquired_at_utc": acquired, "source_available_at_utc": None,
                    "verified_by_external_observer_at_utc": observed}
        refs = [ref("kickoff-review", review["source_url"], _sha(review_bytes),
                    review["acquired_at_utc"], "CLEARED", review["license_reference"], review["reviewed_at_utc"]),
                ref("shadow-audit", "local://shadow/audit", digest, cutoff_utc)]
        if success:
            refs.append(ref("model-artifact", "local://shadow/model", report["model_bytes_sha256"], model_acquired_at_utc))
        try:
            # Recorder arithmetic uses Decimal; isolate from caller precision.
            with localcontext() as context:
                context.prec = 60
                packet = evidence.freeze_packet({"protocol": evidence.VERSION, "league": "EPL", "assurance": "LOCAL_ONLY",
                    "fixture": {"fixture_id": fixture["fixture_id"], "home": fixture["home"], "away": fixture["away"],
                                "kickoff_utc": fixture["kickoff_utc"], "kickoff_source_url": review["source_url"],
                                "kickoff_observed_at_utc": review["acquired_at_utc"]},
                    "cutoff_utc": cutoff_utc, "inputs": refs, "forecast": forecast, "model": model_meta,
                    "capture": {"captured_at_utc": cutoff_utc, "operator": operator, "method": "offline_file", "local_only": True}})
        except evidence.EvidenceError:
            report.update(status="ABSTAIN", reason="RECORDER_REJECTED")
            report_bytes = _json(report)
            digest = _sha(report_bytes)
    return ShadowDecision(report["status"], report["reason"], report_bytes, digest, packet)
