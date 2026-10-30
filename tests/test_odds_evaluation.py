from dataclasses import replace, FrozenInstanceError
from decimal import localcontext
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from premfootballbot import odds_observations as oo
from premfootballbot import result_evaluation as re
from premfootballbot.poisson import poisson_distribution, truncated_poisson_distribution
from premfootballbot.settlement import settle_handicap
from tests.odds_evaluation_cases import quote, result, trio, packet, scoring, RAW


class ConversionTests(unittest.TestCase):
    def test_invalid_quotes(self):
        for text in ('0','NaN','inf','1e2','1,5',' 2','2 ','âˆ’100','ï¼’','1/2','2.', '.5', True, 2.0, None):
            with self.subTest(text=text), self.assertRaises(ValueError):
                oo.price(text,'DECIMAL')

    def test_domains_and_explicit_notation(self):
        for form, text in ((None,'-100'),('UNKNOWN','2'),('DECIMAL','-100'),('AMERICAN','100'),
                           ('AMERICAN','-99'),('AMERICAN','+100.0'),('MALAY','-100'),('MALAY','1.1'),
                           ('INDONESIAN','0.9'),('INDONESIAN','-0.5'),('HONG_KONG','-1')):
            with self.subTest(form=form,text=text), self.assertRaises(ValueError):
                oo.price(text,form)

    def test_rational_recurring_display_not_authoritative(self):
        d=oo.price('-150','AMERICAN')
        self.assertEqual(d,Fraction(5,3))
        self.assertNotEqual(Fraction(oo.decimal_display(d)),d)

    def test_decimal_context_independence(self):
        expected=oo.freeze_odds(quote(raw_price='-150',price_format='AMERICAN'))
        with localcontext() as c:
            c.prec=3
            self.assertEqual(expected,oo.freeze_odds(quote(raw_price='-150',price_format='AMERICAN')))


VECTORS=[('DECIMAL','1.50','3/2'),('DECIMAL','2','2'),('AMERICAN','+200','3'),
         ('AMERICAN','-200','3/2'),('AMERICAN','-100','2'),('AMERICAN','+100','2'),
         ('HONG_KONG','0.87','187/100'),('HONG_KONG','2','3'),('MALAY','0.5','3/2'),
         ('MALAY','-0.5','3'),('MALAY','1','2'),('MALAY','-1','2'),
         ('INDONESIAN','2','3'),('INDONESIAN','-2','3/2'),('INDONESIAN','1','2'),('INDONESIAN','-1','2')]
def conversion_case(form, raw, expected):
    def test(self):
        self.assertEqual(oo.price(raw,form),Fraction(expected))
        record=oo.freeze_odds(quote(raw_price=raw,price_format=form))
        self.assertEqual(oo.checked(record)['decimal_price_exact'],str(Fraction(expected)))
        self.assertEqual(record,oo.freeze_odds(record.canonical_bytes))
    return test
for i,(form,raw,expected) in enumerate(VECTORS):
    setattr(ConversionTests,f'test_conversion_{i:02d}_{form.lower()}',conversion_case(form,raw,expected))


class RecordTests(unittest.TestCase):
    def test_strict_json(self):
        for raw in (b'{"protocol":"x","protocol":"x"}',b'{"a":NaN}',b'\xff',b'x'*65537):
            with self.assertRaises(ValueError): oo.freeze_odds(raw)

    def test_schema_boundaries(self):
        for change in ({'market':'TOTAL'},{'period':'EXTRA_TIME'},{'league':'UCL'},{'handicap_q':-100},
                        {'market':'AH','handicap_q':True},{'provenance_assurance':'VERIFIED'},
                        {'decimal_price':'999'},{'source_url':'https://u:p@example.org'},
                        {'claimed_observed_at_utc':'2027-01-09T12:00:00Z'}):
            with self.subTest(change=change), self.assertRaises(ValueError): oo.freeze_odds(quote(**change))

    def test_source_bytes_tampering(self):
        with self.assertRaises(ValueError): oo.freeze_odds(quote(),source_bytes=RAW+b'x')
        q=oo.freeze_odds(quote(source_content_sha256=None),source_bytes=RAW)
        self.assertEqual(oo.checked(q)['source_content_sha256'],hashlib.sha256(RAW).hexdigest())

    def test_missing_bytes_remain_unknown(self):
        q=oo.freeze_odds(quote(source_content_sha256=None))
        self.assertIsNone(oo.checked(q)['source_content_sha256'])

    def test_frozen_record_tampered(self):
        q=oo.freeze_odds(quote())
        with self.assertRaises(FrozenInstanceError): q.sha256='a'*64
        with self.assertRaises(ValueError): oo.checked(replace(q,sha256='a'*64))

    def test_complete_linked_chain_and_append(self):
        a=oo.freeze_odds(quote())
        b=oo.freeze_odds(quote(raw_price='3',previous_entry_sha256=a.sha256))
        chain=oo.append_record((a,),b)
        self.assertTrue(oo.validate_chain(chain,expected_head=b.sha256))
        for values in ((b,), (b,a), (a,a)):
            with self.assertRaises(ValueError): oo.validate_chain(values)

    def test_resealed_chain_requires_external_head(self):
        a=oo.freeze_odds(quote())
        b=oo.freeze_odds(quote(raw_price='3'))
        with self.assertRaises(ValueError): oo.validate_chain((b,),expected_head=a.sha256)

    def test_late_observation_stored_but_not_prematch(self):
        q=oo.freeze_odds(quote(captured_at_utc='2027-01-10T15:00:00Z',independent_observed_at_utc=None))
        self.assertEqual(oo.checked(q)['timing_status'],'LATE_UNSUITABLE_FOR_PREMATCH')


