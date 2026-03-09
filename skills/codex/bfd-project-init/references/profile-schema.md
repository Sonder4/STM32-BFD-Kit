# BFD Active Profile Schema

## Canonical JSON

Path: `.codex/bfd/active_profile.json`

Top-level fields:

- `schema_version`
- `generated_at`
- `project`
- `mcu`
- `artifacts`
- `debug`
- `rtt`
- `runtime`
- `tooling`
- `capabilities`
- `gaps`
- `generated_files`

`runtime` includes:

- `profile_dir`
- `legacy_profile_dir`
- `profile_json`
- `profile_env`
- `legacy_profile_json`
- `legacy_profile_env`
- `ioc_json_dir`
- `profile_overrides_env`
- `fingerprint_version`
- `fingerprint`

## Canonical Env

Path: `.codex/bfd/active_profile.env`

Key variables:

- `STM32_PROFILE_DIR`
- `STM32_PROFILE_JSON`
- `STM32_PROFILE_ENV`
- `STM32_PROFILE_LEGACY_DIR`
- `STM32_PROFILE_LEGACY_JSON`
- `STM32_PROFILE_LEGACY_ENV`
- `STM32_PROFILE_FINGERPRINT`
- `STM32_PROFILE_FINGERPRINT_VERSION`
- `STM32_IOC_JSON_DIR`
- `STM32_PROFILE_OVERRIDES_ENV`
- `STM32_PROJECT_ROOT`
- `STM32_IOC`
- `STM32_FAMILY`
- `STM32_DEVICE`
- `STM32_IF`
- `STM32_SPEED_KHZ`
- `STM32_PROBE`
- `STM32_ELF`
- `STM32_HEX`
- `STM32_MAP`
- `STM32_STARTUP`
- `STM32_LINKER`
- `STM32_SVD`
- `STM32_CFG`
- `STM32_RTT_SYMBOL`
- `STM32_RTT_SCAN_WINDOW`

## Compatibility Mirror

Legacy mirror paths remain available under `.codex/stm32/bootstrap/`.

## Precedence

`CLI args > environment > .codex/bfd/active_profile.env/json > profile_overrides.env > fallback detection`
