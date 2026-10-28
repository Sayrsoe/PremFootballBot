"""Invented archive snippets using inspected team labels, NOT historical results."""
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import unittest

from premfootballbot.openfootball_exploratory import (
    BANNER, LICENSE_BLOB, REPOSITORY, MAX_BYTES, MAX_LINES, MAX_LINE_LENGTH,
    OpenFootballSource, OpenFootballError, parse_openfootball_epl,
    summarize_exploratory_coverage, select_exploratory_prior_dates, exploratory_json,
)

COMMIT = "9ee7a0c351805c99cc334478a9bf04b7d0432fec"


def invented(body="", *, season=2023):
    title = "= English Premier League 2023/24" if season == 2023 else "= England | Premier League 2025/26"
    return (title + "\n# INVENTED TEST INPUT: not a published result archive\n" + body).encode("utf8")


def source_for(raw, *, season=2023, **changes):
    # Test pins are invented caller assertions; no claim these bytes are in COMMIT.
    value = OpenFootballSource(REPOSITORY, COMMIT,
        "2023-24/1-premierleague.txt" if season == 2023 else "2025-26/1-premierleague.txt",
        hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
        hashlib.sha256(raw).hexdigest(), "CC0-1.0",
        f"{REPOSITORY}/blob/{COMMIT}/LICENSE.md", LICENSE_BLOB,
        datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc))
    return replace(value, **changes)


def parse(body="", *, season=2023):
    raw = invented(body, season=season)
    return parse_openfootball_epl(raw, source=source_for(raw, season=season))