class ComparisonTests(unittest.TestCase):
    def test_complete_no_vig_exact(self):
        q=trio()
        report=json.loads(re.compare_1x2(packet(),q,source_bytes=RAW,approved_odds_sha256=tuple(x.sha256 for x in q)).canonical_bytes)
        self.assertEqual(report['overround'],'0')
        self.assertEqual(report['no_vig'],{'HOME':'1/2','DRAW':'1/4','AWAY':'1/4'})

    def test_overround(self):
        q=tuple(oo.freeze_odds(quote(selection=s,raw_price='2')) for s in ('HOME','DRAW','AWAY'))
        p=json.loads(re.compare_1x2(packet(),q,source_bytes=RAW,approved_odds_sha256=tuple(x.sha256 for x in q)).canonical_bytes)
        self.assertEqual(p['overround'],'1/2')
        self.assertEqual(set(p['no_vig'].values()),{'1/3'})

    def test_unapproved_local_hash_not_proof(self):
        with self.assertRaises(ValueError): re.compare_1x2(packet(),trio())

    def test_mixed_book_snapshot_time_fixture(self):
        for change in ({'bookmaker':'OTHER'},{'snapshot_id':'OTHER'},{'fixture_id':'OTHER'},
                        {'home':'OTHER'},{'captured_at_utc':'2027-01-09T10:31:00Z'},
                        {'source_content_sha256':'a'*64},{'rights_status':'UNKNOWN'},
                        {'independent_observed_at_utc':None}):
            q=list(trio()); q[0]=oo.freeze_odds(quote(**change))
            with self.subTest(change=change), self.assertRaises(ValueError):
                re.compare_1x2(packet(),tuple(q),source_bytes=RAW,approved_odds_sha256=tuple(x.sha256 for x in q))

    def test_duplicate_missing_and_AH_quotes_rejected(self):
        for q in (trio()[:2],(trio()[0],)*3,(oo.freeze_odds(quote(market='AH',handicap_q=-2)),*trio()[1:])):
            with self.assertRaises(ValueError): re.compare_1x2(packet(),q,source_bytes=RAW,approved_odds_sha256=tuple(x.sha256 for x in q))

    def test_quotes_after_forecast_capture_rejected(self):
        q=trio(captured_at_utc='2027-01-10T10:00:00Z',independent_observed_at_utc='2027-01-10T10:01:00Z')
        with self.assertRaises(ValueError): re.compare_1x2(packet(),q,source_bytes=RAW,approved_odds_sha256=tuple(x.sha256 for x in q))


