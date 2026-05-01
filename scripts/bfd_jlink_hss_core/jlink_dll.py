"""Native libjlinkarm access for BFD-Kit HSS sampling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import ctypes
import os
import sys
from typing import Iterable, Optional

from .env import ProbeInfo


INTERFACE_TO_TIF = {
    "JTAG": 0,
    "SWD": 1,
}


class JLinkDllError(RuntimeError):
    """Raised when libjlinkarm operations fail."""


def normalize_platform_name(platform_name: Optional[str] = None) -> str:
    raw = (platform_name or sys.platform).strip().lower()
    if raw.startswith("win"):
        return "windows"
    if raw.startswith("linux"):
        return "linux"
    if raw.startswith("darwin"):
        return "darwin"
    return raw


def default_jlink_dll_placeholder(platform_name: Optional[str] = None) -> str:
    normalized = normalize_platform_name(platform_name)
    if normalized == "windows":
        return r"<JLINK_INSTALL_DIR>\JLink_x64.dll"
    return "<JLINK_INSTALL_DIR>/libjlinkarm.so"


def default_jlink_dll_hints(platform_name: Optional[str] = None) -> list[str]:
    normalized = normalize_platform_name(platform_name)
    if normalized == "windows":
        return [
            r"%JLINKARM_DLL%",
            r"%ProgramFiles%\SEGGER\JLink\JLink_x64.dll",
            r"%ProgramFiles(x86)%\SEGGER\JLink\JLink_x64.dll",
            default_jlink_dll_placeholder("windows"),
        ]
    return [
        "$JLINKARM_DLL",
        "/opt/SEGGER/JLink/libjlinkarm.so",
        "/usr/local/lib/libjlinkarm.so",
        default_jlink_dll_placeholder("linux"),
    ]


def iter_default_jlinkarm_dll_candidates(
    platform_name: Optional[str] = None,
    environ: Optional[dict[str, str]] = None,
) -> Iterable[str]:
    env = environ or os.environ
    normalized = normalize_platform_name(platform_name)
    env_path = env.get("JLINKARM_DLL")
    if env_path:
        yield env_path

    jlink_exe = env.get("JLINK_EXE")
    if jlink_exe:
        exe_dir = Path(jlink_exe).expanduser().parent
        if normalized == "windows":
            for name in ("JLink_x64.dll", "JLinkARM.dll"):
                yield str(exe_dir / name)
        else:
            for name in ("libjlinkarm.so", "libjlinkarm.so.0", "libjlinkarm.so.1"):
                yield str(exe_dir / name)

    if normalized == "windows":
        seen: set[str] = set()
        roots = [
            env.get("ProgramW6432"),
            env.get("ProgramFiles"),
            env.get("ProgramFiles(x86)"),
        ]
        for root in roots:
            if not root:
                continue
            base = Path(root)
            direct_dir = base / "SEGGER" / "JLink"
            for candidate_dir in [direct_dir, *sorted(base.glob("SEGGER/JLink*"))]:
                for name in ("JLink_x64.dll", "JLinkARM.dll"):
                    candidate = candidate_dir / name
                    rendered = str(candidate)
                    if rendered in seen:
                        continue
                    seen.add(rendered)
                    yield rendered
        return

    for pattern in (
        "/opt/SEGGER/JLink*/libjlinkarm.so",
        "/opt/SEGGER/JLink*/libjlinkarm.so.*",
        "/usr/lib/libjlinkarm.so",
        "/usr/lib64/libjlinkarm.so",
        "/usr/local/lib/libjlinkarm.so",
    ):
        for path in sorted(Path("/").glob(pattern.lstrip("/"))):
            if path.is_file():
                yield str(path)


def resolve_jlinkarm_dll(
    candidates: Optional[Iterable[Optional[str]]] = None,
    platform_name: Optional[str] = None,
) -> Path:
    search_candidates = list(candidates) if candidates is not None else list(iter_default_jlinkarm_dll_candidates(platform_name=platform_name))
    for candidate in search_candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
    hints = ", ".join(default_jlink_dll_hints(platform_name))
    raise JLinkDllError(f"J-Link native DLL not found; set JLINKARM_DLL or install it at one of: {hints}")


def choose_probe(probes: list[ProbeInfo], usb_sn: Optional[str]) -> ProbeInfo:
    if usb_sn:
        for probe in probes:
            if probe.serial_number == usb_sn:
                return probe
        raise JLinkDllError(f"requested J-Link serial number not found: {usb_sn}")
    if not probes:
        raise JLinkDllError("no J-Link probes detected")
    if len(probes) == 1:
        return probes[0]
    serials = ", ".join(probe.serial_number for probe in probes)
    raise JLinkDllError(f"multiple J-Link probes detected; pass --usb-sn explicitly ({serials})")


@dataclass
class HssCaps:
    raw_words: list[int]
    max_sampling_rate_khz_inferred: int
    max_buffer_bytes_inferred: int
    raw_word_2_unknown: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HssBlock:
    address: int
    byte_size: int


class _NativeHssBlock(ctypes.Structure):
    _fields_ = [
        ("address", ctypes.c_uint32),
        ("byte_size", ctypes.c_uint32),
        # SEGGER expects 16-byte descriptors; the trailing words are currently zero.
        ("flags", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]


class JLinkDll:
    """Thin wrapper around the libjlinkarm functions used by the HSS CLI."""

    def __init__(self, dll_path: Optional[str | Path] = None, dll=None) -> None:
        self.dll_path = Path(dll_path).expanduser().resolve() if dll_path else resolve_jlinkarm_dll()
        self._dll = dll if dll is not None else self._load_native_dll(self.dll_path)
        self._is_open = False
        self._configure_prototypes()

    @staticmethod
    def _load_native_dll(dll_path: Path):
        normalized = normalize_platform_name()
        if normalized == "windows":
            return ctypes.WinDLL(str(dll_path))
        return ctypes.CDLL(str(dll_path))

    def _configure_prototypes(self) -> None:
        self._dll.JLINKARM_Open.restype = ctypes.c_char_p
        self._dll.JLINKARM_Close.restype = None
        self._dll.JLINKARM_EMU_SelectByUSBSN.argtypes = [ctypes.c_int]
        self._dll.JLINKARM_EMU_SelectByUSBSN.restype = ctypes.c_int
        self._dll.JLINKARM_ExecCommand.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        self._dll.JLINKARM_ExecCommand.restype = ctypes.c_int
        self._dll.JLINKARM_TIF_Select.argtypes = [ctypes.c_int]
        self._dll.JLINKARM_TIF_Select.restype = ctypes.c_int
        self._dll.JLINKARM_SetSpeed.argtypes = [ctypes.c_int]
        self._dll.JLINKARM_SetSpeed.restype = ctypes.c_int
        self._dll.JLINKARM_Connect.restype = ctypes.c_int
        self._dll.JLINKARM_GetSN.restype = ctypes.c_int
        self._dll.JLINK_HSS_GetCaps.argtypes = [ctypes.c_void_p]
        self._dll.JLINK_HSS_GetCaps.restype = ctypes.c_int
        self._dll.JLINK_HSS_Start.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self._dll.JLINK_HSS_Start.restype = ctypes.c_int
        self._dll.JLINK_HSS_Read.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._dll.JLINK_HSS_Read.restype = ctypes.c_int
        self._dll.JLINK_HSS_Stop.restype = ctypes.c_int

    def open(self, usb_sn: Optional[str] = None) -> None:
        if usb_sn:
            self._check_rc(
                self._dll.JLINKARM_EMU_SelectByUSBSN(int(usb_sn)),
                f"failed to select J-Link USB serial number {usb_sn}",
            )
        error = self._dll.JLINKARM_Open()
        if error:
            message = error.decode(errors="ignore") if isinstance(error, bytes) else str(error)
            raise JLinkDllError(message)
        self._is_open = True

    def close(self) -> None:
        if self._is_open:
            self._dll.JLINKARM_Close()
            self._is_open = False

    def exec_command(self, command: str, buffer_size: int = 512) -> str:
        self._require_open()
        output = ctypes.create_string_buffer(buffer_size)
        self._check_rc(
            self._dll.JLINKARM_ExecCommand(command.encode("utf-8"), output, len(output)),
            f"J-Link command failed: {command}",
        )
        return output.value.decode(errors="ignore")

    def connect(self, *, device: str, interface: str, speed_khz: int) -> int:
        self._require_open()
        self.exec_command("SuppressGUI = 1")
        self.exec_command(f"Device = {device}")
        tif = INTERFACE_TO_TIF.get(interface.upper())
        if tif is None:
            raise JLinkDllError(f"unsupported target interface: {interface}")
        self._check_rc(self._dll.JLINKARM_TIF_Select(tif), f"failed to select target interface {interface}")
        self._check_rc(self._dll.JLINKARM_SetSpeed(int(speed_khz)), f"failed to set J-Link speed {speed_khz} kHz")
        self._check_rc(self._dll.JLINKARM_Connect(), "failed to connect to target")
        return int(self._dll.JLINKARM_GetSN())

    def get_hss_caps(self) -> HssCaps:
        self._require_open()
        buffer = (ctypes.c_uint32 * 16)()
        self._check_rc(self._dll.JLINK_HSS_GetCaps(buffer), "failed to query J-Link HSS capabilities")
        raw_words = [int(word) for word in buffer]
        return HssCaps(
            raw_words=raw_words,
            max_sampling_rate_khz_inferred=raw_words[0],
            max_buffer_bytes_inferred=raw_words[1],
            raw_word_2_unknown=raw_words[2],
        )

    def hss_start(self, blocks: list[HssBlock], period_us: int, flags: int = 0) -> None:
        self._require_open()
        if not blocks:
            raise JLinkDllError("at least one HSS data block is required")
        native_blocks = (_NativeHssBlock * len(blocks))()
        for index, block in enumerate(blocks):
            native_blocks[index].address = int(block.address)
            native_blocks[index].byte_size = int(block.byte_size)
        self._check_rc(
            self._dll.JLINK_HSS_Start(native_blocks, len(blocks), int(period_us), int(flags)),
            "failed to start J-Link HSS",
        )

    def hss_read(self, buffer_size: int) -> bytes:
        self._require_open()
        if buffer_size <= 0:
            raise JLinkDllError("buffer_size must be greater than zero")
        buffer = (ctypes.c_ubyte * buffer_size)()
        bytes_read = int(self._dll.JLINK_HSS_Read(buffer, len(buffer)))
        if bytes_read < 0:
            raise JLinkDllError(f"failed to read J-Link HSS data (rc={bytes_read})")
        return bytes(buffer[:bytes_read])

    def hss_stop(self) -> None:
        self._require_open()
        self._check_rc(self._dll.JLINK_HSS_Stop(), "failed to stop J-Link HSS")

    def _require_open(self) -> None:
        if not self._is_open:
            raise JLinkDllError("J-Link DLL session is not open")

    @staticmethod
    def _check_rc(rc: int, message: str) -> None:
        if rc != 0:
            raise JLinkDllError(f"{message} (rc={rc})")
