# Ops Digital Twin

Describe how work flows through your company, propose an automation, and watch what happens before you spend a pound.

Ops Digital Twin is a CPU-only Python CLI that tests ideas against a declared, fictional process model. It validates a workflow graph, runs a seeded discrete-event simulation, and compares trace-derived throughput, lead times, queues, utilisation and cost proxies.

## HONESTY BOUNDARY

This simulates a declared model of a fictional process, not a real company. It does not predict real company outcomes. Results follow from the model's assumptions, and predictions are only as good as the model: a wrong model gives wrong answers. No real companies or real process data are included. All fixtures are synthetic and labelled fictional. Applying these results to a business requires independent validation of assumptions and data. Every Markdown and JSON report and comparison carries this boundary.

## Quickstart

Requires Python 3.10 or later. From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m pytest -q
odt fixtures --out outputs/fixtures
odt validate outputs/fixtures/model.yaml
odt simulate --model outputs/fixtures/model.yaml --seed 42 --out outputs/base.json
odt scenario --base outputs/fixtures/model.yaml --change outputs/fixtures/add-qa-capacity.yaml --out outputs/capacity.yaml
odt simulate --model outputs/capacity.yaml --seed 42 --out outputs/capacity.json
odt compare --base outputs/base.json --scenario outputs/capacity.json --out outputs/comparison.json
odt report --trace outputs/base.json --scenario outputs/capacity.json --format md --out outputs/report.md
```

Use `auto-approve.yaml` in the same workflow to evaluate skipping low-value QA. `python -m odt` also works for every command. Outputs go to stdout unless `--out` is supplied. Validation failures print named errors to stderr and return exit code 2.

## Architecture

```text
YAML model -> strict DSL validation -> declared workflow graph
YAML changes -> scenario validation -> transformed workflow graph
workflow + seed -> heap event engine -> canonical JSON event trace
event trace -> time integrals and job timings -> metrics
base trace + scenario trace -> comparison + event evidence -> MD / JSON report
```

The simulator uses only Python's standard library and PyYAML. It never uses wall-clock time or GPU libraries. Trace events include arrivals, queue transitions, starts, finishes, resource occupancy transitions, branch decisions, skips, join arrivals and completions.

## DSL reference

All model and nested schema keys are checked. Units are user-declared and must be consistent: for example minutes, pounds per resource-minute and pounds of order value. Rates refer to one model time unit.

```yaml
name: FICTIONAL single-stage workflow
fictional: true
start: review
resources:
  reviewer:
    capacity: 1
    cost_rate: 0.5
arrivals:
  count: 20
  interval: {kind: fixed, value: 1}
  value: {kind: uniform, low: 0, high: 100}
steps:
  review:
    duration: {kind: fixed, value: 2}
    queue: reviews
    resources: {reviewer: 1}
    next: []
```

Model fields: `name` is a string, `fictional` must be true, `start` names an existing step, `resources` and `steps` are mappings, and `arrivals` declares a finite population. All steps must be reachable and the graph must be acyclic. Durations and arrival intervals accept `fixed` (`value >= 0`), `uniform` (`0 <= low <= high`), or `exponential` (`mean > 0`). Arrival `count` must be a positive integer. Optional arrival `value` uses the same distribution syntax and defaults to zero. The first arrival is at time zero; subsequent arrivals add sampled intervals.

Each resource declares positive integer `capacity` and nonnegative `cost_rate`. Each step declares `duration` and a nonempty `queue` name. Optional `resources` maps resource names to positive integer units not exceeding capacity, and defaults to no requirements. All required units are acquired atomically and held until the step finishes. Queues are unbounded FIFO, including when steps share a queue. Other queues can progress when one is blocked.

`next` is a list of `{step: name, probability: p}` branches, defaulting to terminal. Nonnegative probabilities must sum to one. A terminal step completes a job when no parallel work or pending join remains. Ordinary merges accept any incoming branch. Advanced coordination nodes use `fork: [step_a, step_b]` instead of `next`, and `join: 2` to wait for two incoming activations of the same job. Fork paths must reconverge exactly once on a matching join; the parallelise scenario generates this structure automatically. A malformed coordination graph that cannot drain raises `SimulationDeadlockError`. `auto_approve: threshold` skips a step when the arrival value is strictly below the threshold, consuming neither resources nor duration.

Named validation errors include `ModelSchemaError`, `HonestyError`, `ResourceError`, `DurationError`, `QueueError`, `BranchError`, `ReferenceError`, `CycleError`, `ReachabilityError`, `ArrivalError`, `ForkError`, `JoinError` and `ThresholdError`. Scenario failures are wrapped in `InvalidScenario` with the specific reason.

## Scenario change types

```yaml
name: FICTIONAL increase review capacity
changes:
  - type: add_capacity
    resource: reviewer
    amount: 1
