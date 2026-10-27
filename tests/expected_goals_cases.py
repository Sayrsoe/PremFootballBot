"""Invented Phase2B cases; no provider records or real club identities."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from premfootballbot.match_data import parse_synthetic_json

ROOT=Path(__file__).parent/"fixtures"/"phase2b_synthetic_v1.json"
NS="synthetic:phase2b"
CUTOFF=datetime(2040,1,1,tzinfo=timezone.utc)
TARGET=datetime(2040,1,2,tzinfo=timezone.utc)
TOY_A=[("a","b",2,1),("a","c",3,0),("b","a",1,1),
       ("b","c",2,0),("c","a",0,2),("c","b",1,1)]
TOY_B=[("a","b",4,1),("b","c",2,1),("c","a",1,1)]
TOY_C=[("a","b",2,1),("b","a",1,1)]

def team(name):
    return NS+":team:"+name

def payload(games=TOY_A):
    raw=json.loads(ROOT.read_bytes())
    template=raw["records"][0]
    raw["teams"]=[dict(team_id=team(t),aliases=["Invented "+t.upper()])
                  for t in sorted({t for home,away,_,_ in games for t in (home,away)})]
    rows=[]
    for index,(home,away,x,y) in enumerate(games):
        row=deepcopy(template)
        kickoff=datetime(2026,8,1,14,tzinfo=timezone.utc)+timedelta(days=index)
        row.update(fixture_id=NS+":fixture:game-"+str(index),source_record_id=NS+":record:game-"+str(index),
                   home_team_id=team(home),away_team_id=team(away),
                   home_team_name_raw="Invented "+home.upper(),away_team_name_raw="Invented "+away.upper(),
                   home_goals_90=x,away_goals_90=y,kickoff_utc=kickoff.isoformat(),
                   available_at_utc=(kickoff+timedelta(hours=2)).isoformat(),
                   retrieved_at_utc="2050-01-01T00:00:00Z")
        rows.append(row)
    raw["records"]=rows
    return raw

def batch(games=TOY_A):
    return parse(payload(games))

def parse(raw):
    return parse_synthetic_json(json.dumps(raw).encode()).require_valid()

def target(home="a",away="c",**kwargs):
    values=dict(target_fixture_id=NS+":fixture:target",home_team_id=team(home),away_team_id=team(away),
                target_kickoff_utc=TARGET,cutoff_utc=CUTOFF)
    values.update(kwargs)
    return values
