from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Optional


RTT_SIGNATURE = b"SEGGER RTT"
RTT_DESCRIPTOR_SIZE = 24
RTT_HEADER_SIZE = 24


@dataclass(frozen=True)
class RttBufferDescriptor:
    index: int
    descriptor_addr: int
    s_name_ptr: int
    p_buffer: int
    size_of_buffer: int
    wr_off: int
    rd_off: int
    flags: int

    @property
    def wr_off_addr(self) -> int:
        return self.descriptor_addr + 12

    @property
    def rd_off_addr(self) -> int:
        return self.descriptor_addr + 16


@dataclass(frozen=True)
class RttControlBlock:
    address: int
    max_num_up_buffers: int
    max_num_down_buffers: int
    buffers: tuple[RttBufferDescriptor, ...]


def find_rtt_signature(blob: bytes) -> Optional[int]:
    offset = blob.find(RTT_SIGNATURE)
    if offset < 0:
        return None
    return offset


def parse_rtt_control_block(data: bytes, *, base_address: int) -> RttControlBlock:
    if len(data) < RTT_HEADER_SIZE:
        raise ValueError("RTT control block data too short")

    signature, max_up, max_down = struct.unpack_from("<16sII", data, 0)
    if not signature.startswith(RTT_SIGNATURE):
        raise ValueError("RTT signature not found at control block base")

    buffer_count = max_up + max_down
    expected_size = RTT_HEADER_SIZE + buffer_count * RTT_DESCRIPTOR_SIZE
    if len(data) < expected_size:
        raise ValueError("RTT control block data truncated")

    buffers = []
    for index in range(buffer_count):
        desc_offset = RTT_HEADER_SIZE + index * RTT_DESCRIPTOR_SIZE
        desc_addr = base_address + desc_offset
        s_name_ptr, p_buffer, size_of_buffer, wr_off, rd_off, flags = struct.unpack_from(
            "<6I", data, desc_offset
        )
        buffers.append(
            RttBufferDescriptor(
                index=index,
                descriptor_addr=desc_addr,
                s_name_ptr=s_name_ptr,
                p_buffer=p_buffer,
                size_of_buffer=size_of_buffer,
                wr_off=wr_off,
                rd_off=rd_off,
                flags=flags,
            )
        )

    return RttControlBlock(
        address=base_address,
        max_num_up_buffers=max_up,
        max_num_down_buffers=max_down,
        buffers=tuple(buffers),
    )


def extract_unread_bytes(buffer: bytes, *, rd_off: int, wr_off: int) -> bytes:
    if rd_off == wr_off:
        return b""
    if rd_off < wr_off:
        return buffer[rd_off:wr_off]
    return buffer[rd_off:] + buffer[:wr_off]
