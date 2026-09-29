import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from odt import HONESTY
from odt.engine import canonical, metrics, simulate
from odt.fixtures import AUTO, CAPACITY, fixture_model, write_fixtures
from odt.model import ModelError, ScenarioError, apply_scenario, validate
from odt.report import compare, report


def tiny(count=2):
    return {"name": "FICTIONAL tiny", "fictional": True, "start": "work",
            "resources": {"worker": {"capacity": 1, "cost_rate": 3}},
            "arrivals": {"count": count, "interval": {"kind": "fixed", "value": 1}},
            "steps": {"work": {"duration": {"kind": "fixed", "value": 2},
                               "queue": "work", "resources": {"worker": 1}, "next": []}}}


def change(kind, **kwargs):
    return {"name": "FICTIONAL change", "changes": [{"type": kind, **kwargs}]}


def test_valid_models():
    assert validate(tiny())
    assert validate(fixture_model())


@pytest.mark.parametrize("mutation,error", [
    (lambda m: m.update(fictional=False), "HonestyError"),
    (lambda m: m.update(extra=1), "ModelSchemaError"),
    (lambda m: m.update(start="missing"), "ReferenceError"),
    (lambda m: m["resources"]["worker"].update(capacity=0), "ResourceError"),
    (lambda m: m["steps"]["work"].update(duration={"kind": "fixed", "value": -1}), "DurationError"),
    (lambda m: m["steps"]["work"].update(queue=""), "QueueError"),
    (lambda m: m["steps"]["work"].update(next=[{"step": "work", "probability": .5}]), "BranchError"),
    (lambda m: m["steps"]["work"].update(next=[{"step": "work", "probability": 1}]), "CycleError"),
    (lambda m: m["arrivals"].update(count=True), "ArrivalError"),
    (lambda m: m["steps"]["work"].update(resources={"missing": 1}), "ResourceError"),
    (lambda m: m["steps"]["work"].update(duration={"kind": "uniform", "low": 5, "high": 1}), "DurationError"),
    (lambda m: m["steps"]["work"].update(duration={"kind": "fixed", "value": float("nan")}), "DurationError"),
])
def test_named_model_errors(mutation, error):
    model = tiny()
    mutation(model)
    with pytest.raises(ModelError, match=error):
        validate(model)


@pytest.mark.parametrize("scenario", [change("unknown"), change("remove_step", step="missing"),
    change("add_capacity", resource="worker", amount=0), change("add_capacity", resource="missing", amount=1),
    change("auto_approve", step="work", threshold=-1), change("change_arrival_rate", rate=0),
    change("parallelise", steps=["work", "missing"]), {"name": "x", "changes": []}])
def test_invalid_scenarios(scenario):
    with pytest.raises(ScenarioError, match="InvalidScenario"):
        apply_scenario(tiny(), scenario)


def test_single_step_exact_trace():
    assert simulate(tiny(1), 7)["events"] == [
        {"time": 0, "type": "arrival", "job": 0, "value": 0},
        {"time": 0, "type": "enqueue", "job": 0, "step": "work", "queue": "work", "length": 1},
        {"time": 0, "type": "dequeue", "job": 0, "step": "work", "queue": "work", "length": 0},
        {"time": 0, "type": "resource", "job": 0, "step": "work", "resource": "worker", "busy": 1},
        {"time": 0, "type": "start", "job": 0, "step": "work", "duration": 2},
        {"time": 2, "type": "end", "job": 0, "step": "work"},
        {"time": 2, "type": "resource", "job": 0, "step": "work", "resource": "worker", "busy": 0},
        {"time": 2, "type": "complete", "job": 0}]


def test_hand_metrics():
    m = metrics(simulate(tiny(), 0))
    assert m == {"completed": 2, "horizon": 4, "throughput": .5, "mean_lead_time": 2.5,
                 "p95_lead_time": 3, "queues": {"work": {"max": 1, "mean": .25}},
                 "resource_utilisation": {"worker": 1}, "cost_proxy": 12}


