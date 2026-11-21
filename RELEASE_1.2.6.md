# AgentFlow Runtime v1.2.6

## Change

Regression Guard persists an atomic JSON checkpoint after every test module. The `complete` field remains `false` until all modules have finished. This preserves partial evidence after interruption without representing it as a passing full regression. Atomic replacement uses a temporary file in the report directory and fsync before replace.

## Validation and limitations

The new tests exercise incomplete/complete reports and failed atomic replacement. The full suite, native CI, Docker/PostgreSQL and QEMU require separate verification; no claim of production security or isolation is made.
