"""Offline EPL demonstration report. No data acquisition or model execution."""

from datetime import datetime
from fractions import Fraction
import math
import re

from .odds_observations import price
from .poisson import MAX_GOAL_CAP, poisson_distribution
from .settlement import parse_handicap

DEMO = "INVENTED_DEMONSTRATION"
MAX_OMITTED_MASS = 1e-10
# Mirrors the existing Poisson mass roundoff budget. A display guard, not
# a formally certified floating-point error bound.
ROUNDING_GUARD = Fraction(5, 10**12)
_REQUIRED = {"status", "fixture_id", "home", "away", "home_rate", "away_rate",
             "statistics", "side", "handicap"}
_OPTIONAL = {"decimal_odds", "source_reference", "observed_at_utc", "kickoff_utc"}


def _text(value, limit=120):
    if type(value) is not str or not 1 <= len(value) <= limit or not value.isprintable():
        raise ValueError("Expected bounded printable demonstration text.")
    return value


def _utc(value):
    if type(value) is not str or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value
    ):
        raise ValueError("Timestamp must be UTC text ending in Z.")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _number(value):
    try:
        return f"{float(value):.10g}"
    except OverflowError:
        return "outside floating-point display range"


def _verdict(lines, verdict, reason):
    return "\n".join([*lines, f"Verdict: {verdict}", f"Explanation: {reason}"])


def render_report(record: dict, *, max_goals: int = MAX_GOAL_CAP) -> str:
    """Render one invented report; malformed inputs return INSUFFICIENT_DATA.

    Statistics are bounded caller-supplied text and never influence rates.
    The required status is a declaration, not independent provenance.
    """
    lines = ["EPL | INVENTED DEMONSTRATION | No proven real-world betting edge."]
    try:
        if type(record) is not dict or not _REQUIRED <= record.keys() <= _REQUIRED | _OPTIONAL:
            raise ValueError("Missing or unsupported report fields.")
        if record["status"] != DEMO:
            raise ValueError("Explicit invented demonstration status required.")
        fixture = _text(record["fixture_id"])
        if not re.fullmatch(r"toy:[a-z0-9][a-z0-9_-]{0,70}", fixture):
            raise ValueError("Use an invented toy: fixture ID.")
        home, away = _text(record["home"]), _text(record["away"])
        if home.strip().casefold() == away.strip().casefold() or not home.strip() or not away.strip():
            raise ValueError("Supply two distinct invented teams.")
        stats = record["statistics"]
        if type(stats) is not dict or len(stats) > 16:
            raise ValueError("Use an object with up to 16 statistical summaries.")
        summaries = sorted((_text(k, 60), _text(v)) for k, v in stats.items())
        side = record["side"]
        if side not in ("home", "away"):
            raise ValueError("Select home or away.")
        line = _text(record["handicap"], 24)
        quarter = parse_handicap(line)
        if abs(quarter) > 80:
            raise ValueError("Handicap must be within ±20 goals.")
        source = record.get("source_reference")
        if source is not None:
            _text(source)
        observed = record.get("observed_at_utc")
        kickoff = record.get("kickoff_utc")
        if kickoff is not None:
            _utc(kickoff)
        if observed is not None and (kickoff is None or _utc(observed) >= _utc(kickoff)):
            raise ValueError("Observation must precede the supplied UTC kickoff.")
        home_rate, away_rate = record["home_rate"], record["away_rate"]
        if type(home_rate) not in (int, float) or type(away_rate) not in (int, float):
            raise ValueError("Supply numeric demonstration rates.")
    except (TypeError, ValueError, OverflowError) as exc:
        return _verdict(lines, "INSUFFICIENT_DATA", str(exc))

    lines.extend([f"Match: {home} vs {away} ({fixture})",
                  "Pre-match summaries (caller supplied, unverified; not used in probabilities):"])
    lines.extend(f"  {key}: {value}" for key, value in summaries)
    if not summaries:
        lines.append("  None supplied")
    if source is not None:
        lines.append(f"Source reference (caller supplied, unverified): {source}")
    if observed is not None:
        lines.append(f"Observation (caller supplied, unverified): {observed}")
    if kickoff is not None:
        lines.append(f"Kickoff (caller supplied, unverified): {kickoff}")
    lines.append(f"AH selection: {side.upper()} ({home if side == 'home' else away}) {line} ({quarter} quarter units)")
    try:
        dist = poisson_distribution(home_rate, away_rate, tolerance=MAX_OMITTED_MASS, max_goals=max_goals)
        tail = dist.mass.omitted_mass_bound
        if not math.isfinite(tail) or not 0 <= tail <= MAX_OMITTED_MASS:
            raise ArithmeticError("Omitted mass exceeds the demonstration tolerance.")
        outcome = dist.one_x_two()
        ah = dist.asian_handicap(side, quarter)
    except (TypeError, ValueError, ArithmeticError) as exc:
        return _verdict(lines, "INSUFFICIENT_DATA", str(exc))

    lines.extend([
        f"Expected-goal inputs (invented): home {_number(dist.lambda_home)}, away {_number(dist.lambda_away)}",
        f"Retained mass: {_number(dist.mass.retained_mass)}; omitted mass bound: {_number(tail)} (unrenormalized)",
        f"1X2 probabilities: home {_number(outcome.home_win)}, draw {_number(outcome.draw)}, away {_number(outcome.away_win)}",
        "AH probabilities: " + ", ".join(f"{label} {_number(value)}" for label, value in
            (("full win", ah.fw), ("half win", ah.hw), ("push", ah.push),
             ("half loss", ah.hl), ("full loss", ah.fl))),
    ])
    win = Fraction(ah.fw) + Fraction(ah.hw) / 2
    loss = Fraction(ah.fl) + Fraction(ah.hl) / 2
    lines.append("Model-implied fair decimal odds (retained mass): " +
                 (_number(1 + loss / win) if win else "undefined (zero winning weight)"))
    quote = record.get("decimal_odds")
    if quote is None:
        return _verdict(lines, "INSUFFICIENT_DATA", "No bookmaker price supplied; no market-edge claim.")
    try:
        gain = price(quote, "DECIMAL") - 1
    except (TypeError, ValueError) as exc:
        return _verdict(lines, "INSUFFICIENT_DATA", f"Invalid decimal price: {exc}")
    lines.append(f"Bookmaker decimal odds (caller supplied, unverified demonstration): {quote}")
    ev = gain * win - loss
    guard = ROUNDING_GUARD * max(1, gain) if dist.lambda_home or dist.lambda_away else 0
    low = ev - Fraction(tail) - guard
    high = ev + Fraction(tail) * gain + guard
    lines.append(f"Expected net return per unit (retained estimate): {_number(ev)}")
    lines.append(f"Tail and rounding allowance range: [{_number(low)}, {_number(high)}]")
    if ev == 0:
        return _verdict(lines, "DEMONSTRATION_NON_POSITIVE_EV",
                        "Break-even to numerical precision on retained mass; no positive EV claim.")
    if low > 0:
        return _verdict(lines, "DEMONSTRATION_POSITIVE_EV", "Positive under the invented assumptions only.")
    if high < 0:
        return _verdict(lines, "DEMONSTRATION_NON_POSITIVE_EV", "Negative under the invented assumptions.")
    return _verdict(lines, "INSUFFICIENT_DATA", "Omitted mass and rounding allowance leave the EV sign unresolved.")
