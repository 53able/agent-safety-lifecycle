# Profile Rules

Apply the first matching rule from highest to lowest impact.

1. `human-gated-impact`: irreversible or high-impact action is required.
2. `brokered-write`: an external write or credential-bound action is required.
3. `isolated-execution`: command execution, arbitrary binary execution, or file mutation is required.
4. `read-only`: repository or document inspection is required without mutation.
5. `no-exec`: only an explanation, plan, or proposed patch is required.

Unknown facts never justify a larger ambient permission. Keep the smaller profile and request the missing fact.
