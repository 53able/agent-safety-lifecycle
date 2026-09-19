# Guardrail Mapping

| Observed failure | Preferred guardrail |
|---|---|
| Undeclared file write | Read-only mount and guest-local scratch |
| Secret access | Remove injection and add dummy-secret denial test |
| Undeclared network | Default-deny network and destination allowlist |
| Excessive changes | File-count and diff-size limits |
| Runaway process | Wall-time, process, CPU, memory, disk, and log limits |
| Duplicate side effect | Idempotency key and duplicate-execution test |
| Dangerous dependency | Lockfile, digest, install-script, and registry checks |
| External write | Task-scoped host-side broker and approval condition |
