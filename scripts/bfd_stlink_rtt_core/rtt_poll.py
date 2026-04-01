from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .programmer_cli import STM32ProgrammerCLI
from .rtt_layout import (
    RTT_DESCRIPTOR_SIZE,
    RTT_HEADER_SIZE,
    RttControlBlock,
    find_rtt_signature,
    parse_rtt_control_block,
)


def resolve_rtt_symbol(elf_path: str, symbol: str = "_SEGGER_RTT") -> Optional[int]:
    result = subprocess.run(
        ["arm-none-eabi-nm", "-n", elf_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    pattern = re.compile(rf"^([0-9a-fA-F]+)\s+\w\s+{re.escape(symbol)}$")
    for line in result.stdout.splitlines():
        match = pattern.match(line.strip())
        if match:
            return int(match.group(1), 16)
    return None


def scan_for_rtt_signature(
    client: STM32ProgrammerCLI, *, ram_start: int, ram_size: int
) -> Optional[int]:
    blob = client.read_bytes(ram_start, ram_size)
    offset = find_rtt_signature(blob)
    if offset is None:
        return None
    return ram_start + offset


def load_rtt_control_block(
    client: STM32ProgrammerCLI, control_block_addr: int
) -> RttControlBlock:
    header = client.read_bytes(control_block_addr, RTT_HEADER_SIZE)
    max_up = int.from_bytes(header[16:20], "little")
    max_down = int.from_bytes(header[20:24], "little")
    total_size = RTT_HEADER_SIZE + (max_up + max_down) * RTT_DESCRIPTOR_SIZE
    raw = client.read_bytes(control_block_addr, total_size)
    return parse_rtt_control_block(raw, base_address=control_block_addr)


def poll_up_channel(
    client: STM32ProgrammerCLI, control_block_addr: int, *, channel: int
) -> Tuple[bytes, RttControlBlock]:
    block = load_rtt_control_block(client, control_block_addr)
    if channel < 0 or channel >= block.max_num_up_buffers:
        raise IndexError(f"invalid RTT up-buffer channel: {channel}")

    descriptor = block.buffers[channel]
    if descriptor.size_of_buffer == 0 or descriptor.rd_off == descriptor.wr_off:
        return b"", block

    if descriptor.rd_off < descriptor.wr_off:
        payload = client.read_bytes(
            descriptor.p_buffer + descriptor.rd_off,
            descriptor.wr_off - descriptor.rd_off,
        )
    else:
        tail = client.read_bytes(
            descriptor.p_buffer + descriptor.rd_off,
            descriptor.size_of_buffer - descriptor.rd_off,
        )
        head = client.read_bytes(descriptor.p_buffer, descriptor.wr_off)
        payload = tail + head

    client.write_u32(descriptor.rd_off_addr, descriptor.wr_off)
    return payload, block
