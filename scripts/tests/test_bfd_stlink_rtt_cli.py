import importlib.util
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_stlink_rtt.py"
SPEC = importlib.util.spec_from_file_location("bfd_stlink_rtt_cli", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_scan_window_supports_hex_values():
    start, size = MODULE.parse_scan_window("0x20000000:0x00030000")
    assert start == 0x20000000
    assert size == 0x00030000


def test_resolve_channel_prefers_role_mapping():
    assert MODULE.resolve_channel(role="diag", channel=None) == 1
    assert MODULE.resolve_channel(role=None, channel=3) == 3


def test_normalize_text_payload_strips_nuls():
    assert MODULE.normalize_text_payload(b"Log Init!\n\x00\x00\x00") == "Log Init!\n"


def test_programmer_cli_uses_freq_connect_parameter():
    from bfd_stlink_rtt_core.programmer_cli import STM32ProgrammerCLI

    cli = STM32ProgrammerCLI.__new__(STM32ProgrammerCLI)
    cli.cli_path = "/opt/st/stm32cubeclt_1.19.0/STM32CubeProgrammer/bin/STM32_Programmer_CLI"
    cli.interface = "SWD"
    cli.speed_khz = 4000
    cli.connect_mode = "UR"
    cli.reset_mode = "HWrst"
    cli.serial_number = None
    cli.quiet = True

    command = cli._base_command()
    assert "freq=4000" in command
    assert "speed=4000" not in command
