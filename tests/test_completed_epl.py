"""Pinned CC0 results plus clearly invented malformed snippets; no model fitting."""
import ast
from dataclasses import replace, FrozenInstanceError
from datetime import datetime, date, timezone
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from premfootballbot import completed_epl as ce
from premfootballbot import openfootball_exploratory as old
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.expected_goals import fit_expected_goals, ExpectedGoalsError
from premfootballbot.backtesting import generate_forecasts, BacktestError
from premfootballbot.prospective_evidence import freeze_packet, EvidenceError
from tests.backtesting_cases import manifest

FIXTURE = Path(__file__).parent / 'fixtures/completed_epl'


def inputs():
    metadata = json.loads((FIXTURE/'SOURCES.json').read_text(encoding='utf8'))
    sources = [old.OpenFootballSource(**{**m,'retrieved_at_utc':datetime.fromisoformat(m['retrieved_at_utc'])}) for m in metadata]
    return tuple(ce.SeasonInput((FIXTURE/(s.path[:7]+'.txt')).read_bytes(),s) for s in sources)


def imported():
    return ce.import_completed_epl(inputs(),license_bytes=(FIXTURE/'LICENSE.md').read_bytes())


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=inputs(); cls.license=(FIXTURE/'LICENSE.md').read_bytes(); cls.dataset=imported()

    def call(self, values=None, license=None):
        return ce.import_completed_epl(self.inputs if values is None else values,
                                       license_bytes=self.license if license is None else license)

    def test_exact_blob_and_sha256(self):
        for item in self.inputs:
            raw=item.raw_bytes
            self.assertEqual(hashlib.sha256(raw).hexdigest(),item.source.expected_sha256)
            self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),item.source.expected_git_blob_sha)

    def test_complete760_and_each380(self):
        self.assertEqual(len(self.dataset.rows),760)
        for season in self.dataset.seasons:
            self.assertEqual(season.accepted_results,380)
            self.assertEqual(len(season.clubs),20)
            self.assertTrue(all(h==a==19 for _,h,a in season.appearances))
            self.assertEqual(season.round_counts,tuple((r,10) for r in range(1,39)))
            self.assertFalse(season.issues)

    def test_exact_directed_pairs(self):
        for year in (2024,2025):
            rows=[r for r in self.dataset.rows if r.original.season_start_year==year]
            pairs={(r.home_team_id,r.away_team_id) for r in rows}
            teams={r.home_team_id for r in rows}
            self.assertEqual(pairs,{(h,a) for h in teams for a in teams if h!=a})

    def test_explicit_aliases_and_promotion(self):
        aliases=dict(self.dataset.aliases)
        self.assertEqual(dict(aliases[2024])['AFC Bournemouth'],dict(aliases[2025])['Bournemouth'])
        self.assertEqual(dict(aliases[2024])['Arsenal FC'],dict(aliases[2025])['Arsenal'])
        a,b=(set(s.clubs) for s in self.dataset.seasons)
        self.assertEqual(a-b,{'ipswich','leicester','southampton'})
        self.assertEqual(b-a,{'leeds','burnley','sunderland'})

    def test_missing_halftime_not_invented(self):
        self.assertEqual(tuple(s.missing_halftime for s in self.dataset.seasons),(16,0))
        self.assertEqual(sum(r.original.halftime_score is None for r in self.dataset.rows),16)

    def test_date_coverage_and_score_totals(self):
        self.assertEqual([(s.earliest_date,s.latest_date,s.home_goals,s.away_goals) for s in self.dataset.seasons],
                         [('2024-08-16','2025-05-25',575,540),('2025-08-15','2026-05-24',580,465)])

    def test_temporal_restrictions_retained_everywhere(self):
        self.assertFalse(self.dataset.strict_point_in_time_eligible)
        for value in (self.dataset,*(r.original for r in self.dataset.rows)):
            self.assertEqual(value.record_kind,'NON_SYNTHETIC_REAL_ARCHIVE')
            self.assertEqual(value.evidence_status,'EXPLORATORY_DATE_LEVEL_RECONSTRUCTION')
            self.assertIsNone(value.historical_available_at)
            self.assertIsNone(value.kickoff_utc)
            self.assertFalse(value.strict_point_in_time_eligible)

    def test_raw_rows_and_source_locators(self):
        raw_by_year={int(i.source.path[:4]):i.raw_bytes.decode().splitlines() for i in self.inputs}
        for row in self.dataset.rows:
            r=row.original
            self.assertEqual(raw_by_year[r.season_start_year][r.source_line_number-1],r.raw_row)
            self.assertEqual(raw_by_year[r.season_start_year][r.date_header_line-1],r.raw_date_header)
            self.assertIn(ce.COMMIT,r.source_locator)

    def test_sort_by_actual_date_not_round(self):
        keys=[(r.original.season_start_year,r.original.match_date,r.home_team_id,r.away_team_id) for r in self.dataset.rows]
        self.assertEqual(keys,sorted(keys))
        rounds=[r.nominal_round for r in self.dataset.rows if r.original.season_start_year==2024]
        self.assertNotEqual(rounds,sorted(rounds))

    def test_repeat_and_input_order_reproducibility(self):
        self.assertEqual(ce.completed_json(self.dataset),ce.completed_json(self.call(tuple(reversed(self.inputs)))))
        self.assertEqual(self.dataset,self.call())

    def test_source_dictionary_order_irrelevant(self):
        s=self.inputs[0].source
        fields=old.asdict(s)
        other=old.OpenFootballSource(**dict(reversed(list(fields.items()))))
        self.assertEqual(self.dataset,self.call((replace(self.inputs[0],source=other),self.inputs[1])))

    def test_frozen_dataset_and_rows(self):
        for obj,field,value in ((self.dataset,'sha256','x'),(self.dataset.rows[0],'home_team_id','x')):
            with self.assertRaises(FrozenInstanceError): setattr(obj,field,value)

    def test_integrity_and_resealed_replay(self):
        row=replace(self.dataset.rows[0],home_team_id='forged')
        changed=replace(self.dataset,rows=(row,)+self.dataset.rows[1:])
        with self.assertRaises(ce.CompletedEplError): ce.completed_json(changed)
        with self.assertRaises(ce.CompletedEplError) as caught:
            ce.verify_completed_dataset(ce._seal(changed),self.inputs,license_bytes=self.license)
        self.assertEqual(caught.exception.code,'REPLAY_MISMATCH')

    def test_resealed_historical_certification_rejected(self):
        changed=ce._seal(replace(self.dataset,strict_point_in_time_eligible=True))
        with self.assertRaises(ce.CompletedEplError): ce.completed_json(changed)

    def test_resealed_row_certification_rejected(self):
        row=self.dataset.rows[0]
        row=replace(row,original=replace(row.original,strict_point_in_time_eligible=True))
        changed=ce._seal(replace(self.dataset,rows=(row,)+self.dataset.rows[1:]))
        with self.assertRaises(ce.CompletedEplError): ce.completed_json(changed)

    def test_exact_replay(self):
        self.assertTrue(ce.verify_completed_dataset(self.dataset,self.inputs,license_bytes=self.license))

    def test_duplicate_missing_or_partial_season(self):
        for values in ((), self.inputs[:1], (self.inputs[0],)*2, list(self.inputs)):
            with self.assertRaises(ce.CompletedEplError): self.call(values)

    def test_2026_partial_archive_not_admitted(self):
        item=replace(self.inputs[0],source=replace(self.inputs[0].source,path='2026-27/1-premierleague.txt'))
        with self.assertRaises(ce.CompletedEplError) as caught: self.call((item,self.inputs[1]))
        self.assertEqual(caught.exception.code,'UNSUPPORTED_SEASON')

    def test_source_identity_licensing_and_missing_bytes(self):
        for field,value in (('repository_commit_sha','a'*40),('expected_git_blob_sha','b'*40),
                            ('expected_sha256','c'*64),('licence_id','UNKNOWN'),
                            ('licence_evidence_url','https://example.org'),('repository_url','https://example.org')):
            item=replace(self.inputs[0],source=replace(self.inputs[0].source,**{field:value}))
            with self.subTest(field=field),self.assertRaises(ce.CompletedEplError): self.call((item,self.inputs[1]))
        for raw in (None,b'',b'\xff',self.inputs[0].raw_bytes+b'\n'):
            with self.assertRaises(ce.CompletedEplError): self.call((replace(self.inputs[0],raw_bytes=raw),self.inputs[1]))

    def test_wrong_or_missing_license_bytes(self):
        for raw in (b'',b'CC0',self.license+b'\n'):
            with self.assertRaises(ce.CompletedEplError): self.call(license=raw)

    def test_acquisition_not_backdated_as_history(self):
        for dt in (datetime(2024,1,1,tzinfo=timezone.utc),datetime(2026,10,30)):
            item=replace(self.inputs[0],source=replace(self.inputs[0].source,retrieved_at_utc=dt))
            with self.assertRaises(ce.CompletedEplError): self.call((item,self.inputs[1]))

    def test_no_network_files_clock_or_fitting(self):
        with patch('socket.socket',side_effect=AssertionError),patch('builtins.open',side_effect=AssertionError), \
             patch.object(Path,'read_bytes',side_effect=AssertionError),patch('premfootballbot.real_epl_training.fit_real_epl',side_effect=AssertionError):
            self.assertEqual(self.dataset,self.call())

    def test_synthetic_model_recorder_and_backtest_boundaries(self):
        raw=ce.completed_json(self.dataset)
        self.assertFalse(parse_synthetic_json(raw).valid)
        with self.assertRaises(ExpectedGoalsError): fit_expected_goals(self.dataset,datetime.now(timezone.utc))
        with self.assertRaises(BacktestError): generate_forecasts(self.dataset,manifest())
        with self.assertRaises(EvidenceError): freeze_packet(raw)

    def test_source_has_no_io_or_model_imports(self):
        tree=ast.parse(Path(ce.__file__).read_text(encoding='utf8'))
        imports=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import): imports.update(i.name for i in n.names)
            if isinstance(n,ast.ImportFrom): imports.add(n.module or '')
            if isinstance(n,ast.Call):
                self.assertNotIn(getattr(n.func,'attr',getattr(n.func,'id','')),('open','now','today','read_bytes','write_bytes','urlopen'))
        self.assertLessEqual(imports,{'__future__','collections','dataclasses','datetime','hashlib','re',''})


