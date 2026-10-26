"""Invented inputs shared by offline validation and independent leakage tests."""
from copy import deepcopy
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "phase2a_synthetic_v1.json"

def document():
    return json.loads(FIXTURE.read_bytes())

def one_result(**updates):
    payload = document()
    record = deepcopy(payload["records"][1])
    record.update(revision=0, supersedes_revision=None)
    record.update(updates)
    payload["records"] = [record]
    return payload

def encode(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf8")
