"""Entirely synthetic fictional order fulfilment examples."""
from pathlib import Path
import yaml


def fixture_model():
    names = ["receive", "pick", "pack", "QA", "ship"]
    return {"name": "FICTIONAL synthetic order fulfilment", "fictional": True, "start": "receive",
            "arrivals": {"count": 80, "interval": {"kind": "fixed", "value": 1},
                         "value": {"kind": "uniform", "low": 0, "high": 100}},
            "resources": {s: {"capacity": 1, "cost_rate": 2 if s == "QA" else 1} for s in names},
            "steps": {s: {"queue": s, "resources": {s: 1},
                          "duration": {"kind": "uniform", "low": 3, "high": 5} if s == "QA" else {"kind": "fixed", "value": .25},
                          "next": [{"step": names[i+1], "probability": 1}] if i < 4 else []} for i, s in enumerate(names)}}


CAPACITY = {"name": "FICTIONAL add QA capacity", "changes": [{"type": "add_capacity", "resource": "QA", "amount": 3}]}
AUTO = {"name": "FICTIONAL auto-approve low-value orders", "changes": [{"type": "auto_approve", "step": "QA", "threshold": 75}]}


def write_fixtures(out):
    path = Path(out)
    path.mkdir(parents=True, exist_ok=True)
    for name, content in (("model.yaml", fixture_model()), ("add-qa-capacity.yaml", CAPACITY), ("auto-approve.yaml", AUTO)):
        (path / name).write_text(yaml.safe_dump(content, sort_keys=True), encoding="utf-8")
