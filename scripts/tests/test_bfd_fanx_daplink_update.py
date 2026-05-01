import importlib.util
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_fanx_daplink_update.py"
SPEC = importlib.util.spec_from_file_location("bfd_fanx_daplink_update", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_proc_mounts_detects_daplink_and_bootloader():
    mounts = MODULE.parse_proc_mounts(
        """
/dev/sda1 /media/xuan/DAPLINK vfat rw 0 0
/dev/sdb1 /media/xuan/BOOTLOADER vfat rw 0 0
/dev/nvme0n1p2 / ext4 rw 0 0
"""
    )

    assert [mount.kind for mount in mounts] == ["interface", "bootloader"]
    assert mounts[0].label == "DAPLINK"
    assert mounts[1].path == "/media/xuan/BOOTLOADER"


def test_parse_proc_mounts_decodes_escaped_spaces():
    mounts = MODULE.parse_proc_mounts("/dev/sda1 /media/xuan/DAPLINK\\040TEST vfat rw 0 0\n")

    assert mounts == []
    assert MODULE.decode_proc_mount_path("/media/xuan/BOOTLOADER\\040A") == "/media/xuan/BOOTLOADER A"


def test_find_mount_returns_requested_kind():
    mounts = [
        MODULE.MountInfo(label="DAPLINK", path="/media/xuan/DAPLINK", kind="interface"),
        MODULE.MountInfo(label="BOOTLOADER", path="/media/xuan/BOOTLOADER", kind="bootloader"),
    ]

    assert MODULE.find_mount("bootloader", mounts).path == "/media/xuan/BOOTLOADER"
    assert MODULE.find_mount("missing", mounts) is None


def test_copy_firmware_dry_run_does_not_write(tmp_path):
    firmware = tmp_path / "FanX_Tek_DAPLink_High1_V261.bin"
    firmware.write_bytes(b"encrypted")
    mount_path = tmp_path / "BOOTLOADER"
    mount_path.mkdir()
    mount = MODULE.MountInfo(label="BOOTLOADER", path=str(mount_path), kind="bootloader")

    destination = MODULE.copy_firmware_to_bootloader(firmware, mount, execute=False)

    assert destination == mount_path / firmware.name
    assert not destination.exists()


def test_write_empty_command_dry_run_does_not_write(tmp_path):
    mount_path = tmp_path / "DAPLINK"
    mount_path.mkdir()
    mount = MODULE.MountInfo(label="DAPLINK", path=str(mount_path), kind="interface")

    command = MODULE.write_empty_command(mount, MODULE.START_BOOTLOADER_COMMAND, execute=False)

    assert command == mount_path / "START_BL.ACT"
    assert not command.exists()
