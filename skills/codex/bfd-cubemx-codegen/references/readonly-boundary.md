# Read-Only Boundary

This skill is limited to regeneration from an existing `.ioc`.

## Allowed CubeMX commands

- `config load <ioc>`
- `project generate`
- `exit`

## Forbidden CubeMX commands

- `load <mcu>`
- `loadboard ...`
- `config save ...`
- `config saveas ...`
- `project name ...`
- `project path ...`
- `project toolchain ...`
- `setDriver ...`
- Any command that changes peripheral, clock, GPIO, middleware, or project configuration

## Verification rule

The helper script must compare the `.ioc` hash before and after generation.
If the hash changes, the run must fail and restore the original `.ioc` bytes.