class ScoringTests(unittest.TestCase):
    def test_known_conflicting_result_blocks_grading(self):
        r,kw=scoring()
        other=re.freeze_result(result(home_goals=0,away_goals=3))
        self.assertEqual(re.score_1x2(packet(),r,known_results=(other,),**kw).status,'PENDING')

    def test_retained_bytes_required_even_for_approved_hash(self):
        r,kw=scoring()
        for raw in (None,RAW+b'changed'):
            self.assertEqual(re.score_1x2(packet(),r,**{**kw,'result_source_bytes':raw}).status,'PENDING')

    def test_summary_pending_and_excluded_never_counted(self):
        r,kw=scoring()
        pending=re.score_1x2(packet(),r,evaluation_timestamp_utc=kw['evaluation_timestamp_utc'])
        excluded=re.score_1x2(packet(abstain=True),r,**kw)
        p=json.loads(re.summarize((pending,excluded)).canonical_bytes)
        self.assertEqual((p['n'],p['pending'],p['excluded']),(0,1,1))
        self.assertIsNone(p['mean_log_loss'])

    def test_result_roundtrip_and_mixed_record_chain(self):
        q=oo.freeze_odds(quote())
        r=re.freeze_result(result(previous_entry_sha256=q.sha256))
        self.assertEqual(r,re.freeze_result(r.canonical_bytes))
        self.assertTrue(oo.validate_chain((q,r)))

    def test_resealed_quote_cannot_keep_external_approval(self):
        q=list(trio()); old=tuple(x.sha256 for x in q)
        q[0]=oo.freeze_odds(quote(raw_price='3'))
        with self.assertRaises(ValueError): re.compare_1x2(packet(),tuple(q),source_bytes=RAW,approved_odds_sha256=old)

    def test_approved_odds_still_require_matching_retained_bytes(self):
        q=trio()
        for raw in (None,RAW+b'changed'):
            with self.assertRaises(ValueError):
                re.compare_1x2(packet(),q,source_bytes=raw,approved_odds_sha256=tuple(x.sha256 for x in q))

    def test_evaluation_cannot_precede_verified_result(self):
        r,kw=scoring()
        self.assertEqual(re.score_1x2(packet(),r,**{**kw,'evaluation_timestamp_utc':'2027-01-10T17:30:00Z'}).status,'PENDING')

    def test_nontrivial_unscaled_brier_log_loss(self):
        r,kw=scoring()
        p=json.loads(re.score_1x2(packet(),r,**kw).canonical_bytes)
        self.assertEqual(p['brier_unscaled'],'19/50')
        self.assertAlmostEqual(p['log_loss'],math.log(2))

    def test_perfect_and_max_brier(self):
        r,kw=scoring()
        for probs,expected in (({'home':'1','draw':'0','away':'0'},'0'),({'home':'0','draw':'1','away':'0'},'2')):
            p=json.loads(re.score_1x2(packet(probs),r,**kw).canonical_bytes)
            self.assertEqual(p['brier_unscaled'],expected)
            self.assertEqual(p['log_loss'],0 if expected=='0' else 'POSITIVE_INFINITY')

    def test_near_uniform_ln3(self):
        r,kw=scoring()
        probs={'home':'0.333333333333333334','draw':'0.333333333333333333','away':'0.333333333333333333'}
        p=json.loads(re.score_1x2(packet(probs),r,**kw).canonical_bytes)
        self.assertAlmostEqual(float(Fraction(p['brier_unscaled'])),2/3)
        self.assertAlmostEqual(p['log_loss'],math.log(3))

    def test_unknown_or_unverified_pending(self):
        r,kw=scoring()
        self.assertEqual(re.score_1x2(packet(),r,evaluation_timestamp_utc=kw['evaluation_timestamp_utc']).status,'PENDING')
        for status in ('UNKNOWN','ABANDONED','POSTPONED','AWARDED','EXTRA_TIME'):
            r,kw=scoring(status=status,home_goals=None,away_goals=None)
            self.assertEqual(re.score_1x2(packet(),r,**kw).status,'PENDING')

    def test_no_forecast_excluded(self):
        r,kw=scoring()
        self.assertEqual(re.score_1x2(packet(abstain=True),r,**kw).status,'EXCLUDED_NO_FORECAST')

    def test_self_review_rights_missing_source_pending(self):
        for change in ({'reviewer':'invented-operator'},{'verified_at_utc':None},{'license_status':'UNKNOWN'},
                        {'result_source_content_sha256':None}):
            r,kw=scoring(**change)
            self.assertEqual(re.score_1x2(packet(),r,**kw).status,'PENDING')

    def test_wrong_result_identity_and_early_times(self):
        r,kw=scoring(fixture_id='OTHER')
        with self.assertRaises(ValueError): re.score_1x2(packet(),r,**kw)
        for change in ({'home_goals':True},{'home_goals':-1},{'period':'EXTRA_TIME'},
                        {'recorded_at_utc':'2027-01-10T16:00:00Z'}, {'verified_at_utc':'2027-01-10T16:00:00Z'}):
            with self.assertRaises(ValueError): re.freeze_result(result(**change))

    def test_source_tamper_and_resealed_result_unapproved(self):
        with self.assertRaises(ValueError): re.freeze_result(result(),source_bytes=RAW+b'x')
        r,kw=scoring(); changed=re.freeze_result(result(home_goals=0))
        self.assertEqual(re.score_1x2(packet(),changed,**kw).status,'PENDING')

    def test_packet_bytes_unchanged_and_tamper_rejected(self):
        f=packet(); original=f.canonical_bytes; r,kw=scoring()
        re.score_1x2(f,r,**kw)
        self.assertEqual(f.canonical_bytes,original)
        with self.assertRaises(ValueError): re.score_1x2(replace(f,commitment_sha256='a'*64),r,**kw)

    def test_summary_empty_pending_excluded_and_duplicate(self):
        r,kw=scoring(); scored=re.score_1x2(packet(),r,**kw)
        self.assertIsNone(json.loads(re.summarize(()).canonical_bytes)['mean_brier_unscaled'])
        self.assertEqual(json.loads(re.summarize((scored,)).canonical_bytes)['n'],1)
        with self.assertRaises(ValueError): re.summarize((scored,scored))


