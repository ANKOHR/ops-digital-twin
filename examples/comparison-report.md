# Ops Digital Twin report

DECLARED MODEL OF A FICTIONAL PROCESS: This simulates a declared model, not a real company, and does not predict real company outcomes. Results follow from the model's assumptions. Predictions are only as good as the model: a wrong model gives wrong answers.

Model: FICTIONAL synthetic order fulfilment
Seed: 42. Steps: 5. Arrivals: 80.

| Metric | Value |
| --- | ---: |
| completed | 80 |
| cost_proxy | 727.65 |
| horizon | 324.825 |
| mean_lead_time | 126.656 |
| p95_lead_time | 233.272 |
| queues.QA.max | 61 |
| queues.QA.mean | 29.9504 |
| queues.pack.max | 1 |
| queues.pack.mean | 0 |
| queues.pick.max | 1 |
| queues.pick.mean | 0 |
| queues.receive.max | 1 |
| queues.receive.mean | 0 |
| queues.ship.max | 1 |
| queues.ship.mean | 0 |
| resource_utilisation.QA | 0.996921 |
| resource_utilisation.pack | 0.0615716 |
| resource_utilisation.pick | 0.0615716 |
| resource_utilisation.receive | 0.0615716 |
| resource_utilisation.ship | 0.0615716 |
| throughput | 0.246286 |

Bottlenecks ranked by time-weighted mean queue length: QA, pack, pick, receive, ship.

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| completed | 80 | 80 | +0 |
| cost_proxy | 727.65 | 733.056 | +5.40572 |
| horizon | 324.825 | 86.648 | -238.177 |
| mean_lead_time | 126.656 | 6.34441 | -120.311 |
| p95_lead_time | 233.272 | 8.35015 | -224.922 |
| queues.QA.max | 61 | 4 | -57 |
| queues.QA.mean | 29.9504 | 1.13367 | -28.8167 |
| queues.pack.max | 1 | 1 | +0 |
| queues.pack.mean | 0 | 0 | +0 |
| queues.pick.max | 1 | 1 | +0 |
| queues.pick.mean | 0 | 0 | +0 |
| queues.receive.max | 1 | 1 | +0 |
| queues.receive.mean | 0 | 0 | +0 |
| queues.ship.max | 1 | 2 | +1 |
| queues.ship.mean | 0 | 0.032251 | +0.032251 |
| resource_utilisation.QA | 0.996921 | 0.942111 | -0.0548101 |
| resource_utilisation.pack | 0.0615716 | 0.230819 | +0.169247 |
| resource_utilisation.pick | 0.0615716 | 0.230819 | +0.169247 |
| resource_utilisation.receive | 0.0615716 | 0.230819 | +0.169247 |
| resource_utilisation.ship | 0.0615716 | 0.230819 | +0.169247 |
| throughput | 0.246286 | 0.923276 | +0.67699 |

Largest absolute change in time-weighted mean queue length; peak queue and skip events are supporting evidence, not a causal proof.

```json
[
  {
    "event": {
      "job": 79,
      "length": 61,
      "queue": "QA",
      "step": "QA",
      "time": 79.75,
      "type": "enqueue"
    },
    "event_index": 2076,
    "run": "base"
  },
  {
    "event": {
      "job": 59,
      "length": 4,
      "queue": "QA",
      "step": "QA",
      "time": 59.75,
      "type": "enqueue"
    },
    "event_index": 2067,
    "run": "scenario"
  }
]
```
