#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 Variable Monitor
"""

import os
import re
import sys
import json
import time
import socket
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from threading import Thread, Event
from queue import Queue, Empty


@dataclass
class VariableInfo:
    name: str
    address: int
    size: int
    var_type: str
    current_value: Any = None
    previous_value: Any = None
    history: List[Tuple[float, Any]] = field(default_factory=list)
    watch_count: int = 0


class RTTMonitor:
    JLINK_PATH = r"D:\STM32CubeCLT\Segger\JLink_V864a\JLink.exe"
    
    def __init__(self, device: str, interface: str = "SWD", speed: int = 4000):
        self.device = device
        self.interface = interface
        self.speed = speed
        self.process: Optional[subprocess.Popen] = None
        self.running = False
        self.output_queue: Queue = Queue()
        self.stop_event = Event()
    
    def start_rtt(self) -> bool:
        if not Path(self.JLINK_PATH).exists():
            print(f"Error: J-Link not found at {self.JLINK_PATH}")
            return False
        
        commands = f"""
device {self.device}
si {self.interface}
speed {self.speed}
connect
rtt
rtt start
"""
        cmd_file = Path("rtt_commands.jlink")
        with open(cmd_file, "w") as f:
            f.write(commands)
        
        try:
            self.process = subprocess.Popen(
                [self.JLINK_PATH, "-CommandFile", str(cmd_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.running = True
            Thread(target=self._read_output, daemon=True).start()
            return True
        except Exception as e:
            print(f"Failed to start RTT: {e}")
            return False
    
    def _read_output(self):
        while self.running and self.process:
            try:
                line = self.process.stdout.readline()
                if line:
                    self.output_queue.put(line.strip())
            except:
                break
    
    def get_output(self, timeout: float = 0.1) -> Optional[str]:
        try:
            return self.output_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def stop(self):
        self.running = False
        self.stop_event.set()
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
        cmd_file = Path("rtt_commands.jlink")
        if cmd_file.exists():
            cmd_file.unlink()


class GDBMonitor:
    GDB_PATH = "arm-none-eabi-gdb"
    
    def __init__(self, elf_file: str, host: str = "localhost", port: int = 2331):
        self.elf_file = elf_file
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.variables: Dict[str, VariableInfo] = {}
        self.watchpoints: Dict[int, str] = {}
    
    def connect(self) -> bool:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self._read_response()
            self._send_command(f"file {self.elf_file}")
            self.connected = True
            return True
        except Exception as e:
            print(f"Failed to connect to GDB server: {e}")
            return False
    
    def _send_command(self, command: str) -> Optional[str]:
        if not self.socket:
            return None
        try:
            self.socket.sendall((command + "\n").encode())
            return self._read_response()
        except Exception as e:
            print(f"Command failed: {e}")
            return None
    
    def _read_response(self, timeout: float = 2.0) -> str:
        if not self.socket:
            return ""
        self.socket.settimeout(timeout)
        response = b""
        try:
            while True:
                chunk = self.socket.recv(4096)
                if not chunk:
                    break
                response += chunk
                if b"(gdb)" in response:
                    break
        except socket.timeout:
            pass
        return response.decode(errors="ignore")
    
    def add_watchpoint(self, var_name: str, watch_type: str = "write") -> bool:
        watch_cmds = {
            "write": f"watch {var_name}",
            "read": f"rwatch {var_name}",
            "access": f"awatch {var_name}"
        }
        cmd = watch_cmds.get(watch_type, f"watch {var_name}")
        response = self._send_command(cmd)
        if response and "Watchpoint" in response:
            match = re.search(r"Watchpoint (\d+):", response)
            if match:
                wp_num = int(match.group(1))
                self.watchpoints[wp_num] = var_name
                return True
        return False
    
    def remove_watchpoint(self, wp_num: int) -> bool:
        response = self._send_command(f"delete {wp_num}")
        if wp_num in self.watchpoints:
            del self.watchpoints[wp_num]
        return "deleted" in response.lower() or not response
    
    def get_variable_value(self, var_name: str, fmt: str = "natural") -> Optional[str]:
        fmt_map = {
            "natural": "",
            "hex": "/x",
            "decimal": "/d",
            "binary": "/t",
            "octal": "/o"
        }
        cmd = f"print {fmt_map.get(fmt, '')} {var_name}"
        response = self._send_command(cmd)
        if response:
            match = re.search(r"=\s*(.+?)(?:\n|$)", response)
            if match:
                return match.group(1).strip()
        return None
    
    def get_variable_address(self, var_name: str) -> Optional[int]:
        response = self._send_command(f"print &{var_name}")
        if response:
            match = re.search(r"0x([0-9a-fA-F]+)", response)
            if match:
                return int(match.group(1), 16)
        return None
    
    def set_variable_value(self, var_name: str, value: Any) -> bool:
        response = self._send_command(f"set {var_name} = {value}")
        return "error" not in response.lower() if response else False
    
    def read_memory(self, address: int, count: int = 1, size: str = "w") -> List[int]:
        cmd = f"x/{count}{size} 0x{address:08X}"
        response = self._send_command(cmd)
        values = []
        if response:
            for match in re.finditer(r"0x([0-9a-fA-F]+)", response):
                values.append(int(match.group(1), 16))
        return values
    
    def write_memory(self, address: int, value: int, size: str = "w") -> bool:
        type_map = {"b": "char", "h": "short", "w": "int", "g": "long long"}
        cmd = f"set {{{type_map[size]}}}0x{address:08X} = {value}"
        response = self._send_command(cmd)
        return "error" not in response.lower() if response else False
    
    def halt(self) -> bool:
        self._send_command("monitor halt")
        return True
    
    def resume(self) -> bool:
        self._send_command("continue")
        return True
    
    def step(self) -> bool:
        self._send_command("stepi")
        return True
    
    def get_registers(self) -> Dict[str, int]:
        response = self._send_command("info registers")
        registers = {}
        if response:
            for match in re.finditer(r"(\w+)\s+0x([0-9a-fA-F]+)", response):
                registers[match.group(1)] = int(match.group(2), 16)
        return registers
    
    def disconnect(self):
        if self.socket:
            self._send_command("detach")
            self.socket.close()
            self.connected = False


class VariableMonitor:
    def __init__(self, config_file: Optional[str] = None):
        self.variables: Dict[str, VariableInfo] = {}
        self.gdb: Optional[GDBMonitor] = None
        self.rtt: Optional[RTTMonitor] = None
        self.history_file = Path("var_history.json")
        self.max_history = 1000
        self.poll_interval = 0.1
        
        if config_file:
            self.load_config(config_file)
    
    def load_config(self, config_file: str):
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
            
            for var in config.get("variables", []):
                self.add_variable(
                    name=var["name"],
                    address=var.get("address", 0),
                    size=var.get("size", 4),
                    var_type=var.get("type", "int")
                )
        except Exception as e:
            print(f"Failed to load config: {e}")
    
    def add_variable(self, name: str, address: int = 0, size: int = 4, var_type: str = "int"):
        self.variables[name] = VariableInfo(
            name=name,
            address=address,
            size=size,
            var_type=var_type
        )
    
    def remove_variable(self, name: str):
        if name in self.variables:
            del self.variables[name]
    
    def connect_gdb(self, elf_file: str, host: str = "localhost", port: int = 2331) -> bool:
        self.gdb = GDBMonitor(elf_file, host, port)
        if self.gdb.connect():
            for name, var in self.variables.items():
                if var.address == 0:
                    addr = self.gdb.get_variable_address(name)
                    if addr:
                        var.address = addr
            return True
        return False
    
    def start_rtt(self, device: str) -> bool:
        self.rtt = RTTMonitor(device)
        return self.rtt.start_rtt()
    
    def update_values(self):
        if not self.gdb:
            return
        
        for name, var in self.variables.items():
            value = self.gdb.get_variable_value(name, fmt="hex")
            if value:
                var.previous_value = var.current_value
                var.current_value = value
                var.watch_count += 1
                var.history.append((time.time(), value))
                if len(var.history) > self.max_history:
                    var.history.pop(0)
    
    def monitor_loop(self, callback: Optional[callable] = None):
        while True:
            self.update_values()
            if callback:
                callback(self.variables)
            time.sleep(self.poll_interval)
    
    def get_changed_variables(self) -> List[str]:
        changed = []
        for name, var in self.variables.items():
            if var.current_value != var.previous_value:
                changed.append(name)
        return changed
    
    def export_history(self, output_file: str):
        data = {}
        for name, var in self.variables.items():
            data[name] = {
                "address": hex(var.address),
                "type": var.var_type,
                "history": [(t, str(v)) for t, v in var.history]
            }
        
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def generate_report(self) -> str:
        lines = ["=" * 60, "Variable Monitor Report", "=" * 60, ""]
        
        for name, var in self.variables.items():
            lines.append(f"Variable: {name}")
            lines.append(f"  Address: 0x{var.address:08X}")
            lines.append(f"  Type: {var.var_type}")
            lines.append(f"  Current Value: {var.current_value}")
            lines.append(f"  Previous Value: {var.previous_value}")
            lines.append(f"  Watch Count: {var.watch_count}")
            lines.append(f"  History Length: {len(var.history)}")
            lines.append("")
        
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="STM32 Variable Monitor - Real-time variable monitoring tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python var_monitor.py --elf build/firmware.elf --connect
  python var_monitor.py --elf build/firmware.elf --watch counter --watch state
  python var_monitor.py --config monitor_config.json --report
  python var_monitor.py --rtt --device STM32H743VI
        """
    )
    
    parser.add_argument("--elf", "-e", help="ELF file path")
    parser.add_argument("--host", default="localhost", help="GDB server host")
    parser.add_argument("--port", "-p", type=int, default=2331, help="GDB server port")
    parser.add_argument("--connect", "-c", action="store_true", help="Connect to GDB server")
    parser.add_argument("--watch", "-w", action="append", help="Variable to watch")
    parser.add_argument("--watchpoint", "-W", action="append", help="Add watchpoint (format: var:type)")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--rtt", action="store_true", help="Use RTT monitoring")
    parser.add_argument("--device", "-d", help="Target device name")
    parser.add_argument("--report", "-r", action="store_true", help="Generate report")
    parser.add_argument("--export", "-x", help="Export history to file")
    parser.add_argument("--interval", "-i", type=float, default=0.1, help="Poll interval (seconds)")
    parser.add_argument("--count", "-n", type=int, default=10, help="Number of samples")
    
    args = parser.parse_args()
    
    monitor = VariableMonitor(args.config)
    monitor.poll_interval = args.interval
    
    if args.watch:
        for var_name in args.watch:
            monitor.add_variable(var_name)
    
    if args.connect and args.elf:
        print(f"Connecting to GDB server at {args.host}:{args.port}...")
        if monitor.connect_gdb(args.elf, args.host, args.port):
            print("Connected successfully!")
            
            if args.watchpoint:
                for wp_spec in args.watchpoint:
                    parts = wp_spec.split(":")
                    var_name = parts[0]
                    wp_type = parts[1] if len(parts) > 1 else "write"
                    if monitor.gdb.add_watchpoint(var_name, wp_type):
                        print(f"Added {wp_type} watchpoint on {var_name}")
            
            print(f"\nMonitoring {len(monitor.variables)} variables for {args.count} samples...")
            for i in range(args.count):
                monitor.update_values()
                changed = monitor.get_changed_variables()
                if changed:
                    print(f"[{i+1}/{args.count}] Changed: {', '.join(changed)}")
                    for name in changed:
                        var = monitor.variables[name]
                        print(f"  {name}: {var.previous_value} -> {var.current_value}")
                else:
                    print(f"[{i+1}/{args.count}] No changes")
                time.sleep(args.interval)
            
            if args.report:
                print("\n" + monitor.generate_report())
            
            if args.export:
                monitor.export_history(args.export)
                print(f"History exported to {args.export}")
            
            monitor.gdb.disconnect()
        else:
            print("Failed to connect to GDB server")
            return 1
    
    elif args.rtt and args.device:
        print(f"Starting RTT monitor for {args.device}...")
        if monitor.start_rtt(args.device):
            print("RTT started. Press Ctrl+C to stop...")
            try:
                while True:
                    output = monitor.rtt.get_output()
                    if output:
                        print(output)
                    time.sleep(0.01)
            except KeyboardInterrupt:
                print("\nStopping RTT...")
                monitor.rtt.stop()
        else:
            print("Failed to start RTT")
            return 1
    
    else:
        parser.print_help()
    
    return 0


if __name__ == "__main__":
    exit(main())
