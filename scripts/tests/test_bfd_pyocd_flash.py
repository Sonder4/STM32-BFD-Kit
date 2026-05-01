import argparse
import importlib.util
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_pyocd_flash.py"
SPEC = importlib.util.spec_from_file_location("bfd_pyocd_flash", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_build_load_command_supports_force_program():
    args = argparse.Namespace(
        firmware="app.hex",
        target="stm32h723xx",
        frequency="100000",
        erase="sector",
        uid="6d1395736d13957301",
        force_program=True,
        no_reset=False,
    )

    command = MODULE.build_load_command(args, "/venv/bin/pyocd")

    assert command[:2] == ["/venv/bin/pyocd", "load"]
    assert command[command.index("-t") + 1] == "stm32h723xx"
    assert command[command.index("-u") + 1] == "6d1395736d13957301"
    assert "-O" in command
    assert "smart_flash=false" in command


def test_parse_verify_range_supports_hex_address_and_decimal_words():
    assert MODULE.parse_verify_range("0x0802b1d4:8") == (0x0802B1D4, 8)


def test_build_verify_command_uses_explicit_address_and_word_count():
    args = argparse.Namespace(
        target="stm32h723xx",
        frequency="100000",
        uid="6d1395736d13957301",
        elf="app.elf",
    )

    command = MODULE.build_verify_command(args, "/venv/bin/pyocd", 0x0802B1D4, 8)

    assert command[:2] == ["/venv/bin/pyocd", "commander"]
    assert command[command.index("-c") + 1] == "read32 0x0802b1d4 32"
    assert command[command.index("--elf") + 1] == "app.elf"


def test_read_image_words_from_bin(tmp_path):
    firmware = tmp_path / "app.bin"
    firmware.write_bytes(bytes.fromhex("00000220 d9c10108 b5bd0108 bd01ff08".replace(" ", "")))

    words = MODULE.read_image_words(firmware, 0x08000000, 4)

    assert words == [0x20020000, 0x0801C1D9, 0x0801BDB5, 0x08FF01BD]


def test_read_image_words_from_intel_hex(tmp_path):
    firmware = tmp_path / "app.hex"
    firmware.write_text(
        "\n".join(
            [
                ":020000040800F2",
                ":1000000000000220D9C10108B5BD0108BDBD0108E1",
                ":00000001FF",
            ]
        )
        + "\n",
        encoding="ascii",
    )

    words = MODULE.read_image_words(firmware, 0x08000000, 4)

    assert words == [0x20020000, 0x0801C1D9, 0x0801BDB5, 0x0801BDBD]


def test_parse_read32_words_ignores_non_memory_lines():
    output = """
Setting SWD clock to 100 kHz
08000000:  20020000 0801c1d9 0801bdb5 0801bdbd    | ...............|
08000010:  0801bdc5 0801bdcd 0801bdd5 00000000    |................|
"""

    assert MODULE.parse_read32_words(output) == [
        0x20020000,
        0x0801C1D9,
        0x0801BDB5,
        0x0801BDBD,
        0x0801BDC5,
        0x0801BDCD,
        0x0801BDD5,
        0x00000000,
    ]
