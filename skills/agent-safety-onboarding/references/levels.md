# Onboarding Levels

1. Proposal only: explain a change and produce a patch proposal without execution.
2. Read only: inspect a bounded input without mutation.
3. Isolated edit: create a patch in guest-local scratch.
4. Isolated execution: build and test inside a verified guest profile.
5. Result import: inspect and import an artifact through the result gate.
6. Brokered action: request one scoped external action with explicit approval.

No level grants production access automatically.
