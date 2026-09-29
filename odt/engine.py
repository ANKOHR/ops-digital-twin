"""Seeded discrete-event simulation with deterministic event ordering."""
import heapq
import json
import random
from collections import defaultdict
from .model import validate


def canonical(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def sample(rng, d):
    if d["kind"] == "fixed":
        return d["value"]
    if d["kind"] == "uniform":
        return rng.uniform(d["low"], d["high"])
    return rng.expovariate(1 / d["mean"])


def simulate(model, seed=0):
    validate(model)
    rng = random.Random(seed)
    events, heap, waiting = [], [], []
    serial = 0
    busy = {r: 0 for r in sorted(model["resources"])}
    queues = {q: 0 for q in sorted({s["queue"] for s in model["steps"].values()})}
    values, outstanding, joins = {}, defaultdict(int), defaultdict(int)
    def schedule(t, kind, job, step=None):
        nonlocal serial
        heapq.heappush(heap, (t, serial, kind, job, step))
        serial += 1
    def record(t, kind, job, step=None, **extra):
        e = {"time": t, "type": kind, "job": job}
        if step is not None:
            e["step"] = step
        e.update(extra)
        events.append(e)
    t = 0
    for job in range(model["arrivals"]["count"]):
        if job:
            t += sample(rng, model["arrivals"]["interval"])
        values[job] = sample(rng, model["arrivals"].get("value", {"kind": "fixed", "value": 0}))
        schedule(t, "arrival", job)
    def activate(t, job, step):
        spec = model["steps"][step]
        if "join" in spec:
            joins[job, step] += 1
            record(t, "join_arrival", job, step, received=joins[job, step])
            if joins[job, step] < spec["join"]:
                return
        outstanding[job] += 1
        if "auto_approve" in spec and values[job] < spec["auto_approve"]:
            record(t, "skip", job, step, value=values[job])
            schedule(t, "skip_end", job, step)
        else:
            waiting.append((job, step))
            q = spec["queue"]
            queues[q] += 1
            record(t, "enqueue", job, step, queue=q, length=queues[q])
    def dispatch(t):
        blocked_queues = set()
        for job, step in list(waiting):
            spec = model["steps"][step]
            q, req = spec["queue"], spec.get("resources", {})
            if q in blocked_queues:
                continue
            if any(busy[r] + n > model["resources"][r]["capacity"] for r, n in req.items()):
                blocked_queues.add(q)
                continue
            waiting.remove((job, step))
            queues[q] -= 1
            record(t, "dequeue", job, step, queue=q, length=queues[q])
            for r in sorted(req):
                busy[r] += req[r]
                record(t, "resource", job, step, resource=r, busy=busy[r])
            duration = sample(rng, spec["duration"])
            record(t, "start", job, step, duration=duration)
            schedule(t + duration, "end", job, step)
    while heap:
        t, _, kind, job, step = heapq.heappop(heap)
        if kind == "arrival":
            record(t, "arrival", job, value=values[job])
            activate(t, job, model["start"])
        else:
            spec = model["steps"][step]
            if kind == "end":
                record(t, "end", job, step)
                for r, n in sorted(spec.get("resources", {}).items()):
                    busy[r] -= n
                    record(t, "resource", job, step, resource=r, busy=busy[r])
            outstanding[job] -= 1
            targets = spec.get("fork", [])
            if not targets and spec.get("next"):
                draw = rng.random()
                cumulative = 0
                target = spec["next"][-1]["step"]
                for b in spec["next"]:
                    cumulative += b["probability"]
                    if draw < cumulative:
                        target = b["step"]
                        break
                targets = [target]
                record(t, "branch", job, step, target=target, draw=draw)
            for target in targets:
                activate(t, job, target)
            pending_join = any(j == job and count < model["steps"][s]["join"] for (j, s), count in joins.items())
            if outstanding[job] == 0 and not pending_join:
                record(t, "complete", job)
        dispatch(t)
    completed = sum(e["type"] == "complete" for e in events)
    if waiting or completed != model["arrivals"]["count"]:
        raise ValueError("SimulationDeadlockError: work failed to complete; check fork and join paths")
    return {"version": 1, "seed": seed, "model": model, "events": events}


def metrics(trace):
    events, model = trace["events"], trace["model"]
    horizon = max((e["time"] for e in events), default=0)
    arrivals, lead = {}, []
    qstate = {s["queue"]: [0, 0, 0, 0] for s in model["steps"].values()}
    rstate = {r: [0, 0, 0] for r in model["resources"]}
    for e in events:
        t = e["time"]
        if e["type"] == "arrival":
            arrivals[e["job"]] = t
        elif e["type"] == "complete":
            lead.append(t - arrivals[e["job"]])
        elif e["type"] in {"enqueue", "dequeue"}:
            state = qstate[e["queue"]]
            state[2] += state[0] * (t - state[1])
            state[0], state[1] = e["length"], t
            state[3] = max(state[3], e["length"])
        elif e["type"] == "resource":
            state = rstate[e["resource"]]
            state[2] += state[0] * (t - state[1])
            state[0], state[1] = e["busy"], t
    for state in list(qstate.values()) + list(rstate.values()):
        state[2] += state[0] * (horizon - state[1])
    ordered = sorted(lead)
    return {"completed": len(lead), "horizon": horizon,
            "throughput": len(lead) / horizon if horizon else 0,
            "mean_lead_time": sum(lead) / len(lead) if lead else 0,
            "p95_lead_time": ordered[max(0, math_ceil(.95 * len(lead)) - 1)] if lead else 0,
            "queues": {q: {"max": s[3], "mean": s[2] / horizon if horizon else 0} for q, s in sorted(qstate.items())},
            "resource_utilisation": {r: s[2] / (horizon * model["resources"][r]["capacity"]) if horizon else 0 for r, s in sorted(rstate.items())},
            "cost_proxy": sum(s[2] * model["resources"][r]["cost_rate"] for r, s in rstate.items())}


def math_ceil(x):
    import math
    return math.ceil(x)