def test_hand_deltas():
    base = tiny()
    altered = apply_scenario(base, change("add_capacity", resource="worker", amount=1))
    rows = {r["metric"]: r for r in compare(simulate(base), simulate(altered))["rows"]}
    assert rows["mean_lead_time"]["delta"] == -.5
    assert rows["throughput"]["delta"] == pytest.approx(1/6)
    assert rows["queues.work.mean"]["delta"] == -.25
    assert rows["cost_proxy"]["delta"] == 0
    assert rows["resource_utilisation.worker"]["after"] == pytest.approx(2/3)
    assert base == tiny()


def test_fixture_bottleneck_and_scenarios():
    model = fixture_model()
    base = simulate(model, 42)
    capacity = simulate(apply_scenario(model, CAPACITY), 42)
    auto = simulate(apply_scenario(model, AUTO), 42)
    a, b, c = map(metrics, (base, capacity, auto))
    assert max(a["queues"], key=lambda q: a["queues"][q]["mean"]) == "QA"
    assert b["queues"]["QA"]["max"] < a["queues"]["QA"]["max"]
    assert c["mean_lead_time"] < a["mean_lead_time"]
    assert json.loads(report(base, auto, "json"))["bottlenecks"][0] == "QA"
    assert compare(base, auto)["evidence"]


def test_determinism():
    model = fixture_model()
    a, b, c = simulate(model, 1), simulate(model, 1), simulate(model, 2)
    assert canonical(a).encode() == canonical(b).encode()
    assert canonical(metrics(a)).encode() == canonical(metrics(b)).encode()
    assert canonical(a) != canonical(c)
    assert metrics(c)["completed"] == 80


def test_fixture_files_deterministic(tmp_path):
    write_fixtures(tmp_path / "a")
    write_fixtures(tmp_path / "b")
    for f in (tmp_path / "a").iterdir():
        assert f.read_bytes() == (tmp_path / "b" / f.name).read_bytes()
        assert "FICTIONAL" in f.read_text()


def chain():
    m = tiny(1)
    m["steps"]["after"] = copy.deepcopy(m["steps"]["work"])
    m["steps"]["after"]["resources"] = {}
    m["steps"]["after"]["queue"] = "after"
    m["steps"]["work"]["next"] = [{"step": "after", "probability": 1}]
    return m


def test_remove_step():
    m = apply_scenario(chain(), change("remove_step", step="work"))
    assert "work" not in m["steps"]
    assert metrics(simulate(m))["mean_lead_time"] == 2


def test_parallelise_actual_overlap_and_join():
    m = apply_scenario(chain(), change("parallelise", steps=["work", "after"]))
    trace = simulate(m)
    assert metrics(trace)["mean_lead_time"] == 2
    starts = [e for e in trace["events"] if e["type"] == "start" and e["step"] in {"work", "after"}]
    assert [e["time"] for e in starts] == [0, 0]
    assert sum(e["type"] == "complete" for e in trace["events"]) == 1


def test_parallelise_shared_resource_contention():
    m = chain()
    m["steps"]["after"]["resources"] = {"worker": 1}
    m = apply_scenario(m, change("parallelise", steps=["work", "after"]))
    assert metrics(simulate(m))["mean_lead_time"] == 4


def test_arrival_rate():
    m = apply_scenario(tiny(), change("change_arrival_rate", rate=2))
    assert m["arrivals"]["interval"] == {"kind": "exponential", "mean": .5}
    assert canonical(simulate(m, 4)) == canonical(simulate(m, 4))


def test_auto_approve_strict_threshold():
    m = apply_scenario(tiny(1), change("auto_approve", step="work", threshold=10))
    m["arrivals"]["value"] = {"kind": "fixed", "value": 10}
    assert metrics(simulate(m))["mean_lead_time"] == 2
    m["arrivals"]["value"]["value"] = 9
    assert metrics(simulate(m))["cost_proxy"] == 0


