# Adversarial Test Classes

Each test defines an attack action, an expected denial, observable evidence, and cleanup.

1. Mount: attempt reads and writes outside declared mounts.
2. Credential: probe dummy secret locations and inherited environment variables.
3. Network: attempt undeclared destinations and methods.
4. Command: attempt unavailable command paths and host control sockets.
5. Resource: exceed time, process, memory, disk, and log limits.
6. Supply chain: introduce an unapproved dependency or mutable image reference.
7. Side effect: attempt an external write without a broker.
8. Duplicate execution: repeat the same action and inspect side effects.
9. Cleanup: verify guest, scratch, grants, and credentials are removed.
