import struct
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


from bfd_stlink_rtt_core.rtt_layout import (
    extract_unread_bytes,
    find_rtt_signature,
    parse_rtt_control_block,
)
from bfd_stlink_rtt_core.rtt_poll import poll_up_channel


def _make_control_block_bytes() -> bytes:
    sig = b"SEGGER RTT" + b"\x00" * (16 - len("SEGGER RTT"))
    up_desc = struct.pack("<6I", 0, 0x20001000, 16, 4, 1, 1)
    down_desc = struct.pack("<6I", 0, 0x20002000, 16, 0, 0, 0)
    return sig + struct.pack("<II", 1, 1) + up_desc + down_desc


def test_find_rtt_signature_returns_offset():
    blob = b"\x00" * 19 + _make_control_block_bytes() + b"\xFF" * 8
    assert find_rtt_signature(blob) == 19


def test_parse_rtt_control_block_decodes_buffers():
    block = parse_rtt_control_block(_make_control_block_bytes(), base_address=0x20010000)
    assert block.address == 0x20010000
    assert block.max_num_up_buffers == 1
    assert block.max_num_down_buffers == 1
    assert block.buffers[0].p_buffer == 0x20001000
    assert block.buffers[0].wr_off == 4
    assert block.buffers[0].rd_off == 1
    assert block.buffers[1].p_buffer == 0x20002000


def test_extract_unread_bytes_handles_wraparound():
    buf = b"ABCDEFGH"
    assert extract_unread_bytes(buf, rd_off=6, wr_off=2) == b"GHAB"
    assert extract_unread_bytes(buf, rd_off=1, wr_off=4) == b"BCD"


def test_poll_up_channel_reads_payload_and_updates_rd_off():
    class FakeClient:
        def __init__(self):
            self.memory = {}
            self.writes = []

        def read_bytes(self, address: int, size: int) -> bytes:
            return self.memory[address][:size]

        def write_u32(self, address: int, value: int) -> None:
            self.writes.append((address, value))

    client = FakeClient()
    control_block_addr = 0x20010000
    control_block = _make_control_block_bytes()
    client.memory[control_block_addr] = control_block
    client.memory[0x20001001] = b"BCD"

    payload, block = poll_up_channel(client, control_block_addr, channel=0)
    assert payload == b"BCD"
    assert block.buffers[0].rd_off_addr == control_block_addr + 24 + 16
    assert client.writes == [(control_block_addr + 24 + 16, 4)]
