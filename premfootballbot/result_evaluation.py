"""Separate offline post-match analysis. No actual wagers or provenance certification."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from fractions import Fraction
import hashlib
import json
import math

from . import prospective_evidence as pe
from .odds_observations import (FrozenRecord, canonical, fields, fixture_fields,
                               need, seal, checked)
from .settlement import settle_handicap, calculate_payout
from .poisson import PoissonDistribution, truncated_poisson_distribution

RESULT_PROTOCOL = "pmb-final-result/v1"


def time(value):
    return datetime.fromisoformat(pe._utc(value, "time").replace("Z", "+00:00"))


def freeze_result(value, *, source_bytes=None):
    p = pe._load(value)
    fields(p, {"protocol", "league", "fixture_id", "home", "away", "kickoff_utc", "period", "status",
               "home_goals", "away_goals", "result_source_url", "result_source_content_sha256",
               "recorded_at_utc", "verified_at_utc", "license_status", "source_method", "reviewer",
               "operator", "previous_entry_sha256", "provenance_assurance"})
    need(p["protocol"] == RESULT_PROTOCOL and p["provenance_assurance"] == "LOCAL_ONLY", "Result protocol")
    fixture_fields(p)
    need(p["status"] in ("FINISHED_REGULATION", "UNKNOWN", "POSTPONED", "ABANDONED", "AWARDED", "EXTRA_TIME"), "Result status")
    if p["status"] == "FINISHED_REGULATION":
        need(all(type(p[k]) is int and 0 <= p[k] <= 99 for k in ("home_goals", "away_goals")), "Regulation integer goals required")
    else:
        need(p["home_goals"] is None and p["away_goals"] is None, "Unconfirmed/nonregulation scores forbidden")
    p["recorded_at_utc"] = pe._utc(p["recorded_at_utc"], "recorded")
    p["verified_at_utc"] = pe._optional_utc(p["verified_at_utc"], "verified")
    need(time(p["recorded_at_utc"]) >= time(p["kickoff_utc"]), "Result recorded before kickoff")
    if p["status"] == "FINISHED_REGULATION":
        need(time(p["recorded_at_utc"]) >= time(p["kickoff_utc"]) + timedelta(minutes=90), "Impossible regulation finish")
    need(p["verified_at_utc"] is None or p["verified_at_utc"] >= p["recorded_at_utc"], "Review predates result")
    need(p["license_status"] in ("CLEARED", "UNKNOWN", "BLOCKED"), "License status")
    need(p["source_method"] in ("MANUAL_TRANSCRIPTION", "RETAINED_SNAPSHOT"), "Source method")
    pe._url(p["result_source_url"], "result source")
    pe._id(p["operator"], "operator")
    if p["reviewer"] is not None:
        pe._id(p["reviewer"], "reviewer")
    if source_bytes is not None:
        need(type(source_bytes) is bytes and len(source_bytes) <= 4*1024*1024, "Result bytes")
        digest = hashlib.sha256(source_bytes).hexdigest()
        need(p["result_source_content_sha256"] in (None, digest), "Result source tamper")
        p["result_source_content_sha256"] = digest
    if p["result_source_content_sha256"] is not None:
        pe._digest(p["result_source_content_sha256"], "result hash")
    return seal(p)


@dataclass(frozen=True, slots=True)
class Evaluation:
    status: str
    canonical_bytes: bytes
    sha256: str


def output(status, **values):
    raw = canonical({"protocol": "pmb-offline-evaluation/v1", "status": status,
                     "assurance": "LOCAL_ONLY_EXTERNAL_AUDIT_REQUIRED", **values})
    return Evaluation(status, raw, hashlib.sha256(raw).hexdigest())


def packet_checked(packet):
    need(type(packet) is pe.FrozenEvidence, "Frozen forecast required")
    need(pe.freeze_packet(packet.canonical_bytes) == packet, "Frozen packet altered")
    return json.loads(packet.canonical_bytes)


def identity(p, fixture):
    need(all(p[k] == fixture[k] for k in ("fixture_id", "home", "away", "kickoff_utc")), "Fixture mismatch")


def approved(record, pins):
    need(type(pins) is tuple, "Externally provisioned immutable approval pins required")
    for pin in pins:
        pe._digest(pin, "approval pin")
    return record.sha256 in pins


def eligible_quote(q, record, forecast, pins, source_bytes):
    identity(q, forecast["fixture"])
    need(type(source_bytes) is bytes and hashlib.sha256(source_bytes).hexdigest() == q["source_content_sha256"], "Retained odds bytes required/mismatch")
    need(approved(record, pins) and q["rights_status"] == "CLEARED"
         and q["source_content_sha256"] is not None and q["claimed_observed_at_utc"] is not None
         and q["independent_observed_at_utc"] is not None, "Unapproved/missing odds evidence")
    need(max(q["captured_at_utc"], q["claimed_observed_at_utc"], q["independent_observed_at_utc"])
         <= min(forecast["cutoff_utc"], forecast["capture"]["captured_at_utc"])
         and q["timing_status"] == "PREMATCH_CAPTURE", "Late odds unsuitable")


def compare_1x2(packet, quotes: tuple[FrozenRecord, ...], *, approved_odds_sha256=(), source_bytes=None):
    f = packet_checked(packet)
    need(f["forecast"]["kind"] == "ONE_X_TWO", "NO_FORECAST excluded")
    need(type(quotes) is tuple and len(quotes) == 3, "Three quotes required")
    values = {}
    group = None
    for record in quotes:
        q = checked(record)
        need(q["protocol"] == "pmb-odds-observation/v1" and q["market"] == "1X2", "1X2 only")
        eligible_quote(q, record, f, approved_odds_sha256, source_bytes)
        key = tuple(q[k] for k in ("bookmaker", "snapshot_id", "source_url", "source_content_sha256",
                                   "captured_at_utc", "claimed_observed_at_utc", "independent_observed_at_utc"))
        need(group is None or group == key, "Mixed bookmaker/snapshot/times")
        group = key
        need(q["selection"] not in values, "Duplicate selection")
        values[q["selection"]] = 1 / Fraction(q["decimal_price_exact"])
    need(set(values) == {"HOME", "DRAW", "AWAY"}, "Incomplete group")
    total = sum(values.values())
    return output("COMPARABLE", forecast_sha256=packet.commitment_sha256,
                  odds_sha256=sorted(q.sha256 for q in quotes), overround=str(total - 1),
                  method="PROPORTIONAL_NO_VIG_NOT_OBJECTIVE_CHANCES",
                  no_vig={k: str(v/total) for k, v in values.items()},
                  model_minus_no_vig={k: str(Fraction(f["forecast"]["probabilities"][k.lower()])-v/total)
                                     for k,v in values.items()},
                  forecast_probabilities=f["forecast"]["probabilities"])


def verified_result(packet, result, pins, evaluated_at_utc, result_source_bytes, known_results):
    f = packet_checked(packet)
    r = checked(result)
    need(r["protocol"] == RESULT_PROTOCOL, "Separate result record required")
    identity(r, f["fixture"])
    evaluated = pe._utc(evaluated_at_utc, "evaluation time")
    need(evaluated >= r["recorded_at_utc"], "Evaluation predates result")
    conflict = False
    need(type(known_results) is tuple, "Immutable known-result history required")
    for prior in known_results:
        candidate = checked(prior)
        need(candidate["protocol"] == RESULT_PROTOCOL, "Result history type")
        identity(candidate, f["fixture"])
        if candidate["status"] == "FINISHED_REGULATION" and (candidate["home_goals"], candidate["away_goals"]) != (r["home_goals"], r["away_goals"]):
            conflict = True
    ok = (not conflict and type(result_source_bytes) is bytes
          and hashlib.sha256(result_source_bytes).hexdigest() == r["result_source_content_sha256"] and r["status"] == "FINISHED_REGULATION" and r["verified_at_utc"] is not None
          and r["verified_at_utc"] <= evaluated and r["reviewer"] is not None
          and r["reviewer"].casefold() != r["operator"].casefold()
          and r["license_status"] == "CLEARED" and r["result_source_content_sha256"] is not None
          and approved(result, pins))
    return f, r, ok, evaluated


def score_1x2(packet, result, *, evaluation_timestamp_utc, approved_result_sha256=(), result_source_bytes=None, known_results=()):
    f, r, verified, evaluated = verified_result(packet, result, approved_result_sha256, evaluation_timestamp_utc, result_source_bytes, known_results)
    refs = dict(forecast_sha256=packet.commitment_sha256, result_sha256=result.sha256,
                evaluation_timestamp_utc=evaluated, n=0)
    if f["forecast"]["kind"] == "NO_FORECAST":
        return output("EXCLUDED_NO_FORECAST", **refs)
    if not verified:
        return output("PENDING", **refs)
    actual = "home" if r["home_goals"] > r["away_goals"] else "away" if r["home_goals"] < r["away_goals"] else "draw"
    p = {k: Fraction(v) for k, v in f["forecast"]["probabilities"].items()}
    brier = sum((v - int(k == actual))**2 for k, v in p.items())
    probability = p[actual]
    loss = "POSITIVE_INFINITY" if probability == 0 else math.log(probability.denominator) - math.log(probability.numerator)
    refs["n"] = 1
    return output("SCORED", **refs, actual=actual, brier_unscaled=str(brier), brier_range="[0,2]",
                  log_loss=loss, log_base="natural", zero_probability_policy="POSITIVE_INFINITY_NO_CLIPPING")


def summarize(evaluations: tuple[Evaluation, ...]):
    scored, pending, excluded = [], 0, 0
    seen = set()
    for value in evaluations:
        need(type(value) is Evaluation, "Evaluation type")
        p = json.loads(value.canonical_bytes)
        need(value == output(p.pop("status"), **{k:v for k,v in p.items() if k not in ("protocol", "assurance")}), "Evaluation tampered")
        status = value.status
        p = json.loads(value.canonical_bytes)
        need(p["forecast_sha256"] not in seen, "Duplicate forecast evaluation")
        seen.add(p["forecast_sha256"])
        if status == "SCORED":
            scored.append(p)
        elif status == "PENDING":
            pending += 1
        else:
            need(status == "EXCLUDED_NO_FORECAST", "Only 1X2 scores may be summarized")
            excluded += 1
    n = len(scored)
    return output("SUMMARY", n=n, pending=pending, excluded=excluded,
                  mean_brier_unscaled=str(sum(Fraction(p["brier_unscaled"]) for p in scored)/n) if n else None,
                  mean_log_loss=("POSITIVE_INFINITY" if any(p["log_loss"] == "POSITIVE_INFINITY" for p in scored)
                                 else math.fsum(p["log_loss"] for p in scored)/n) if n else None)


def settle_ah(packet, quote, result, *, evaluation_timestamp_utc, approved_odds_sha256=(), odds_source_bytes=None, approved_result_sha256=(), result_source_bytes=None, known_results=()):
    f, r, ok, evaluated = verified_result(packet, result, approved_result_sha256, evaluation_timestamp_utc, result_source_bytes, known_results)
    q = checked(quote)
    need(q["market"] == "AH", "AH quote required")
    eligible_quote(q, quote, f, approved_odds_sha256, odds_source_bytes)
    refs = dict(forecast_sha256=packet.commitment_sha256, odds_sha256=quote.sha256,
                result_sha256=result.sha256, evaluation_timestamp_utc=evaluated,
                interpretation="HYPOTHETICAL_UNIT_NET_NOT_ACTUAL_WAGERING_ROI")
    if f["forecast"]["kind"] == "NO_FORECAST":
        return output("EXCLUDED_NO_FORECAST", **refs)
    if not ok:
        return output("PENDING", **refs)
    settlement = settle_handicap(r["home_goals"], r["away_goals"], q["selection"].lower(), q["handicap_q"])
    # Existing payout is also exposed for the documented rounded display price;
    # authoritative net uses exact converted rational and existing split fractions.
    display_net = calculate_payout(settlement, decimal_odds=q["decimal_price"]).net_per_unit
    exact_net = settlement.win * (Fraction(q["decimal_price_exact"]) - 1) - settlement.loss
    return output("SETTLED_HYPOTHETICAL", **refs, outcome=settlement.outcome.value,
                  unit_net_exact=str(exact_net), display_price_payout=str(display_net),
                  win=str(settlement.win), refund=str(settlement.refund), loss=str(settlement.loss))


def ah_model_value(quote, distribution):
    q = checked(quote)
    need(q["market"] == "AH" and type(distribution) is PoissonDistribution, "AH and existing Poisson required")
    replay = truncated_poisson_distribution(distribution.lambda_home, distribution.lambda_away,
                home_cap=distribution.home_cap, away_cap=distribution.away_cap)
    need(replay == distribution, "Poisson distribution tampered")
    p = distribution.asian_handicap(q["selection"].lower(), q["handicap_q"])
    d = Fraction(q["decimal_price_exact"])
    gain = float(d - 1)
    net = (p.fw + p.hw/2)*gain - p.hl/2 - p.fl
    bound = p.mass.omitted_mass_bound
    return output("HYPOTHETICAL_MODEL_ANALYSIS", odds_sha256=quote.sha256,
                  retained_unit_net=net, lower_unit_net=net-bound,
                  upper_unit_net=net+bound*gain, probabilities={k:getattr(p,k) for k in ("fw","hw","push","hl","fl")},
                  mass=asdict(p.mass), interpretation="RAW_TRUNCATED_MODEL_NOT_ACTUAL_WAGERING_ROI")