class AHTests(unittest.TestCase):
    def test_all_quarters_both_sides_settlement_and_exact_payout(self):
        for side in ('HOME','AWAY'):
            for q in range(-5,6):
                for hg,ag in ((0,0),(1,0),(0,1),(2,0),(0,2)):
                    quote_record=oo.freeze_odds(quote(market='AH',handicap_q=q,selection=side,raw_price='1.9'))
                    r,kw=scoring(home_goals=hg,away_goals=ag)
                    p=json.loads(re.settle_ah(packet(),quote_record,r,odds_source_bytes=RAW,approved_odds_sha256=(quote_record.sha256,),**kw).canonical_bytes)
                    expected=settle_handicap(hg,ag,side.lower(),q)
                    self.assertEqual(p['outcome'],expected.outcome.value)
                    self.assertEqual(Fraction(p['unit_net_exact']),expected.win*Fraction(9,10)-expected.loss)

    def test_specific_half_win_push_loss(self):
        for q,h,a,outcome in ((-3,2,1,'HW'),(-4,2,1,'P'),(-2,1,1,'FL')):
            qr=oo.freeze_odds(quote(market='AH',handicap_q=q)); r,kw=scoring(home_goals=h,away_goals=a)
            self.assertEqual(json.loads(re.settle_ah(packet(),qr,r,odds_source_bytes=RAW,approved_odds_sha256=(qr.sha256,),**kw).canonical_bytes)['outcome'],outcome)

    def test_expected_net_vs_scoreline_enumeration_and_mass(self):
        qr=oo.freeze_odds(quote(market='AH',handicap_q=-3,raw_price='1.9'))
        d=poisson_distribution(1.4,1.1)
        p=json.loads(re.ah_model_value(qr,d).canonical_bytes)
        enumerated=0
        for h,hp in enumerate(d.home_pmf):
            for a,ap in enumerate(d.away_pmf):
                s=settle_handicap(h,a,'home',-3)
                enumerated+=hp*ap*float(s.win*Fraction(9,10)-s.loss)
        self.assertAlmostEqual(p['retained_unit_net'],enumerated,places=12)
        self.assertGreater(p['mass']['omitted_mass_bound'],0)
        self.assertLessEqual(p['lower_unit_net'],enumerated)
        self.assertGreaterEqual(p['upper_unit_net'],enumerated)

    def test_large_omitted_mass_never_normalized(self):
        qr=oo.freeze_odds(quote(market='AH',handicap_q=0))
        d=truncated_poisson_distribution(2,2,home_cap=0,away_cap=0)
        p=json.loads(re.ah_model_value(qr,d).canonical_bytes)
        self.assertLess(sum(p['probabilities'].values()),0.02)
        self.assertEqual(p['retained_unit_net'],0)

    def test_tampered_distribution_rejected(self):
        qr=oo.freeze_odds(quote(market='AH',handicap_q=0)); d=poisson_distribution(1,1)
        with self.assertRaises(ValueError): re.ah_model_value(qr,replace(d,home_pmf=(1.0,)))

    def test_offline_pure_calls(self):
        f=packet(); r,kw=scoring(); q=trio()
        with patch('socket.socket',side_effect=AssertionError),patch('builtins.open',side_effect=AssertionError),patch.object(Path,'read_bytes',side_effect=AssertionError):
            re.score_1x2(f,r,**kw)
            re.compare_1x2(f,q,source_bytes=RAW,approved_odds_sha256=tuple(x.sha256 for x in q))


if __name__=='__main__': unittest.main()
