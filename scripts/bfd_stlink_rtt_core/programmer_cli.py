from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class ProgrammerCliError(RuntimeError):
    """Raised when STM32_Programmer_CLI cannot complete the requested action."""


def resolve_programmer_cli(explicit_path: Optional[str] = None) -> str:
    candidate = (
        explicit_path
        or os.environ.get("STM32_PROGRAMMER_CLI")
        or shutil.which("STM32_Programmer_CLI")
        or "/opt/st/stm32cubeclt_1.19.0/STM32CubeProgrammer/bin/STM32_Programmer_CLI"
    )

    if Path(candidate).is_file():
        return candidate

    resolved = shutil.which(candidate)
    if resolved:
        return resolved

    raise ProgrammerCliError(f"STM32_Programmer_CLI not found: {candidate}")


class STM32ProgrammerCLI:
    def __init__(
        self,
        *,
        cli_path: Optional[str] = None,
        interface: str = "SWD",
        speed_khz: int = 4000,
        connect_mode: str = "UR",
        reset_mode: str = "HWrst",
        serial_number: Optional[str] = None,
        quiet: bool = True,
    ) -> None:
        self.cli_path = resolve_programmer_cli(cli_path)
        self.interface = interface
        self.speed_khz = int(speed_khz)
        self.connect_mode = connect_mode
        self.reset_mode = reset_mode
        self.serial_number = serial_number
        self.quiet = quiet

    def _base_command(self) -> list[str]:
        command = [self.cli_path]
        if self.quiet:
            command.append("-q")
        command.extend(
            [
                "-c",
                f"port={self.interface}",
                f"mode={self.connect_mode}",
                f"reset={self.reset_mode}",
                f"freq={self.speed_khz}",
            ]
        )
        if self.serial_number:
            command.append(f"sn={self.serial_number}")
        return command

    def _run(self, args: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
        command = self._base_command() + args
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            detail = stderr or stdout or f"exit code {result.returncode}"
            raise ProgrammerCliError(detail)
        return result

    def read_bytes(self, address: int, size: int) -> bytes:
        if size < 0:
            raise ValueError("size must be non-negative")
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            self._run(["-u", f"0x{address:08X}", str(size), str(temp_path)], timeout=120.0)
            data = temp_path.read_bytes()
        finally:
            temp_path.unlink(missing_ok=True)
        return data[:size]

    def write_u32(self, address: int, value: int) -> None:
        self._run(["-w32", f"0x{address:08X}", f"0x{value & 0xFFFFFFFF:08X}", "-nv"])