def test_probabilistic_branch():
    m = chain()
    m["arrivals"]["count"] = 100
    m["steps"]["other"] = copy.deepcopy(m["steps"]["after"])
    m["steps"]["work"]["next"] = [{"step": "after", "probability": .5}, {"step": "other", "probability": .5}]
    trace = simulate(m, 1)
    assert {e["target"] for e in trace["events"] if e["type"] == "branch"} == {"after", "other"}
    assert metrics(trace)["completed"] == 100


@pytest.mark.parametrize("format", ["md", "json"])
@pytest.mark.parametrize("with_scenario", [False, True])
def test_all_reports_have_banner(format, with_scenario):
    trace = simulate(tiny())
    assert HONESTY in report(trace, trace if with_scenario else None, format)
    assert compare(trace, trace)["honesty_banner"] == HONESTY


def cli(*args):
    return subprocess.run([sys.executable, "-m", "odt", *map(str, args)], capture_output=True, text=True)


def test_cli_full_workflow(tmp_path):
    assert cli("--help").returncode == 0
    assert cli("fixtures", "--out", tmp_path).returncode == 0
    model = tmp_path / "model.yaml"
    assert cli("validate", model).returncode == 0
    base, altered, output = [tmp_path / n for n in ("base.json", "changed.yaml", "scenario.json")]
    assert cli("simulate", "--model", model, "--seed", 42, "--out", base).returncode == 0
    assert cli("scenario", "--base", model, "--change", tmp_path / "add-qa-capacity.yaml", "--out", altered).returncode == 0
    assert cli("simulate", "--model", altered, "--seed", 42, "--out", output).returncode == 0
    compared = cli("compare", "--base", base, "--scenario", output)
    assert compared.returncode == 0
    assert HONESTY in compared.stdout
    for format in ("md", "json"):
        result = cli("report", "--trace", base, "--scenario", output, "--format", format)
        assert result.returncode == 0
        assert HONESTY in result.stdout
    again = tmp_path / "again.json"
    assert cli("simulate", "--model", model, "--seed", 42, "--out", again).returncode == 0
    assert base.read_bytes() == again.read_bytes()


def test_cli_errors(tmp_path):
    invalid = tmp_path / "bad.yaml"
    invalid.write_text("fictional: false")
    result = cli("validate", invalid)
    assert result.returncode == 2
    assert "HonestyError" in result.stderr
    assert cli("simulate", "--model", tmp_path / "missing").returncode == 2


def test_no_em_dash_in_project_sources():
    root = Path(__file__).resolve().parents[1]
    for directory in (root / "odt", root / "tests"):
        for path in directory.glob("*.py"):
            assert chr(0x2014) not in path.read_text(encoding="utf-8")
    assert chr(0x2014) not in (root / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("mutation,error", [
    (lambda m: m.update(start=[]), "ReferenceError"),
    (lambda m: m["steps"]["work"].update(next=[{"step": [], "probability": 1}]), "ReferenceError"),
    (lambda m: m["steps"]["work"].update(fork=[[], "work"]), "ForkError"),
    (lambda m: m["resources"].update({1: {"capacity": 1, "cost_rate": 0}}), "ResourceError"),
])
def test_malformed_names_raise_named_errors(mutation, error):
    m = tiny()
    mutation(m)
    with pytest.raises(ModelError, match=error):
        validate(m)


def test_exponential_durations_and_multi_unit_capacity():
    m = tiny(10)
    m["resources"]["worker"]["capacity"] = 4
    m["steps"]["work"]["resources"]["worker"] = 2
    m["steps"]["work"]["duration"] = {"kind": "exponential", "mean": 3}
    trace = simulate(m, 5)
    assert metrics(trace)["completed"] == 10
    assert all(0 <= e["busy"] <= 4 for e in trace["events"] if e["type"] == "resource")
    assert canonical(trace) == canonical(simulate(m, 5))
