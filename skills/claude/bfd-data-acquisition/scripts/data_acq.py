#!/usr/bin/env python3
"""
STM32 Data Acquisition Script
通过J-Link/ST-Link接口实时采集STM32目标板数据

Usage:
    python data_acq.py --device ${STM32_DEVICE} --variable g_sensorData --count 1000
    python data_acq.py --device ${STM32_DEVICE} --address 0x20000000 --size 256 --count 100
    python data_acq.py --device ${STM32_DEVICE} --rtt --channel 0 --count 10000
"""

import argparse
import subprocess
import struct
import time
import csv
import json
import os
import sys
import shutil
from datetime import datetime
from typing import Optional, List, Dict, Any

DEFAULT_DEVICE = os.environ.get("STM32_DEVICE", "STM32H743VI")
DEFAULT_INTERFACE = os.environ.get("STM32_IF", "SWD")
DEFAULT_SPEED = int(os.environ.get("STM32_SPEED_KHZ", "4000"))

JLINK_EXE = shutil.which("JLinkExe") or "JLinkExe"
JLINK_GDB_SERVER = shutil.which("JLinkGDBServerCLExe") or "JLinkGDBServerCLExe"
JLINK_RTT_VIEWER = shutil.which("JLinkRTTLogger") or "JLinkRTTLogger"

STLINK_GDB_SERVER = shutil.which("ST-LINK_gdbserver") or "ST-LINK_gdbserver"


class DataAcquisition:
    def __init__(self, device: str, interface: str = "SWD", speed: int = 4000):
        self.device = device
        self.interface = interface
        self.speed = speed
        self.connected = False
        self.elf_file = None
        self.symbols: Dict[str, int] = {}

    def find_elf_file(self, search_dir: str = ".") -> Optional[str]:
        elf_files = []
        for root, dirs, files in os.walk(search_dir):
            for f in files:
                if f.endswith('.elf') or f.endswith('.axf'):
                    elf_files.append(os.path.join(root, f))
        if elf_files:
            return elf_files[0]
        return None

    def load_symbols(self, elf_file: str) -> bool:
        self.elf_file = elf_file
        try:
            result = subprocess.run(
                ["arm-none-eabi-nm", elf_file],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 3:
                        addr = int(parts[0], 16)
                        name = parts[2]
                        self.symbols[name] = addr
                return True
        except Exception as e:
            print(f"Warning: Could not load symbols: {e}")
        return False

    def get_symbol_address(self, name: str) -> Optional[int]:
        return self.symbols.get(name)

    def create_jlink_script(self, commands: List[str]) -> str:
        script_path = os.path.join(os.getcwd(), "jlink_temp.jlink")
        with open(script_path, 'w') as f:
            f.write(f"device {self.device}\n")
            f.write(f"si {self.interface}\n")
            f.write(f"speed {self.speed}\n")
            for cmd in commands:
                f.write(cmd + "\n")
            f.write("exit\n")
        return script_path

    def run_jlink_command(self, commands: List[str], timeout: int = 60) -> str:
        script_path = self.create_jlink_script(commands)
        try:
            result = subprocess.run(
                [JLINK_EXE, "-CommandFile", script_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return "Error: Command timed out"
        except Exception as e:
            return f"Error: {e}"
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)

    def read_memory(self, address: int, size: int, count: int = 1) -> List[int]:
        commands = [
            "connect",
            f"mem32 {hex(address)} {count * (size // 4)}",
        ]
        output = self.run_jlink_command(commands)
        values = []
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('0x') or line.startswith('0X'):
                try:
                    val = int(line.split('=')[1].strip(), 16)
                    values.append(val)
                except (ValueError, IndexError):
                    continue
        return values

    def read_variable(self, var_name: str, size: int = 4) -> Optional[int]:
        if var_name in self.symbols:
            addr = self.symbols[var_name]
            values = self.read_memory(addr, size, 1)
            return values[0] if values else None
        return None

    def read_memory_block(self, address: int, size: int) -> bytes:
        commands = [
            "connect",
            f"savebin temp_mem.bin {hex(address)} {size}",
        ]
        self.run_jlink_command(commands)
        
        bin_path = os.path.join(os.getcwd(), "temp_mem.bin")
        if os.path.exists(bin_path):
            with open(bin_path, 'rb') as f:
                data = f.read()
            os.remove(bin_path)
            return data
        return b''

    def sample_variable(self, var_name: str, count: int, interval_ms: int = 10) -> List[Dict[str, Any]]:
        if var_name not in self.symbols:
            print(f"Error: Variable '{var_name}' not found in symbols")
            return []
        
        addr = self.symbols[var_name]
        samples = []
        start_time = time.time()
        
        for i in range(count):
            elapsed = time.time() - start_time
            value = self.read_variable(var_name)
            if value is not None:
                samples.append({
                    'timestamp': elapsed,
                    'value': value
                })
            if interval_ms > 0:
                time.sleep(interval_ms / 1000.0)
        
        return samples

    def sample_memory_region(self, address: int, size: int, count: int, 
                            interval_ms: int = 100) -> List[Dict[str, Any]]:
        samples = []
        start_time = time.time()
        
        for i in range(count):
            elapsed = time.time() - start_time
            data = self.read_memory_block(address, size)
            if data:
                samples.append({
                    'timestamp': elapsed,
                    'size': size,
                    'data': list(data)
                })
            if interval_ms > 0:
                time.sleep(interval_ms / 1000.0)
        
        return samples

    def start_rtt_capture(self, channel: int, count: int, output_file: str):
        print(f"Starting RTT capture on channel {channel}...")
        print(f"Target device: {self.device}")
        print(f"Interface: {self.interface} @ {self.speed} kHz")
        
        rtt_script = f"""device {self.device}
si {self.interface}
speed {self.speed}
connect
rsetrttblock 0x20000000 0x1000
rsetrttblock 0x24000000 0x1000
"""
        script_path = "rtt_capture.jlink"
        with open(script_path, 'w') as f:
            f.write(rtt_script)
        
        print(f"RTT capture script created: {script_path}")
        print("Use JLinkRTTViewer.exe for interactive RTT capture")
        print(f"Command: {JLINK_RTT_VIEWER} -device {self.device} -if {self.interface} -speed {self.speed}")


def save_to_csv(data: List[Dict], output_file: str, format_type: str = "simple"):
    with open(output_file, 'w', newline='') as f:
        if format_type == "simple":
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'value'])
            for sample in data:
                writer.writerow([sample['timestamp'], sample['value']])
        elif format_type == "memory":
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'size', 'data_hex'])
            for sample in data:
                hex_data = ''.join(f'{b:02x}' for b in sample['data'])
                writer.writerow([sample['timestamp'], sample['size'], hex_data])


