"""Strict model and scenario validation."""
import copy
import math
import yaml


class ModelError(ValueError):
    """A named DSL validation error."""


class ScenarioError(ValueError):
    """A named scenario validation error."""


def fail(name, message):
    raise ModelError(f"{name}: {message}")


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail(name, "expected a finite number")
    if value < 0 or (positive and value == 0):
        fail(name, "number outside allowed range")


def keys(obj, allowed, name):
    if not isinstance(obj, dict) or set(obj) - set(allowed):
        fail(name, f"expected mapping with keys {sorted(allowed)}")


def distribution(d, name):
    keys(d, {"kind", "value", "low", "high", "mean"}, name)
    kind = d.get("kind")
    required = {"fixed": {"kind", "value"}, "uniform": {"kind", "low", "high"},
                "exponential": {"kind", "mean"}}.get(kind)
    if required is None or set(d) != required:
        fail(name, "invalid distribution fields")
    for k in required - {"kind"}:
        number(d[k], name, positive=(kind == "exponential"))
    if kind == "uniform" and d["high"] < d["low"]:
        fail(name, "high must be >= low")


def validate(m):
    keys(m, {"name", "fictional", "resources", "steps", "start", "arrivals"}, "ModelSchemaError")
    if m.get("fictional") is not True or not isinstance(m.get("name"), str):
        fail("HonestyError", "name and fictional: true are required")
    resources, steps = m.get("resources"), m.get("steps")
    if not isinstance(resources, dict) or not isinstance(steps, dict) or not steps:
        fail("ModelSchemaError", "resources and nonempty steps mappings required")
    for r, spec in resources.items():
        if not isinstance(r, str) or not r:
            fail("ResourceError", "resource names must be nonempty strings")
        keys(spec, {"capacity", "cost_rate"}, "ResourceError")
        c = spec.get("capacity")
        if isinstance(c, bool) or not isinstance(c, int) or c < 1:
            fail("ResourceError", f"{r}: capacity must be a positive integer")
        number(spec.get("cost_rate"), "ResourceError")
    for s, spec in steps.items():
        if not isinstance(s, str) or not s:
            fail("StepError", "step names must be nonempty strings")
        keys(spec, {"duration", "resources", "queue", "next", "fork", "join", "auto_approve"}, "StepError")
        distribution(spec.get("duration"), "DurationError")
        if not isinstance(spec.get("queue"), str) or not spec["queue"]:
            fail("QueueError", f"{s}: queue required")
        req = spec.get("resources", {})
        if not isinstance(req, dict):
            fail("ResourceError", "requirements must be a mapping")
        for r, units in req.items():
            if r not in resources or isinstance(units, bool) or not isinstance(units, int) or not 1 <= units <= resources[r]["capacity"]:
                fail("ResourceError", f"{s}: invalid requirement {r}")
        nxt = spec.get("next", [])
        if not isinstance(nxt, list):
            fail("BranchError", "next must be a list")
        for b in nxt:
            keys(b, {"step", "probability"}, "BranchError")
            if not isinstance(b.get("step"), str) or b["step"] not in steps:
                fail("ReferenceError", f"{s}: missing next step")
            number(b.get("probability"), "BranchError")
        if nxt and not math.isclose(sum(b["probability"] for b in nxt), 1, abs_tol=1e-12):
            fail("BranchError", f"{s}: probabilities must sum to one")
        if "fork" in spec:
            if nxt or not isinstance(spec["fork"], list) or len(spec["fork"]) < 2 or any(not isinstance(x, str) for x in spec["fork"]) or len(set(spec["fork"])) != len(spec["fork"]) or any(x not in steps for x in spec["fork"]):
                fail("ForkError", "fork must name distinct existing steps and cannot have next")
        if "join" in spec and (isinstance(spec["join"], bool) or not isinstance(spec["join"], int) or spec["join"] < 2):
            fail("JoinError", "join must be an integer >= 2")
        if "auto_approve" in spec:
            number(spec["auto_approve"], "ThresholdError")
    if not isinstance(m.get("start"), str) or m["start"] not in steps:
        fail("ReferenceError", "start step missing")
    visiting, visited = set(), set()
    def walk(s):
        if s in visiting:
            fail("CycleError", "workflow must be acyclic")
        if s in visited:
            return
        visiting.add(s)
        for t in steps[s].get("fork", []) + [b["step"] for b in steps[s].get("next", [])]:
            walk(t)
        visiting.remove(s)
        visited.add(s)
    walk(m["start"])
    if visited != set(steps):
        fail("ReachabilityError", "all steps must be reachable")
    a = m.get("arrivals")
    keys(a, {"count", "interval", "value"}, "ArrivalError")
    if isinstance(a.get("count"), bool) or not isinstance(a.get("count"), int) or a["count"] < 1:
        fail("ArrivalError", "count must be a positive integer")
    distribution(a.get("interval"), "ArrivalError")
    distribution(a.get("value", {"kind": "fixed", "value": 0}), "ArrivalError")
    return m


