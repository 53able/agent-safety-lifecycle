# State Machine

The authoritative state and edge definition is [`../assets/state-machine.json`](../assets/state-machine.json). This page explains that machine-readable policy; consumers must not parse this Markdown.

Allowed nonterminal transitions:

- `PLANNED -> RUNNING`
- `RUNNING -> RETRYING`
- `RETRYING -> RUNNING`
- `RUNNING -> AWAITING_ELEVATION`
- `AWAITING_ELEVATION -> RUNNING`
- `RUNNING -> AWAITING_RESULT_GATE`
- Any active state -> `COMPLETED`, `FAILED`, `BLOCKED`, or `STOPPED`

`COMPLETED`, `FAILED`, `BLOCKED`, and `STOPPED` are terminal. The transition CLI retains its existing edge-only behavior, including active-to-`COMPLETED`. Applications must enforce the additional result-gate binding before accepting completion; the replay prototype rejects `COMPLETED` until report v2 exists.