def save_to_json(data: List[Dict], output_file: str, metadata: Dict = None):
    output = {
        'metadata': metadata or {},
        'data': data
    }
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description='STM32 Data Acquisition Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --device ${STM32_DEVICE} --variable g_sensorData --count 1000
  %(prog)s --device ${STM32_DEVICE} --address 0x20000000 --size 256 --count 100
  %(prog)s --device ${STM32_DEVICE} --rtt --channel 0 --count 10000
        """
    )
    
    parser.add_argument('--device', '-d', default=DEFAULT_DEVICE,
                       help=f'Target device (default: {DEFAULT_DEVICE})')
    parser.add_argument('--interface', '-i', default=DEFAULT_INTERFACE,
                       choices=['SWD', 'JTAG'], help='Debug interface')
    parser.add_argument('--speed', '-s', type=int, default=DEFAULT_SPEED,
                       help=f'Interface speed in kHz (default: {DEFAULT_SPEED})')
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--variable', '-v', help='Variable name to monitor')
    group.add_argument('--address', '-a', help='Memory address (hex)')
    group.add_argument('--rtt', action='store_true', help='Use RTT mode')
    
    parser.add_argument('--size', type=int, default=4,
                       help='Memory region size in bytes')
    parser.add_argument('--count', '-c', type=int, default=100,
                       help='Number of samples')
    parser.add_argument('--rate', '-r', type=int, default=1000,
                       help='Sample rate in Hz')
    parser.add_argument('--interval', type=int,
                       help='Sample interval in ms (overrides rate)')
    parser.add_argument('--channel', type=int, default=0,
                       help='RTT channel number')
    parser.add_argument('--elf', '-e', help='ELF file path')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--format', '-f', choices=['csv', 'json'], default='csv',
                       help='Output format')
    
    args = parser.parse_args()
    
    acq = DataAcquisition(args.device, args.interface, args.speed)
    
    if args.interval:
        interval_ms = args.interval
    else:
        interval_ms = 1000 // args.rate if args.rate > 0 else 10
    
    if args.rtt:
        output_file = args.output or f"rtt_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        acq.start_rtt_capture(args.channel, args.count, output_file)
        return
    
    elf_file = args.elf
    if not elf_file:
        elf_file = acq.find_elf_file()
    
    if elf_file:
        print(f"Loading symbols from: {elf_file}")
        acq.load_symbols(elf_file)
        print(f"Loaded {len(acq.symbols)} symbols")
    
    output_file = args.output
    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"data_{timestamp}.{args.format}"
    
    if args.variable:
        if args.variable not in acq.symbols:
            print(f"Error: Variable '{args.variable}' not found")
            print("Available symbols (first 20):")
            for name in list(acq.symbols.keys())[:20]:
                print(f"  {name}: 0x{acq.symbols[name]:08X}")
            return
        
        print(f"Sampling variable: {args.variable}")
        print(f"Address: 0x{acq.symbols[args.variable]:08X}")
        print(f"Sample count: {args.count}")
        print(f"Interval: {interval_ms}ms")
        
        data = acq.sample_variable(args.variable, args.count, interval_ms)
        
        metadata = {
            'device': args.device,
            'variable': args.variable,
            'address': hex(acq.symbols[args.variable]),
            'sample_count': args.count,
            'interval_ms': interval_ms,
            'timestamp': datetime.now().isoformat()
        }
        
        if args.format == 'csv':
            save_to_csv(data, output_file, 'simple')
        else:
            save_to_json(data, output_file, metadata)
        
        print(f"Data saved to: {output_file}")
        print(f"Total samples: {len(data)}")
        
    elif args.address:
        addr = int(args.address, 16)
        print(f"Sampling memory region: 0x{addr:08X}")
        print(f"Size: {args.size} bytes")
        print(f"Sample count: {args.count}")
        
        data = acq.sample_memory_region(addr, args.size, args.count, interval_ms)
        
        metadata = {
            'device': args.device,
            'address': hex(addr),
            'size': args.size,
            'sample_count': args.count,
            'interval_ms': interval_ms,
            'timestamp': datetime.now().isoformat()
        }
        
        if args.format == 'csv':
            save_to_csv(data, output_file, 'memory')
        else:
            save_to_json(data, output_file, metadata)
        
        print(f"Data saved to: {output_file}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
