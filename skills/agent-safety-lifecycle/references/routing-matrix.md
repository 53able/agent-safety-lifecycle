# Routing Matrix

| Condition | Next skill |
|---|---|
| Profile is unknown | `agent-task-risk-classifier` |
| Capabilities are not fixed | `agent-autonomy-envelope` |
| Isolation is not materialized | `agent-host-isolation` |
| Bounded execution is ready | `agent-run-supervisor` |
| Boundary is new or changed | `agent-boundary-adversary` |
| Artifacts leave the guest | `agent-result-gate` |
| A concrete failure exists | `failure-to-guardrail` |
| An incident or near miss exists | `agent-near-miss-review` |

Do not skip a missing step by treating it as passed. Record it as `UNVERIFIED` or `BLOCKED`.
