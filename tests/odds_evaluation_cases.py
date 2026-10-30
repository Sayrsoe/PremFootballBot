"""One invented example, with mutations for regression tests; no genuine prices/results."""
import hashlib
from premfootballbot.odds_observations import freeze_odds, PROTOCOL
from premfootballbot.result_evaluation import freeze_result, RESULT_PROTOCOL
from premfootballbot.prospective_evidence import freeze_packet
from tests.test_prospective_evidence import sample

RAW = b'INVENTED local snapshot, not market evidence'


def packet(probabilities=None, abstain=False):
    p = sample()
    if not abstain:
        p['model'] = {'name':'invented', 'version':'v1', 'config_sha256':'a'*64}
        p['forecast'] = {'kind':'ONE_X_TWO', 'probabilities': probabilities or {'home':'0.5','draw':'0.3','away':'0.2'}}
    return freeze_packet(p)


def quote(**changes):
    f = sample()['fixture']
    p = dict(protocol=PROTOCOL, league='EPL', fixture_id=f['fixture_id'], home=f['home'], away=f['away'],
             kickoff_utc=f['kickoff_utc'], bookmaker='INVENTED', market='1X2', period='REGULATION_90',
             selection='HOME', handicap_q=None, price_format='DECIMAL', raw_price='2',
             source_url='https://example.org/INVENTED', source_kind='RETAINED_SNAPSHOT', rights_status='CLEARED',
             source_content_sha256=hashlib.sha256(RAW).hexdigest(), captured_at_utc='2027-01-09T10:30:00Z',
             claimed_observed_at_utc='2027-01-09T10:30:00Z', independent_observed_at_utc='2027-01-09T10:45:00Z',
             operator='invented-operator', provenance_assurance='LOCAL_ONLY', previous_entry_sha256=None, snapshot_id='INVENTED')
    p.update(changes)
    return p


def result(**changes):
    f = sample()['fixture']
    p = dict(protocol=RESULT_PROTOCOL, league='EPL', fixture_id=f['fixture_id'], home=f['home'], away=f['away'],
             kickoff_utc=f['kickoff_utc'], period='REGULATION_90', status='FINISHED_REGULATION', home_goals=2, away_goals=1,
             result_source_url='https://example.org/INVENTED-result', result_source_content_sha256=hashlib.sha256(RAW).hexdigest(),
             recorded_at_utc='2027-01-10T17:00:00Z', verified_at_utc='2027-01-10T18:00:00Z', license_status='CLEARED',
             source_method='RETAINED_SNAPSHOT', reviewer='invented-reviewer', operator='invented-operator',
             previous_entry_sha256=None, provenance_assurance='LOCAL_ONLY')
    p.update(changes)
    return p


def trio(**changes):
    return tuple(freeze_odds(quote(selection=s, raw_price=p, **changes)) for s,p in
                 (('HOME','2'),('DRAW','4'),('AWAY','4')))


def scoring(**changes):
    r = freeze_result(result(**changes))
    return r, dict(evaluation_timestamp_utc='2027-01-10T19:00:00Z', approved_result_sha256=(r.sha256,), result_source_bytes=RAW)