class NewProfileAdversarialTests(unittest.TestCase):
    def parse(self,body):
        # Explicitly invented snippets test the private grammar, never approved source pins.
        raw=('= English Premier League 2024/25\n'+body).encode()
        return ce._parse_2024(raw,inputs()[0].source)

    def test_v_layout_without_halftime(self):
        r=self.parse('Fri Aug 16 2024\nArsenal FC v Chelsea FC 2-1\n')[0]
        self.assertIsNone(r.halftime_score)
        self.assertEqual((r.home_goals_ft90,r.away_goals_ft90),(2,1))

    def test_january_rollover_and_weekday(self):
        r=self.parse('Wed Jan 1\nArsenal FC v Chelsea FC 0-0\n')[0]
        self.assertEqual(r.match_date,date(2025,1,1))

    def test_malformed_dates_never_inherit_previous_header(self):
        for header in ('Sat Aug 16','Feb 30','Aug','Jan 1 2024','Aug 16 2026'):
            with self.subTest(header=header),self.assertRaises(ce.CompletedEplError) as caught:
                self.parse('Fri Aug 16\nArsenal FC v Chelsea FC 1-0\n'+header+'\nLiverpool FC v Fulham FC 0-0\n')
            self.assertTrue(caught.exception.issues)

    def test_missing_date_unknown_alias_and_fixture_without_score(self):
        for body in ('Arsenal FC v Chelsea FC 1-0\n','Aug 16\nArsenall FC v Chelsea FC 1-0\n',
                     'Aug 16\nArsenal FC v Chelsea FC\n'):
            with self.assertRaises(ce.CompletedEplError): self.parse(body)

    def test_round_resets_date_and_invalid_round(self):
        for round_header in ('▪ Matchday 2','▪ Matchday 39'):
            with self.assertRaises(ce.CompletedEplError):
                self.parse('Aug 16\nArsenal FC v Chelsea FC 1-0\n'+round_header+'\nLiverpool FC v Fulham FC 0-0\n')

    def test_nonregulation_halftime_or_bad_clock(self):
        for line in ('Arsenal FC v Chelsea FC 0-0 (1-0)', 'Arsenal FC v Chelsea FC 1-0 awarded',
                     '25:00 Arsenal FC v Chelsea FC 1-0', 'Arsenal FC v Arsenal FC 1-0'):
            with self.assertRaises(ce.CompletedEplError): self.parse('Aug 16\n'+line+'\n')

    def test_duplicate_pair_and_missing_schedule_fail_with_lines(self):
        raw=inputs()[0].raw_bytes
        rows=ce._parse_2024(raw,inputs()[0].source)
        for changed in (rows[:-1],rows+(rows[0],),rows[:-1]+(rows[0],)):
            with self.assertRaises(ce.CompletedEplError) as caught:
                ce._normalize(changed,inputs()[0].source,2024,raw)
            self.assertTrue(caught.exception.issues)
        self.assertTrue(any(i.reason=='DUPLICATE_ORDERED_PAIR' and i.line>0 for i in caught.exception.issues))

    def test_alias_collision_rejected(self):
        for pairs in (ce.ALIASES_2024[:-1],ce.ALIASES_2024[:-1]+(ce.ALIASES_2024[0],),
                      ce.ALIASES_2024[:-1]+(('OTHER','arsenal'),)):
            with self.assertRaises(ce.CompletedEplError): ce._aliases(pairs)

    def test_modified_source_cannot_be_self_pinned(self):
        values=inputs(); raw=values[0].raw_bytes+b'\n'
        item=replace(values[0],raw_bytes=raw,source=replace(values[0].source,expected_sha256=hashlib.sha256(raw).hexdigest()))
        with self.assertRaises(ce.CompletedEplError): ce.import_completed_epl((item,values[1]),license_bytes=(FIXTURE/'LICENSE.md').read_bytes())


if __name__=='__main__': unittest.main()
