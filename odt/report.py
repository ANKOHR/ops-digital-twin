"""Trace-derived comparisons and reports, always with the honesty boundary."""
from . import HONESTY
from .engine import metrics, canonical


def flatten(m):
    out = {}
    def visit(prefix, value):
        if isinstance(value, dict):
            for key, child in sorted(value.items()):
                visit(f"{prefix}.{key}" if prefix else key, child)
        else:
            out[prefix] = value
    visit("", m)
    return out


def compare(base, scenario):
    a, b = flatten(metrics(base)), flatten(metrics(scenario))
    rows = [{"metric": k, "before": a.get(k, 0), "after": b.get(k, 0),
             "delta": b.get(k, 0) - a.get(k, 0)} for k in sorted(set(a) | set(b))]
    comparable = [r for r in rows if r["metric"].startswith("queues.") and r["metric"].endswith(".mean")]
    biggest = max(comparable, key=lambda r: abs(r["delta"]), default=None)
    evidence = []
    if biggest:
        queue = biggest["metric"][7:-5]
        for label, trace in (("base", base), ("scenario", scenario)):
            candidates = [e for e in trace["events"] if e.get("queue") == queue and e["type"] == "enqueue"]
            if candidates:
                peak = max(candidates, key=lambda e: e["length"])
                evidence.append({"run": label, "event_index": trace["events"].index(peak), "event": peak})
            evidence.extend({"run": label, "event_index": i, "event": e}
                            for i, e in enumerate(trace["events"]) if e["type"] == "skip" and len(evidence) < 8)
    return {"honesty_banner": HONESTY, "rows": rows,
            "explanation": "Largest absolute change in time-weighted mean queue length; peak queue and skip events are supporting evidence, not a causal proof.",
            "largest_queue_delta": biggest, "evidence": evidence}


def report(trace, scenario=None, format="md"):
    m = metrics(trace)
    ranked = sorted(m["queues"], key=lambda q: (-m["queues"][q]["mean"], -m["queues"][q]["max"], q))
    data = {"honesty_banner": HONESTY,
            "model_summary": {"name": trace["model"]["name"], "steps": len(trace["model"]["steps"]),
                              "arrivals": trace["model"]["arrivals"], "resources": trace["model"]["resources"], "seed": trace["seed"]},
            "metrics": m, "bottlenecks": ranked,
            "comparison": compare(trace, scenario) if scenario else None}
    if format == "json":
        return canonical(data)
    lines = ["# Ops Digital Twin report", "", HONESTY, "", f"Model: {trace['model']['name']}",
             f"Seed: {trace['seed']}. Steps: {len(trace['model']['steps'])}. Arrivals: {trace['model']['arrivals']['count']}.",
             "", "| Metric | Value |", "| --- | ---: |"]
    lines.extend(f"| {k} | {v:.6g} |" for k, v in flatten(m).items())
    lines += ["", "Bottlenecks ranked by time-weighted mean queue length: " + ", ".join(ranked) + "."]
    if scenario:
        c = data["comparison"]
        lines += ["", "| Metric | Before | After | Delta |", "| --- | ---: | ---: | ---: |"]
        lines.extend(f"| {r['metric']} | {r['before']:.6g} | {r['after']:.6g} | {r['delta']:+.6g} |" for r in c["rows"])
        lines += ["", c["explanation"], "", "```json", canonical(c["evidence"]).rstrip(), "```"]
    return "\n".join(lines) + "\n"
