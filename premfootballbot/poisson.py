"""Fixed-rate independent-Poisson probabilities with explicit truncation.

There is no rate fitting, normalization, odds/EV calculation or data access.
Joint calculations support rates 0..100 and inclusive goal caps 0..512.
The scalar poisson_pmf also supports the numerical demonstration at rate 800.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

from .settlement import Outcome, Side, settle_handicap

DEFAULT_TOLERANCE = 1e-10
MAX_GOAL_CAP = 512
MAX_DISTRIBUTION_RATE = 100.0
_MASS_ROUNDOFF_LIMIT = 5e-12


class GoalCapError(ValueError):
    """The requested tail target cannot be established within the goal cap."""


@dataclass(frozen=True, slots=True)
class MassSummary:
    """Unnormalized retained mass and separately evaluated omitted probability.

    omitted_mass is evaluated from positive tail terms, not rounded 1-CDF.
    It equals 1-retained_mass mathematically; float subtraction can lose its
    last bits. mass_roundoff is sum(raw difference masses)-retained_mass.
    omitted_mass_bound is a geometric upper bound with a float roundoff margin,
    not a formally directed-rounding/interval-arithmetic certificate.
    """

    retained_mass: float
    omitted_mass: float
    omitted_mass_bound: float
    mass_roundoff: float


@dataclass(frozen=True, slots=True)
class OneXTwoProbabilities:
    home_win: float
    draw: float
    away_win: float
    mass: MassSummary


@dataclass(frozen=True, slots=True)
class AsianHandicapProbabilities:
    side: Side
    handicap_q: int
    fw: float
    hw: float
    push: float
    hl: float
    fl: float
    mass: MassSummary


@dataclass(frozen=True, slots=True)
class PoissonDistribution:
    """Immutable rectangular distribution and a cached home-goal-difference PMF.

    home_pmf[i]*away_pmf[j] is the retained, unnormalized score-cell mass.
    difference_pmf starts at difference -away_cap and ends at home_cap.
    """

    lambda_home: float
    lambda_away: float
    home_pmf: tuple[float, ...]
    away_pmf: tuple[float, ...]
    difference_pmf: tuple[float, ...]
    mass: MassSummary

    @property
    def home_cap(self) -> int:
        return len(self.home_pmf) - 1

    @property
    def away_cap(self) -> int:
        return len(self.away_pmf) - 1

    def score_probability(self, home_goals: int, away_goals: int) -> float | None:
        """Return a retained score mass, or None when outside the chosen caps.

        None does not assert zero probability in the infinite Poisson model.
        """
        _count(home_goals, "home_goals")
        _count(away_goals, "away_goals")
        if home_goals > self.home_cap or away_goals > self.away_cap:
            return None
        return self.home_pmf[home_goals] * self.away_pmf[away_goals]

    def one_x_two(self) -> OneXTwoProbabilities:
        """Return raw H/D/A masses, whose sum is retained mass up to roundoff."""
        zero = self.away_cap
        return OneXTwoProbabilities(
            home_win=math.fsum(self.difference_pmf[zero + 1:]),
            draw=self.difference_pmf[zero],
            away_win=math.fsum(self.difference_pmf[:zero]),
            mass=self.mass,
        )

    def asian_handicap(self, side: Side, handicap_q: int) -> AsianHandicapProbabilities:
        """Aggregate the cached difference PMF with Phase 1A's sole classifier.

        Construct once and call for many lines; no grid/difference recomputation.
        """
        settle_handicap(0, 0, side, handicap_q)  # Shared validation, including bool.
        buckets: dict[Outcome, list[float]] = {outcome: [] for outcome in Outcome}
        for index, probability in enumerate(self.difference_pmf):
            if probability:
                difference = index - self.away_cap
                outcome = settle_handicap(
                    max(difference, 0), max(-difference, 0), side, handicap_q
                ).outcome
                buckets[outcome].append(probability)
        return AsianHandicapProbabilities(
            side=side, handicap_q=handicap_q,
            fw=math.fsum(buckets[Outcome.FULL_WIN]),
            hw=math.fsum(buckets[Outcome.HALF_WIN]),
            push=math.fsum(buckets[Outcome.PUSH]),
            hl=math.fsum(buckets[Outcome.HALF_LOSS]),
            fl=math.fsum(buckets[Outcome.FULL_LOSS]),
            mass=self.mass,
        )


def _real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not bool or text")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _rate(value: Real, name: str, *, joint: bool = False) -> float:
    rate = _real(value, name)
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    if joint and rate > MAX_DISTRIBUTION_RATE:
        raise ValueError(
            f"{name} exceeds the joint calculation limit {MAX_DISTRIBUTION_RATE:g}; "
            "use poisson_pmf for scalar extreme-rate checks"
        )
    return rate


def _count(value: int, name: str, *, bounded: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, not bool")
    if value < 0 or (bounded and value > MAX_GOAL_CAP):
        limit = f" between 0 and {MAX_GOAL_CAP}" if bounded else " nonnegative"
        raise ValueError(f"{name} must be{limit}")


def _log_pmf(goals: int, rate: float) -> float:
    if rate == 0:
        return 0.0 if goals == 0 else -math.inf
    if goals == 0:
        return -rate
    return math.fsum((-rate, goals * math.log(rate), -math.lgamma(goals + 1)))


def poisson_pmf(goals: int, rate: Real) -> float:
    """Evaluate P(goals) in log space; reject bool/noninteger/negative goals.

    rate is a finite nonnegative numbers.Real (e.g. int, float or Fraction).
    Finite Decimal/text inputs are not implicitly coerced. Scalar rates are
    not subject to the joint rate-100 limit; extremely unrepresentable counts
    raise ValueError rather than returning a manufactured probability.
    """
    _count(goals, "goals")
    value = _rate(rate, "rate")
    try:
        result = math.exp(_log_pmf(goals, value))
    except (OverflowError, ValueError) as error:
        raise ValueError("goals/rate exceed the scalar floating-point range") from error
    if not math.isfinite(result):
        raise ValueError("goals/rate exceed the scalar floating-point range")
    return result


def _tail_bound(rate: float, cap: int) -> float:
    if rate == 0:
        return 0.0
    ratio = rate / (cap + 2)
    if ratio >= 1:
        return 1.0
    # Subsequent omitted-term ratios decrease, so their series is bounded by
    # p(cap+1)/(1-rate/(cap+2)). Calculate that bound in log space.
    margin = 64 * math.ulp(1.0) * (cap + 2)
    log_bound = (
        _log_pmf(cap + 1, rate) - math.log1p(-ratio) + math.log1p(margin)
    )
    if log_bound >= 0:
        return 1.0
    return min(1.0, math.nextafter(math.exp(log_bound), math.inf))


def _choose_cap(rate: float, target: float, max_goals: int) -> int:
    if rate == 0:
        return 0
    for cap in range(min(math.floor(rate), max_goals), max_goals + 1):
        if _tail_bound(rate, cap) <= target:
            return cap
    raise GoalCapError(
        f"max_goals={max_goals} cannot establish marginal tail <= {target:g} "
        f"for rate={rate:g}; increase the cap or relax tolerance"
    )


def _tail_sum(rate: float, cap: int) -> float:
    """Sum decreasing upper-tail terms; caller ensures cap >= floor(rate)."""
    term = math.exp(_log_pmf(cap + 1, rate))
    terms = [term]
    k = cap + 1
    for _ in range(4096):
        total = math.fsum(terms)
        following = term * rate / (k + 1)
        remaining = following / (1 - rate / (k + 2))
        if following == 0 or remaining <= math.ulp(total) / 4:
            return total
        terms.append(following)
        term = following
        k += 1
    raise ArithmeticError("upper-tail summation did not converge")


def _marginal(rate: float, cap: int) -> tuple[tuple[float, ...], float, float, float]:
    if rate == 0:
        return (1.0,) + (0.0,) * cap, 1.0, 0.0, 0.0
    probabilities = tuple(math.exp(_log_pmf(k, rate)) for k in range(cap + 1))
    if cap < math.floor(rate):
        cdf = math.fsum(probabilities)  # Retain very small lower tails directly.
        tail = 1 - cdf
    else:
        tail = _tail_sum(rate, cap)  # Avoid 1-CDF cancellation at the upper end.
        cdf = 1 - tail
    return probabilities, cdf, tail, _tail_bound(rate, cap)


def _union(first: float, second: float) -> float:
    return min(1.0, math.fsum((first, second, -first * second)))


def _distribution(home: float, away: float, home_cap: int, away_cap: int) -> PoissonDistribution:
    ph, ch, th, bh = _marginal(home, home_cap)
    pa, ca, ta, ba = _marginal(away, away_cap)
    differences = tuple(
        math.fsum(
            ph[j + d] * pa[j]
            for j in range(max(0, -d), min(away_cap, home_cap - d) + 1)
        )
        for d in range(-away_cap, home_cap + 1)
    )
    retained = ch * ca
    roundoff = math.fsum(differences) - retained
    if abs(roundoff) > _MASS_ROUNDOFF_LIMIT:
        raise ArithmeticError("PMF and tail mass disagree beyond float roundoff budget")
    return PoissonDistribution(
        lambda_home=home, lambda_away=away,
        home_pmf=ph, away_pmf=pa, difference_pmf=differences,
        mass=MassSummary(
            retained_mass=retained,
            omitted_mass=_union(th, ta),
            omitted_mass_bound=_union(bh, ba),
            mass_roundoff=roundoff,
        ),
    )


def poisson_distribution(
    lambda_home: Real,
    lambda_away: Real,
    *,
    tolerance: Real = DEFAULT_TOLERANCE,
    max_goals: int = MAX_GOAL_CAP,
) -> PoissonDistribution:
    """Build separate adaptive caps; bound combined omitted mass by tolerance.

    tolerance must be finite and strictly between 0 and 1. The cap is inclusive
    and must be an integer in 0..512. Joint rates are bounded to 0..100 to bound
    work to at most 513**2 products. Too-tight/unrepresentable targets raise
    GoalCapError. No probabilities are renormalized.
    """
    home = _rate(lambda_home, "lambda_home", joint=True)
    away = _rate(lambda_away, "lambda_away", joint=True)
    epsilon = _real(tolerance, "tolerance")
    if not 0 < epsilon < 1:
        raise ValueError("tolerance must be strictly between 0 and 1")
    _count(max_goals, "max_goals", bounded=True)
    home_cap = _choose_cap(home, epsilon / 2, max_goals)
    away_cap = _choose_cap(away, epsilon / 2, max_goals)
    result = _distribution(home, away, home_cap, away_cap)
    if result.mass.omitted_mass_bound > epsilon:
        raise GoalCapError("combined tail bound exceeds requested tolerance")
    return result


def truncated_poisson_distribution(
    lambda_home: Real,
    lambda_away: Real,
    *,
    home_cap: int,
    away_cap: int,
) -> PoissonDistribution:
    """Build specified inclusive caps, even if omitted mass is substantial.

    This explicit diagnostic API makes no tolerance promise. It retains raw
    cell masses and reports omitted mass and the same geometric bound.
    """
    home = _rate(lambda_home, "lambda_home", joint=True)
    away = _rate(lambda_away, "lambda_away", joint=True)
    _count(home_cap, "home_cap", bounded=True)
    _count(away_cap, "away_cap", bounded=True)
    return _distribution(home, away, home_cap, away_cap)
