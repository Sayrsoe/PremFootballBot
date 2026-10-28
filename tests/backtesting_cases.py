"""Invented independent schedules and outcomes for Phase3A tests."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.backtesting import parse_target_manifest

ROOT=Path(__file__).parent/"fixtures"
NS="synthetic:phase3a"
EVALUATION=datetime(2027,8,1,tzinfo=timezone.utc)

def observations():
    return json.loads((ROOT/"phase3a_synthetic_v1.json").read_bytes())

def targets():
    return json.loads((ROOT/"phase3a_synthetic_targets_v1.json").read_bytes())

def encode(value):
    return json.dumps(value,ensure_ascii=False).encode("utf8")

def batch(raw=None):
    return parse_synthetic_json(encode(observations() if raw is None else raw)).require_valid()

def manifest(raw=None, names=None):
    raw=targets() if raw is None else deepcopy(raw)
    if names is not None:
        wanted={NS+":fixture:target-"+name for name in names}
        raw["targets"]=[r for r in raw["targets"] if r["fixture_id"] in wanted]
    return parse_target_manifest(encode(raw))

def fixture(name):
    return NS+":fixture:target-"+name

def target_row(raw,name):
    return next(r for r in raw["targets"] if r["fixture_id"]==fixture(name))

def stamp(text):
    return datetime.fromisoformat(text.replace("Z","+00:00"))