class ParserTests(unittest.TestCase):
    def reject(self, raw, code, source=None):
        with self.assertRaises(OpenFootballError) as caught:
            parse_openfootball_epl(raw, source=source_for(raw) if source is None else source)
        self.assertEqual(caught.exception.code, code)

    def test_centered_score_and_halftime_not_swapped(self):
        row = parse("Fri Aug 11\n  20:00 Arsenal FC  3-2 (1-0)  Chelsea FC\n").rows[0]
        self.assertEqual((row.home_goals_ft90, row.away_goals_ft90, row.halftime_score), (3, 2, (1, 0)))
        self.assertEqual(row.match_date, date(2023, 8, 11))
        self.assertEqual(row.raw_clock_text, "20:00")

    def test_v_separated_layout(self):
        row = parse("Fri Aug 11 2023\n  Arsenal FC v Chelsea FC  3-2 (1-0)\n").rows[0]
        self.assertEqual((row.home_team_raw, row.away_team_raw), ("Arsenal FC", "Chelsea FC"))
        self.assertEqual(row.halftime_score, (1, 0))

    def test_2025_profile_with_scorer_annotations(self):
        value = parse("Fri Aug 15 2025\n  19:00 Arsenal  2-1 (0-0)  Chelsea FC\n"
                      "                  (Invented Player 45+2';\n"
                      "                   Another Example 75'(p))\n", season=2025)
        self.assertEqual((len(value.rows), len(value.quarantined)), (1, 0))
        self.assertEqual(value.total_match_like_lines, 1)

    def test_multiword_punctuation_preserved(self):
        r = parse("Aug 11\nBrighton & Hove Albion FC  0-0  Wolverhampton Wanderers FC\n").rows[0]
        self.assertEqual(r.home_team_raw, "Brighton & Hove Albion FC")
        self.assertEqual(r.away_team_raw, "Wolverhampton Wanderers FC")
        self.assertIsNone(r.halftime_score)

    def test_missing_clock_and_raw_audit_locators(self):
        value = parse("Fri Aug 11\n   Arsenal FC  0-0  Chelsea FC   \n")
        row = value.rows[0]
        self.assertIsNone(row.raw_clock_text)
        self.assertEqual((row.source_line_number, row.date_header_line), (4, 3))
        self.assertEqual(row.raw_row, "   Arsenal FC  0-0  Chelsea FC   ")
        self.assertEqual(row.raw_date_header, "Fri Aug 11")
        self.assertTrue(row.source_locator.endswith("/2023-24/1-premierleague.txt#L4"))
        self.assertEqual(row.source_sha256, value.source.expected_sha256)

    def test_year_rollover_independent_of_input_order(self):
        value = parse("Mon Jan 1\nArsenal FC 1-1 Chelsea FC\nSun Dec 31\nLiverpool FC 2-0 Fulham FC\n")
        self.assertEqual([r.match_date for r in value.rows], [date(2023, 12, 31), date(2024, 1, 1)])

    def test_explicit_wrong_year_quarantined(self):
        value = parse("Jan 1 2023\nArsenal FC 1-0 Chelsea FC\n")
        self.assertEqual(value.quarantined[0].reason, "SEASON_DATE")
        self.assertFalse(value.rows)

    def test_ambiguous_and_invalid_dates_never_inherit_last_header(self):
        for header, reason in (("[Fri Aug/11]", "AMBIGUOUS_DATE"), ("Feb 30", "INVALID_DATE"),
                               ("Sat Aug 11", "WEEKDAY_MISMATCH"), ("Aug", "AMBIGUOUS_DATE")):
            with self.subTest(header=header):
                value = parse("Fri Aug 11\nArsenal FC 1-0 Chelsea FC\n" + header + "\nLiverpool FC 2-0 Fulham FC\n")
                self.assertEqual(len(value.rows), 1)
                self.assertEqual(value.quarantined[-1].reason, reason)
                self.assertEqual(value.header_issues[-1].reason, reason)

    def test_rounds_one_and_38_reset_date_context(self):
        value = parse("▪ Matchday 1\nFri Aug 11\nArsenal FC 1-0 Chelsea FC\n"
                      "▪ Matchday 38\nLiverpool FC 1-0 Fulham FC\n")
        self.assertEqual(len(value.rows), 1)
        self.assertEqual(value.quarantined[0].reason, "MISSING_DATE")
        value = parse("▪ Regular Season - 38\nSun May 24\nArsenal 1-0 Chelsea FC\n", season=2025)
        self.assertEqual(value.rows[0].match_date, date(2026, 5, 24))

    def test_unrecognized_competition_or_round_fails_atomically(self):
        for body in ("▪ FA Cup Final\n", "▪ Matchday 39\n"):
            self.reject(invented(body), "SECTION_HEADER")

    def test_halftime_exceeds_final_is_quarantined(self):
        self.assertEqual(parse("Aug 11\nArsenal FC 0-0 (1-0) Chelsea FC\n").quarantined[0].reason,
                         "HALFTIME_EXCEEDS_FT90")

    def test_malformed_scores_and_half_time_only_never_accepted(self):
        for score in ("-1-0", "100-0", "1.5-0", "?-?", "(1-0)", "1:0", "1-0 (x-y)"):
            with self.subTest(score=score):
                value = parse("Aug 11\nArsenal FC " + score + " Chelsea FC\n")
                self.assertFalse(value.rows)
                self.assertEqual(value.total_match_like_lines, 1)

    def test_bounded_goals_zero_and_99(self):
        value = parse("Aug 11\nArsenal FC 99-0 (0-0) Chelsea FC\n")
        self.assertEqual(value.rows[0].home_goals_ft90, 99)

    def test_unexpected_and_self_team_names(self):
        for home, away in (("Invented Aliens FC", "Chelsea FC"), ("Arsenal", "Chelsea FC"),
                           ("Arsenal FC", "Arsenal FC")):
            with self.subTest(home=home, away=away):
                value = parse(f"Aug 11\n{home} 1-0 {away}\n")
                self.assertEqual(value.quarantined[0].reason, "TEAM_IDENTITY")

    def test_status_markers_all_quarantined(self):
        for status in ("postponed", "abandoned", "awarded", "cancelled", "suspended", "a.e.t.", "pen."):
            with self.subTest(status=status):
                self.assertEqual(parse(f"Aug 11\nArsenal FC 1-0 Chelsea FC [{status}]\n").quarantined[0].reason,
                                 "NOT_FINISHED_FT90")

    def test_status_only_fixture_cannot_resurrect_prior_result(self):
        value = parse("Aug 11\nArsenal FC 1-0 Chelsea FC\nAug 13\nArsenal FC v Chelsea FC [postponed]\n")
        self.assertFalse(value.rows)
        self.assertEqual({q.reason for q in value.quarantined}, {"NOT_FINISHED_FT90", "REPEATED_PAIR_IDENTITY"})

    def test_exact_duplicates_all_quarantined(self):
        value = parse("Aug 11\nArsenal FC 1-0 Chelsea FC\nArsenal FC 1-0 Chelsea FC\n")
        self.assertEqual((len(value.rows), len(value.quarantined)), (0, 2))
        self.assertEqual({q.reason for q in value.quarantined}, {"REPEATED_PAIR_IDENTITY"})

    def test_corrected_goals_and_changed_date_conflict(self):
        for suffix in ("Aug 11\nArsenal FC 2-0 Chelsea FC\n", "Aug 13\nArsenal FC 1-0 Chelsea FC\n"):
            value = parse("Aug 11\nArsenal FC 1-0 Chelsea FC\n" + suffix)
            self.assertFalse(value.rows)
            self.assertEqual(len(value.quarantined), 2)

    def test_reverse_home_away_is_distinct_identity(self):
        value = parse("Aug 11\nArsenal FC 1-0 Chelsea FC\nAug 13\nChelsea FC 0-0 Arsenal FC\n")
        self.assertEqual(len({r.fixture_id for r in value.rows}), 2)

    def test_no_date_and_unknown_text_reported(self):
        value = parse("Arsenal FC 1-0 Chelsea FC\nunknown variant\n")
        self.assertEqual([q.reason for q in value.quarantined], ["MISSING_DATE", "UNRECOGNIZED_ROW"])

    def test_status_annotation_invalidates_preceding_row(self):
        value = parse("Aug 11\nArsenal FC 1-0 Chelsea FC\n                  (abandoned)\n")
        self.assertFalse(value.rows)
        self.assertEqual(value.quarantined[0].reason, "UNVERIFIED_ANNOTATION")

    def test_unsupported_date_heading_cannot_reuse_previous_date(self):
        value = parse("Aug 11\nArsenal FC 1-0 Chelsea FC\n2024-03-01\nLiverpool FC 2-0 Fulham FC\n")
        self.assertEqual(len(value.rows), 1)
        self.assertEqual(value.quarantined[-1].reason, "UNRECOGNIZED_DATE_CONTEXT")

    def test_standalone_award_note_invalidates_prior_score(self):
        value = parse("Aug 11\nArsenal FC 1-0 Chelsea FC\n[awarded]\n")
        self.assertFalse(value.rows)
        self.assertEqual(len(value.quarantined), 2)

    def test_invalid_clock_quarantined_not_timezone_corrected(self):
        for clock in ("24:00", "12:60"):
            self.assertEqual(parse(f"Aug 11\n{clock} Arsenal FC 1-0 Chelsea FC\n").quarantined[0].reason, "INVALID_CLOCK")

    def test_bom_crlf_supported_exact_hashes_differ_semantics_equal(self):
        raw = invented("Aug 11\nArsenal FC 1-0 Chelsea FC\n")
        alternate = b"\xef\xbb\xbf" + raw.replace(b"\n", b"\r\n")
        a = parse_openfootball_epl(raw, source=source_for(raw))
        b = parse_openfootball_epl(alternate, source=source_for(alternate))
        self.assertNotEqual(a.source.expected_sha256, b.source.expected_sha256)
        self.assertEqual(a.semantic_sha256, b.semantic_sha256)

    def test_wrong_encoding_and_controls_rejected(self):
        self.reject(invented() + b"\xff", "ENCODING")
        for char in (b"\0", b"\x0b", b"\xef\xbb\xbf"):
            self.reject(invented() + char, "TEXT_CONTROL")

    def test_input_bounds(self):
        self.reject(b"x" * (MAX_BYTES + 1), "INPUT_SIZE")
        self.reject(invented("x" * (MAX_LINE_LENGTH + 1)), "TEXT_BOUNDS")
        self.reject(invented("\n" * MAX_LINES), "TEXT_BOUNDS")
        self.reject(b"", "INPUT_SIZE")

    def test_wrong_input_type_and_missing_source(self):
        self.reject("not bytes", "INPUT_TYPE", source_for(b"x"))
        self.reject(b"x", "SOURCE_TYPE", {})

    def test_bad_hashes_and_document_tamper_atomic(self):
        raw = invented("Aug 11\nArsenal FC 1-0 Chelsea FC\n")
        src = source_for(raw)
        self.reject(raw + b"\n", "SHA256_MISMATCH", src)
        self.reject(raw, "GIT_BLOB_MISMATCH", replace(src, expected_git_blob_sha="1" * 40))
        self.reject(raw, "SHA256_MISMATCH", replace(src, expected_sha256="1" * 64))

    def test_source_hash_fields_full_immutable_lowercase(self):
        raw = invented()
        for field in ("repository_commit_sha", "expected_git_blob_sha", "expected_sha256"):
            for bad in ("main", "master", "abc", "0" * (64 if field == "expected_sha256" else 40), 42):
                with self.subTest(field=field, bad=bad):
                    self.reject(raw, "SOURCE_HASH", source_for(raw, **{field: bad}))

    def test_foreign_repo_path_traversal_and_unsupported_season(self):
        raw = invented()
        self.reject(raw, "REPOSITORY", source_for(raw, repository_url="https://github.com/attacker/england"))
        for path in ("../2023-24/1-premierleague.txt", "2023-25/1-premierleague.txt", "2023-24/2-championship.txt",
                     "/2023-24/1-premierleague.txt", "2024-25/1-premierleague.txt", "2023-24\\1-premierleague.txt"):
            self.reject(raw, "SOURCE_PATH", source_for(raw, path=path))

    def test_licence_spoof_and_mutable_evidence_fail(self):
        raw = invented()
        for changes in ({"licence_id": "MIT"}, {"licence_id": ""}, {"licence_blob_sha": "a" * 40},
                        {"licence_evidence_url": REPOSITORY + "/blob/master/LICENSE.md"},
                        {"licence_evidence_url": "https://example.com/CC0"}):
            self.reject(raw, "LICENCE", source_for(raw, **changes))

    def test_explicit_retrieval_aware_and_normalized(self):
        raw = invented()
        for bad in (None, datetime(2026, 1, 1), "2026-10-28"):
            self.reject(raw, "RETRIEVAL", source_for(raw, retrieved_at_utc=bad))
        a = parse_openfootball_epl(raw, source=source_for(raw))
        local = a.source.retrieved_at_utc.astimezone(timezone(timedelta(hours=7)))
        b = parse_openfootball_epl(raw, source=source_for(raw, retrieved_at_utc=local))
        self.assertEqual(a, b)

    def test_document_title_foreign_league_and_season_fail(self):
        for raw in (b"= FA Cup\n", b"= English Premier League 2025/26\n", invented("= Second Document\n")):
            self.reject(raw, "DOCUMENT_TITLE")

    def test_coverage_denominator_and_reasons(self):
        value = parse("Aug 11\n20:00 Arsenal FC 1-0 Chelsea FC\nLiverpool FC 2-0 Fulham FC\n"
                      "Arsenal FC v Everton FC [awarded]\nSat Aug 11\nBrentford FC 1-0 Burnley FC\n")
        report = summarize_exploratory_coverage(value)
        self.assertEqual((report.total_match_like_lines, report.accepted_rows, report.quarantined_rows), (4, 2, 2))
        self.assertEqual(report.total_lines, report.ignored_lines + report.total_match_like_lines)
        self.assertEqual((report.printed_clocks, report.missing_clocks), (1, 3))
        self.assertEqual((report.accepted_printed_clocks, report.accepted_missing_clocks), (1, 1))
        self.assertEqual(dict(report.reason_counts), {"NOT_FINISHED_FT90": 1, "WEEKDAY_MISMATCH": 1})
        self.assertEqual(report.strict_point_in_time_eligible_count, 0)
        self.assertEqual(report.historical_availability, "UNKNOWN")
        payload = json.loads(exploratory_json(report))
        self.assertEqual(payload["source"]["licence_blob_sha"], LICENSE_BLOB)
        self.assertIn(BANNER, exploratory_json(report).decode())

    def test_deterministic_json_and_frozen_snapshots(self):
        value = parse("Aug 11\nArsenal FC 1-0 Chelsea FC\n")
        self.assertEqual(exploratory_json(value), exploratory_json(parse("Aug 11\nArsenal FC 1-0 Chelsea FC\n")))
        with self.assertRaises(FrozenInstanceError):
            value.rows[0].home_goals_ft90 = 99
        for changed in (replace(value, rows=()), replace(value, source=replace(value.source, licence_id="MIT"))):
            with self.assertRaises(OpenFootballError) as caught:
                summarize_exploratory_coverage(changed)
            self.assertEqual(caught.exception.code, "SNAPSHOT_TAMPERED")

    def test_permutations_change_locators_but_preserve_semantics(self):
        first = "Aug 11\nArsenal FC 1-0 Chelsea FC\n"
        second = "Jan 1\nLiverpool FC 0-0 Fulham FC\n"
        a, b = parse(first + second), parse(second + first)
        self.assertNotEqual(a.sha256, b.sha256)
        self.assertEqual(a.semantic_sha256, b.semantic_sha256)
        self.assertEqual([r.fixture_id for r in a.rows], [r.fixture_id for r in b.rows])


if __name__ == "__main__":
    unittest.main()