def read_model(path):
    with open(path, encoding="utf-8") as f:
        return validate(yaml.safe_load(f))


def apply_scenario(base, change):
    m = copy.deepcopy(validate(base))
    try:
        keys(change, {"name", "changes"}, "ScenarioSchemaError")
        if not isinstance(change.get("name"), str) or not isinstance(change.get("changes"), list) or not change["changes"]:
            fail("ScenarioSchemaError", "name and nonempty changes required")
        for c in change["changes"]:
            kind = c.get("type") if isinstance(c, dict) else None
            allowed = {"remove_step": {"type", "step"}, "parallelise": {"type", "steps"},
                       "auto_approve": {"type", "step", "threshold"},
                       "add_capacity": {"type", "resource", "amount"},
                       "change_arrival_rate": {"type", "rate"}}
            if kind not in allowed or set(c) != allowed[kind]:
                fail("ScenarioChangeError", "unknown change or invalid fields")
            if kind in {"remove_step", "auto_approve"}:
                s = c["step"]
                if s not in m["steps"] or "fork" in m["steps"][s] or "join" in m["steps"][s]:
                    fail("ScenarioReferenceError", "expected ordinary existing step")
                if kind == "auto_approve":
                    number(c["threshold"], "ThresholdError")
                    m["steps"][s]["auto_approve"] = c["threshold"]
                else:
                    successors = m["steps"][s].get("next", [])
                    if m["start"] == s:
                        if len(successors) != 1:
                            fail("RemoveStepError", "start removal needs one successor")
                        m["start"] = successors[0]["step"]
                    for spec in m["steps"].values():
                        if s in spec.get("fork", []):
                            fail("RemoveStepError", "cannot remove fork target")
                        out = []
                        for b in spec.get("next", []):
                            if b["step"] == s:
                                if not successors:
                                    fail("RemoveStepError", "cannot remove referenced terminal step")
                                out.extend({"step": n["step"], "probability": b["probability"] * n["probability"]} for n in successors)
                            else:
                                out.append(b)
                        spec["next"] = out
                    del m["steps"][s]
            elif kind == "add_capacity":
                amount = c["amount"]
                if c["resource"] not in m["resources"] or isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
                    fail("CapacityChangeError", "existing resource and positive integer amount required")
                m["resources"][c["resource"]]["capacity"] += amount
            elif kind == "change_arrival_rate":
                number(c["rate"], "ArrivalRateError", positive=True)
                m["arrivals"]["interval"] = {"kind": "exponential", "mean": 1 / c["rate"]}
            else:
                names = c["steps"]
                if not isinstance(names, list) or len(names) < 2 or len(set(names)) != len(names) or any(s not in m["steps"] for s in names):
                    fail("ParalleliseError", "distinct existing chain steps required")
                for i, s in enumerate(names):
                    spec = m["steps"][s]
                    if "fork" in spec or "join" in spec:
                        fail("ParalleliseError", "ordinary chain required")
                    if i and any(s == b["step"] for p, v in m["steps"].items() if p != names[i-1] for b in v.get("next", [])):
                        fail("ParalleliseError", "chain has external incoming edges")
                    if i < len(names)-1 and spec.get("next") != [{"step": names[i+1], "probability": 1}]:
                        fail("ParalleliseError", "contiguous unconditional chain required")
                fork, join = names[0] + "__fork", names[0] + "__join"
                if fork in m["steps"] or join in m["steps"]:
                    fail("ParalleliseError", "generated name collision")
                tail = m["steps"][names[-1]].get("next", [])
                for p, spec in m["steps"].items():
                    if p not in names:
                        for b in spec.get("next", []):
                            if b["step"] == names[0]:
                                b["step"] = fork
                if m["start"] == names[0]:
                    m["start"] = fork
                for s in names:
                    m["steps"][s]["next"] = [{"step": join, "probability": 1}]
                zero = {"duration": {"kind": "fixed", "value": 0}, "resources": {}, "queue": "coordination"}
                m["steps"][fork] = dict(zero, fork=names)
                m["steps"][join] = dict(zero, join=len(names), next=tail)
        m["name"] += " / " + change["name"]
        return validate(m)
    except (ModelError, KeyError, TypeError) as e:
        raise ScenarioError(f"InvalidScenario: {e}") from e
