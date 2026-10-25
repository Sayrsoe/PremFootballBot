"""Reusable G01-G26 oracles from Phase 1 research, using fabricated results.

Expected outcomes/net returns were derived before the implementation. The
approved handoff's VERIFIED_GOLDEN_CASES.md independently reports 26/26 matches.
No production settlement helpers are used to generate these expectations.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    home: int
    away: int
    side: str
    handicap_q: int
    outcome: str
    net: str
    odds: str = "1.90"


GOLDEN_CASES = (
    GoldenCase("G01", 1, 1, "home", 1, "HW", "9/20"),
    GoldenCase("G02", 1, 1, "home", -1, "HL", "-1/2"),
    GoldenCase("G03", 0, 0, "away", 1, "HW", "9/20"),
    GoldenCase("G04", 0, 0, "away", -1, "HL", "-1/2"),
    GoldenCase("G05", 1, 0, "home", -3, "HW", "9/20"),
    GoldenCase("G06", 0, 1, "away", -3, "HW", "9/20"),
    GoldenCase("G07", 0, 1, "home", 3, "HL", "-1/2"),
    GoldenCase("G08", 1, 0, "away", 3, "HL", "-1/2"),
    GoldenCase("G09", 1, 0, "home", -4, "P", "0"),
    GoldenCase("G10", 0, 1, "away", -4, "P", "0"),
    GoldenCase("G11", 0, 0, "home", -2, "FL", "-1"),
    GoldenCase("G12", 0, 0, "away", 2, "FW", "9/10"),
    GoldenCase("G13", 2, 0, "home", -5, "FW", "9/10"),
    GoldenCase("G14", 1, 0, "home", -5, "HL", "-1/2"),
    GoldenCase("G15", 0, 1, "home", 5, "HW", "9/20"),
    GoldenCase("G16", 1, 0, "away", 5, "HW", "9/20"),
    GoldenCase("G17", 2, 0, "home", -7, "HW", "9/20"),
    GoldenCase("G18", 0, 2, "home", 7, "HL", "-1/2"),
    GoldenCase("G19", 2, 0, "home", -9, "HL", "-1/2"),
    GoldenCase("G20", 0, 2, "home", 9, "HW", "9/20"),
    GoldenCase("G21", 3, 0, "home", -9, "FW", "9/10"),
    GoldenCase("G22", 0, 3, "home", 9, "FL", "-1"),
    GoldenCase("G23", 3, 3, "home", 0, "P", "0"),
    GoldenCase("G24", 2, 1, "away", 0, "FL", "-1"),
    GoldenCase("G25", 1, 1, "home", 1, "HW", "3/5", "2.20"),
    GoldenCase("G26", 2, 0, "home", -5, "FW", "6/5", "2.20"),
)
