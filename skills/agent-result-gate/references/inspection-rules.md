# Inspection Rules

Reject automatically when an artifact:
- escapes the declared artifact root,
- is a symbolic link or special file,
- exceeds declared file-count or byte limits,
- contains undeclared executables,
- requests a side effect outside the envelope.

Require review when:
- dependencies change,
- install scripts appear,
- generated code performs network or destructive operations,
- a patch modifies security-sensitive code,
- rollback is unclear.

Never convert a missing check into `IMPORTABLE`.
