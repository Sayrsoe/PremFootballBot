"""Contract validation, provenance and deterministic synthetic import tests."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import hashlib
import json
from itertools import permutations
import unittest

from premfootballbot.match_data import (
    MatchDataError, canonical_content, parse_synthetic_json,
    select_as_of, snapshot_manifest, summarize_coverage,
)
from tests.match_data_cases import FIXTURE, document, encode, one_result

class ImportContractTests(unittest.TestCase):
    def parse(self, payload):
        return parse_synthetic_json(encode(payload))

    def reject(self, payload, code=None):
        result = self.parse(payload)
        self.assertFalse(result.valid)
        self.assertTrue(result.errors)
        self.assertEqual(result.observations, ())
        self.assertIsNone(result.content_sha256)
        if code:
            self.assertIn(code, {issue.code for issue in result.errors})
        with self.assertRaises(MatchDataError):
            result.require_valid()
        with self.assertRaises(MatchDataError):
            canonical_content(result)
        with self.assertRaises(MatchDataError):
            select_as_of(result, datetime(2027,1,1,tzinfo=timezone.utc))
        return result

    def test_complete_synthetic_fixture_and_zero_score(self):
        result = parse_synthetic_json(FIXTURE.read_bytes()).require_valid()
        self.assertEqual(len(result.observations),7)
        zero = result.observations[1]
        self.assertEqual((zero.home_goals_90,zero.away_goals_90),(0,0))
        self.assertEqual(zero.kickoff_utc.tzinfo,timezone.utc)
        self.assertEqual({i.code for i in result.warnings},{"UNKNOWN_AVAILABILITY","COARSE_KICKOFF"})

    def test_fixture_and_document_are_explicitly_synthetic(self):
        payload = document()
        self.assertTrue(all(r["is_synthetic"] for r in payload["records"]))
        source = payload["source_documents"][0]
        self.assertEqual(source["source_checksum_sha256"],
                         hashlib.sha256(source["content_utf8"].encode()).hexdigest())
        self.assertIn("invented",source["content_utf8"])

    def test_bytes_only(self):
        with self.assertRaises(TypeError):
            parse_synthetic_json("{}")

    def test_malformed_utf8_and_json_are_structured(self):
        for data in (b"\xff",b"{",b"[]",b"null"):
            result = parse_synthetic_json(data)
            self.assertTrue(result.errors)
            self.assertFalse(result.observations)

    def test_duplicate_json_keys_and_nonfinite_numbers_rejected(self):
        for data in (b'{"schema_version":1,"schema_version":1}',
                     b'{"schema_version":NaN}',b'{"schema_version":Infinity}'):
            self.assertTrue(parse_synthetic_json(data).errors)

    def test_resource_guard(self):
        self.assertTrue(parse_synthetic_json(b" "*(4*1024*1024+1)).errors)

    def test_version_is_integer_one(self):
        for version in (True,1.0,0,2,"1"):
            payload = one_result()
            payload["schema_version"] = version
            self.reject(payload)
        payload = one_result(schema_version=2)
        self.reject(payload)

    def test_unknown_fields_are_errors_at_every_level(self):
        for location in ("envelope","record","team","document"):
            payload = one_result()
            target = {"envelope":payload,"record":payload["records"][0],
                      "team":payload["teams"][0],"document":payload["source_documents"][0]}[location]
            target["odds"] = 1.9
            self.reject(payload,"UNKNOWN_FIELD")

    def test_missing_required_fields(self):
        payload = one_result()
        for key in list(payload["records"][0]):
            if key in ("supersedes_revision","match_date","home_team_name_raw","away_team_name_raw"):
                continue
            broken = deepcopy(payload)
            del broken["records"][0][key]
            with self.subTest(field=key):
                self.reject(broken,"MISSING_FIELD")

    def test_envelope_container_types(self):
        for field in ("teams","source_documents","records"):
            for value in ({},None,"rows"):
                payload = one_result()
                payload[field] = value
                self.reject(payload)

    def test_record_must_be_object(self):
        payload = one_result()
        payload["records"] = [None,3,[]]
        self.reject(payload)

    def test_invalid_scores(self):
        for field in ("home_goals_90","away_goals_90"):
            for value in (-1,True,False,1.0,"1",None):
                with self.subTest(field=field,value=value):
                    self.reject(one_result(**{field:value}))

    def test_unplayed_statuses_have_no_score_sentinel(self):
        for status in ("SCHEDULED","TIMED","IN_PLAY","POSTPONED","CANCELLED",
                       "ABANDONED","AWARDED","SUSPENDED"):
            payload = one_result(record_type="fixture",status=status,
                                 home_goals_90=None,away_goals_90=None,result_basis=None)
            self.assertTrue(self.parse(payload).valid,status)
            self.reject(one_result(record_type="fixture",status=status))

    def test_finished_requires_result_and_ft90(self):
        self.reject(one_result(record_type="fixture"))
        for basis in (None,"ET","PENALTIES","ft90"):
            self.reject(one_result(result_basis=basis))
        self.reject(one_result(status="AWARDED"))
        self.reject(one_result(record_type="unknown"))
        self.reject(one_result(status="PAUSED"))

    def test_season_and_competition(self):
        for year in (True,1991,9999,2026.0,"2026",-1):
            self.reject(one_result(season_start_year=year))
        for league in ("PL","EFL",None):
            self.reject(one_result(competition_code=league))

    def test_season_is_explicit_not_inferred_from_date(self):
        self.assertTrue(self.parse(one_result(season_start_year=2019)).valid)

    def test_unknown_same_and_wrong_namespace_teams(self):
        payload = one_result()
        home = payload["records"][0]["home_team_id"]
        for team in (home,"synthetic:demo:team:unknown","real:team:amber",True):
            self.reject(one_result(away_team_id=team))

    def test_exact_alias_matching_and_raw_names_retained(self):
        payload = one_result()
        payload["teams"][0]["aliases"].append("Amber Alias")
        payload["records"][0]["home_team_name_raw"]="Amber Alias"
        parsed=self.parse(payload).require_valid()
        self.assertEqual(parsed.observations[0].home_team_name_raw,"Amber Alias")
        self.reject(one_result(home_team_name_raw="amber test xi"))
        self.reject(one_result(home_team_name_raw="Violet Test XI"))

    def test_ambiguous_aliases_and_duplicate_teams(self):
        payload = one_result()
        payload["teams"][1]["aliases"].append("Amber Test XI")
        self.reject(payload)
        payload = one_result()
        payload["teams"].append(deepcopy(payload["teams"][0]))
        self.reject(payload)

    def test_synthetic_namespace_is_mandatory(self):
        payload = one_result()
        payload["namespace"] = "real:demo"
        self.reject(payload)
        for field in ("fixture_id","source_id","source_record_id","source_document_id","source_terms_id"):
            self.reject(one_result(**{field:"synthetic:other:x"}))
        for value in (False,1,"true"):
            self.reject(one_result(is_synthetic=value))

    def test_source_content_checksum_verified(self):
        payload = one_result()
        payload["source_documents"][0]["content_utf8"] += " changed"
        self.reject(payload,"SOURCE_CHECKSUM")
        self.reject(one_result(source_checksum_sha256="z"*64))

    def test_source_registration_and_provenance_must_match(self):
        self.reject(one_result(source_document_id="synthetic:demo:document:unknown"))
        self.reject(one_result(source_checksum_sha256="0"*64))
        self.reject(one_result(source_terms_id="synthetic:demo:terms:other"))
        self.reject(one_result(licence_status="UNKNOWN"))
        payload = one_result()
        payload["source_documents"].append(deepcopy(payload["source_documents"][0]))
        self.reject(payload)

    def test_unknown_and_blocked_licences_retained_with_warning(self):
        for state in ("UNKNOWN","BLOCKED"):
            payload=one_result(licence_status=state)
            payload["source_documents"][0]["licence_status"]=state
            result=self.parse(payload).require_valid()
            self.assertIn("LICENCE_NOT_CLEARED",{i.code for i in result.warnings})
            self.assertEqual(result.observations[0].licence_status,state)

    def test_timestamps_require_exact_aware_microsecond_precision(self):
        for field in ("kickoff_utc","available_at_utc","retrieved_at_utc"):
            for bad in ("2026-08-01","2026-08-01T14:00:00",
                        "2026-08-01T14:00:00-00:00",
                        "2026-08-01T14:00:00.1234567Z",
                        "2026-13-01T14:00:00Z",True):
                self.reject(one_result(**{field:bad}))

    def test_offsets_normalize_to_utc_including_dst_boundary(self):
        payload=one_result(kickoff_utc="2026-10-25T01:30:00+01:00",
                           available_at_utc="2026-10-25T02:30:00+00:00")
        row=self.parse(payload).require_valid().observations[0]
        self.assertEqual(row.kickoff_utc.isoformat(),"2026-10-25T00:30:00+00:00")
        self.assertEqual(row.available_at_utc-row.kickoff_utc,
                         timedelta(hours=2))

    def test_result_publication_lower_bound_and_retrieval(self):
        self.reject(one_result(available_at_utc="2026-08-01T15:29:59Z"))
        self.assertTrue(self.parse(one_result(available_at_utc="2026-08-01T15:30:00Z")).valid)
        self.reject(one_result(retrieved_at_utc="2026-08-01T15:59:59Z"))

    def test_fixture_notice_after_kickoff_is_valid(self):
        payload=one_result(record_type="fixture",status="POSTPONED",
                           home_goals_90=None,away_goals_90=None,result_basis=None)
        self.assertTrue(self.parse(payload).valid)

    def test_coarse_and_unknown_kickoff_are_auditable(self):
        for precision,date in (("date_only","2026-08-01"),("unknown",None)):
            result=self.parse(one_result(kickoff_utc=None,kickoff_precision=precision,
                                         match_date=date)).require_valid()
            self.assertIn("COARSE_KICKOFF",{i.code for i in result.warnings})
        self.reject(one_result(kickoff_precision="date_only",match_date="2026-08-01"))
        self.reject(one_result(kickoff_utc=None,kickoff_precision="date_only",match_date=None))
        self.reject(one_result(kickoff_precision="guessed"))
        self.reject(one_result(match_date="2026-08-02"))

    def test_unknown_availability_is_never_filled_from_retrieval(self):
        row=self.parse(one_result(available_at_utc=None)).require_valid().observations[0]
        self.assertIsNone(row.available_at_utc)

    def test_datetime_range_overflow_is_structured_error(self):
        self.reject(one_result(kickoff_utc="9999-12-31T23:59:59Z"))
        self.reject(one_result(kickoff_utc="0001-01-01T00:00:00+01:00"))

    def test_immutable_outputs(self):
        batch=self.parse(one_result()).require_valid()
        for target,field in ((batch,"namespace"),(batch.observations[0],"revision"),
                             (batch.teams[0],"team_id"),(batch.source_documents[0],"licence_status")):
            with self.assertRaises(FrozenInstanceError):
                setattr(target,field,"changed")
        with self.assertRaises(TypeError):
            batch.observations[0]=None

    def test_identical_duplicates_idempotent(self):
        payload=one_result()
        payload["records"]*=3
        result=self.parse(payload).require_valid()
        self.assertEqual(len(result.observations),1)
        self.assertEqual(result.duplicates_removed,2)
        self.assertIn("DUPLICATE_REMOVED",{i.code for i in result.warnings})
        self.assertEqual(result.content_sha256,self.parse(one_result()).content_sha256)

    def test_duplicate_different_retrieval_keeps_earliest(self):
        payload=one_result()
        later=deepcopy(payload["records"][0])
        later["retrieved_at_utc"]="2026-10-27T01:00:00Z"
        payload["records"].append(later)
        result=self.parse(payload).require_valid()
        self.assertEqual(result.duplicates_removed,1)
        self.assertEqual(result.observations[0].retrieved_at_utc.day,26)

    def test_conflicting_duplicate_is_atomic(self):
        payload=one_result()
        row=deepcopy(payload["records"][0])
        row["home_goals_90"]=1
        payload["records"].append(row)
        self.reject(payload,"CONFLICTING_DUPLICATE")

    def test_revision_chain_is_complete_and_append_only(self):
        payload=document()
        payload["records"]=[r for r in payload["records"] if r["fixture_id"].endswith(":a")]
        self.assertTrue(self.parse(payload).valid)
        for field,value in (("revision",4),("supersedes_revision",0),
                            ("home_team_id","synthetic:demo:team:violet")):
            bad=deepcopy(payload)
            bad["records"][-1][field]=value
            self.reject(bad)
        self.reject(one_result(revision=1,supersedes_revision=0))
        self.reject(one_result(revision=True))
        self.reject(one_result(supersedes_revision=False))

    def test_revision_identity_and_time_cannot_backdate(self):
        payload=document()
        payload["records"]=[r for r in payload["records"] if r["fixture_id"].endswith(":a")]
        for field,value in (("season_start_year",2025),
                            ("source_record_id","synthetic:demo:record:other"),
                            ("available_at_utc","2026-08-01T15:59:59Z")):
            bad=deepcopy(payload)
            bad["records"][-1][field]=value
            self.reject(bad,"REVISION_CHAIN")

    def test_valid_and_invalid_rows_do_not_leak_partial_batch(self):
        payload=document()
        payload["records"][0]["away_team_id"]=None
        self.reject(payload)

    def test_error_report_order_deterministic(self):
        payload=one_result(home_goals_90=-1)
        other=deepcopy(payload["records"][0])
        other["fixture_id"]="synthetic:demo:fixture:z"
        other["source_record_id"]="synthetic:demo:record:z"
        other["home_goals_90"]=True
        payload["records"].append(other)
        first=self.parse(payload)
        payload["records"].reverse()
        self.assertEqual(first.issues,self.parse(payload).issues)

    def test_conflicting_duplicate_reports_are_order_independent(self):
        payload=one_result()
        other=deepcopy(payload["records"][0])
        other["fixture_id"]="synthetic:demo:fixture:z"
        payload["records"].append(other)
        first=self.reject(payload,"CONFLICTING_DUPLICATE")
        payload["records"].reverse()
        self.assertEqual(first.issues,self.reject(payload).issues)

    def test_invalid_registry_reports_are_order_independent(self):
        payload=one_result()
        first=deepcopy(payload["source_documents"][0])
        second=deepcopy(first)
        first["source_checksum_sha256"]="0"*64
        second["source_document_id"]="synthetic:demo:document:z"
        second["licence_status"]="INVALID"
        payload["source_documents"]=[first,second]
        before=self.reject(payload)
        payload["source_documents"].reverse()
        self.assertEqual(before.issues,self.reject(payload).issues)

    def test_invalid_unicode_and_deep_nesting_are_structured(self):
        self.assertTrue(parse_synthetic_json(b"["*2000+b"]"*2000).errors)
        for depth in (100,500,900,980,990,1000):
            # Exercise registry sorting as well as the JSON decoder depth guard.
            data=(b'{"schema_version":1,"namespace":"synthetic:demo",'
                  b'"teams":['+b'['*depth+b'0'+b']'*depth+
                  b'],"source_documents":[],"records":[]}')
            self.assertTrue(parse_synthetic_json(data).errors)
        payload=one_result(home_team_name_raw="\ud800")
        data=json.dumps(payload,ensure_ascii=True).encode("utf8")
        self.assertTrue(parse_synthetic_json(data).errors)

    def test_observation_count_guard(self):
        payload=document()
        payload["records"]=[{}]*10001
        self.reject(payload,"SIZE")

    def test_registry_and_observation_nested_types_rejected(self):
        for field in ("status","record_type","licence_status","source_id",
                      "home_team_id","kickoff_precision","match_date"):
            for value in ([],{}):
                self.reject(one_result(**{field:value}))

    def test_revision_availability_cannot_tie(self):
        payload=one_result()
        next_row=deepcopy(payload["records"][0])
        next_row.update(revision=1,supersedes_revision=0,home_goals_90=1)
        payload["records"].append(next_row)
        self.reject(payload,"REVISION_CHAIN")

class DeterminismCoverageTests(unittest.TestCase):
    def test_registry_permutations_and_alias_order(self):
        payload=one_result()
        doc=deepcopy(payload["source_documents"][0])
        doc["source_document_id"]="synthetic:demo:document:extra"
        payload["source_documents"].append(doc)
        payload["teams"][0]["aliases"].append("Alias Amber")
        first=parse_synthetic_json(encode(payload)).require_valid()
        payload["source_documents"].reverse()
        payload["teams"].reverse()
        for team in payload["teams"]:
            team["aliases"].reverse()
        second=parse_synthetic_json(encode(payload)).require_valid()
        self.assertEqual(first,second)

    def test_order_permutations_preserve_content_manifest_and_reports(self):
        payload=document()
        expected=parse_synthetic_json(encode(payload)).require_valid()
        # Independent permutations of all three container types.
        for offset in range(len(payload["records"])):
            changed=deepcopy(payload)
            changed["records"]=payload["records"][offset:]+payload["records"][:offset]
            changed["teams"].reverse()
            actual=parse_synthetic_json(encode(changed)).require_valid()
            self.assertEqual(canonical_content(actual),canonical_content(expected))
            self.assertEqual(actual.issues,expected.issues)
            self.assertEqual(snapshot_manifest(actual),snapshot_manifest(expected))
            self.assertEqual(summarize_coverage(actual),summarize_coverage(expected))

    def test_small_fixture_all_permutations(self):
        payload=document()
        rows=payload["records"][:3]
        hashes=set()
        for order in permutations(rows):
            payload["records"]=list(order)
            hashes.add(parse_synthetic_json(encode(payload)).require_valid().content_sha256)
        self.assertEqual(len(hashes),1)

    def test_stable_hash_excludes_retrieval_only(self):
        payload=one_result()
        first=parse_synthetic_json(encode(payload)).require_valid()
        payload["records"][0]["retrieved_at_utc"]="2026-11-01T01:00:00Z"
        second=parse_synthetic_json(encode(payload)).require_valid()
        self.assertEqual(first.content_sha256,second.content_sha256)
        self.assertNotEqual(snapshot_manifest(first),snapshot_manifest(second))
        self.assertEqual(first.content_sha256,hashlib.sha256(canonical_content(first)).hexdigest())
        payload["records"][0]["home_goals_90"]=1
        self.assertNotEqual(first.content_sha256,parse_synthetic_json(encode(payload)).content_sha256)

    def test_offset_equivalent_instants_have_same_hash(self):
        payload=one_result()
        first=parse_synthetic_json(encode(payload)).require_valid()
        payload["records"][0]["kickoff_utc"]="2026-08-01T21:00:00+07:00"
        self.assertEqual(first.content_sha256,parse_synthetic_json(encode(payload)).content_sha256)

    def test_partial_coverage_counts_fixtures_not_revisions(self):
        batch=parse_synthetic_json(FIXTURE.read_bytes()).require_valid()
        report=summarize_coverage(batch,expected_matches={2026:380})[0]
        self.assertEqual((report.fixture_count,report.observation_count),(4,7))
        self.assertEqual(report.eligible_results,1)
        self.assertEqual(report.unknown_availability,1)
        self.assertEqual(report.coarse_kickoffs,1)
        self.assertEqual(report.fixture_completeness,"partial")
        self.assertEqual(dict(report.status_counts),
                         {"AWARDED":1,"FINISHED":2,"TIMED":1})

    def test_coverage_expected_counts_are_explicit(self):
        batch=parse_synthetic_json(encode(one_result())).require_valid()
        self.assertEqual(summarize_coverage(batch)[0].fixture_completeness,"unknown")
        self.assertEqual(summarize_coverage(batch,expected_matches={2026:1})[0].result_completeness,"complete")
        for value in (True,-1,0,1.0):
            with self.assertRaises((TypeError,ValueError)):
                summarize_coverage(batch,expected_matches={2026:value})
        missing=summarize_coverage(batch,expected_matches={2027:2})
        self.assertEqual(missing[1].fixture_count,0)
        self.assertEqual(missing[1].fixture_completeness,"partial")

    def test_repeated_import_is_deterministic_and_has_no_clock(self):
        data=FIXTURE.read_bytes()
        self.assertEqual(parse_synthetic_json(data),parse_synthetic_json(data))

    def test_empty_records_valid(self):
        payload=document()
        payload["records"]=[]
        batch=parse_synthetic_json(encode(payload)).require_valid()
        self.assertEqual(summarize_coverage(batch),())
        self.assertEqual(batch.observations,())

if __name__=="__main__":
    unittest.main()