```

Changes are applied in list order to a copy of the validated base model and the result is validated again.

| Type | Fields | Behaviour |
| --- | --- | --- |
| `remove_step` | `step` | Rewire incoming probabilities through outgoing branches and delete the step. Removing the start requires one successor. Referenced terminal steps and fork targets cannot be removed. |
| `parallelise` | `steps: [a, b, ...]` | Replace a contiguous unconditional chain with a zero-duration fork and join. Branch tasks retain durations, queues and resource needs, and contend normally. External incoming edges to later chain steps are rejected. |
| `auto_approve` | `step`, `threshold` | Skip this step for jobs with value strictly below the nonnegative threshold; continue along its declared branches. |
| `add_capacity` | `resource`, `amount` | Add a positive integer number of units to an existing resource. |
| `change_arrival_rate` | `rate` | Replace arrival intervals with exponential intervals of mean `1 / rate`; population count stays fixed. |

## Determinism and simulation semantics

All randomness comes from one local `random.Random(seed)` instance. Arrivals and job values are sampled first in job order, then durations and branch draws in event order. Equal-time events follow insertion sequence; resource dispatch runs after each event, so a zero-wait enqueue can briefly appear in the trace. Maps and serialisation are ordered and JSON ends with a newline. The same model, seed, Python runtime and implementation produce byte-identical traces and metrics. Changing a scenario can change random draw order, so using the same seed does not imply paired identical durations for every job. Cross-Python-version random distribution compatibility is not promised.

The run drains all declared arrivals rather than stopping at an arbitrary horizon. Time begins at zero and the horizon is the last trace event. No retries, failures, calendars, preemption, finite queue limits, correlated distributions or real company calibration are inferred.

## Metrics and comparator catalogue

| Metric | Trace-derived definition |
| --- | --- |
| Throughput | Completed jobs divided by horizon. |
| Mean / p95 lead time | Completion minus arrival time; p95 uses the nearest-rank definition. |
| Queue max / mean | Maximum recorded waiting occupancy / occupancy integral divided by horizon. Max includes instantaneous enqueue events; mean excludes service time. |
| Resource utilisation | Busy-unit time integral divided by capacity times horizon. |
| Cost proxy | Busy-unit time multiplied by the declared per-resource rate, summed over resources. Idle capacity has no cost in this proxy. |

Zero-horizon ratios are defined as zero. `compare` produces before, after and signed after-minus-before deltas, ranks the largest absolute mean queue change, and includes indexed peak queue and skip events as supporting evidence. This is descriptive evidence, not a causal attribution or a financial forecast. Report bottlenecks rank queues by mean occupancy, then maximum occupancy, then name. Reports include the model summary, metrics, bottlenecks, and optional scenario comparison.

## Fixtures and tests

`fixtures` generates a synthetic receive -> pick -> pack -> QA -> ship process with a planted QA bottleneck and two fictional scenarios: add QA capacity and auto-approve low-value orders. No external data or network access is used. Tests cover named schema errors, invalid scenarios, exact hand-computed traces and metrics, resource contention, forks and joins, probabilistic branches, seed and fixture determinism, scenario improvements, report banners, and a subprocess CLI end-to-end workflow.
