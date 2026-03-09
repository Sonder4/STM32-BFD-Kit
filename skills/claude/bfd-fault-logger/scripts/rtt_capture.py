#!/usr/bin/env python3
"""
RTT Capture Module
Captures Real-Time Transfer (RTT) logs from STM32 devices via J-Link.
"""

import os
import re
import time
import threading
import queue
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import subprocess
import json


class LogLevel(Enum):
    ERROR = 0
    WARN = 1
    INFO = 2
    DEBUG = 3
    TRACE = 4


@dataclass
class RTTLogEntry:
    timestamp: str
    level: str
    buffer_index: int
    message: str
    raw_data: str = ""
    parsed_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RTTBufferConfig:
    name: str
    size: int
    mode: str = "block"


class RTTCapture:
    DEFAULT_RTT_BUFFERS = [
        RTTBufferConfig("error", 1024),
        RTTBufferConfig("warn", 2048),
        RTTBufferConfig("info", 4096),
        RTTBufferConfig("debug", 2048),
    ]
    
    LOG_PATTERNS = {
        "error": re.compile(r'\[ERROR\]|\[ERR\]|ERROR:|ERR:', re.IGNORECASE),
        "warn": re.compile(r'\[WARN\]|\[WARNING\]|WARN:|WARNING:', re.IGNORECASE),
        "info": re.compile(r'\[INFO\]|INFO:', re.IGNORECASE),
        "debug": re.compile(r'\[DEBUG\]|DEBUG:', re.IGNORECASE),
    }
    
    def __init__(
        self,
        device: str = "STM32H7",
        interface: str = "SWD",
        speed: int = 4000,
        jlink_path: str = "JLink.exe"
    ):
        self.device = device
        self.interface = interface
        self.speed = speed
        self.jlink_path = jlink_path
        
        self._connected = False
        self._capturing = False
        self._capture_thread: Optional[threading.Thread] = None
        self._log_queue: queue.Queue = queue.Queue()
        self._log_entries: List[RTTLogEntry] = []
        self._lock = threading.Lock()
        self._callbacks: Dict[str, List[Callable]] = {
            "error": [],
            "warn": [],
            "info": [],
            "debug": [],
            "all": []
        }
        
        self._buffer_configs = list(self.DEFAULT_RTT_BUFFERS)
    
    def configure_buffers(self, configs: List[RTTBufferConfig]):
        self._buffer_configs = configs
    
    def register_callback(self, level: str, callback: Callable[[RTTLogEntry], None]):
        if level in self._callbacks:
            self._callbacks[level].append(callback)
    
    def unregister_callback(self, level: str, callback: Callable):
        if level in self._callbacks and callback in self._callbacks[level]:
            self._callbacks[level].remove(callback)
    
    def _invoke_callbacks(self, entry: RTTLogEntry):
        level = entry.level.lower()
        
        for callback in self._callbacks.get(level, []):
            try:
                callback(entry)
            except Exception as e:
                print(f"Callback error: {e}")
        
        for callback in self._callbacks.get("all", []):
            try:
                callback(entry)
            except Exception as e:
                print(f"Callback error: {e}")
    
    def connect(self) -> bool:
        try:
            command_file = self._create_connect_command()
            result = subprocess.run(
                [self.jlink_path, "-CommandFile", command_file],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            os.remove(command_file)
            
            if "Connected successfully" in result.stdout or "Found" in result.stdout:
                self._connected = True
                return True
            
            return False
            
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    def _create_connect_command(self) -> str:
        commands = [
            f"device {self.device}",
            f"si {self.interface}",
            f"speed {self.speed}",
            "connect",
            "r",
            "g",
            "exit"
        ]
        
        fd, path = tempfile.mkstemp(suffix='.jlink')
        with os.fdopen(fd, 'w') as f:
            f.write('\n'.join(commands))
        
        return path
    
    def disconnect(self):
        self._connected = False
        self.stop_capture()
    
    def start_capture(self, continuous: bool = True) -> bool:
        if not self._connected:
            if not self.connect():
                return False
        
        self._capturing = True
        
        if continuous:
            self._capture_thread = threading.Thread(
                target=self._continuous_capture,
                daemon=True
            )
            self._capture_thread.start()
        
        return True
    
    def stop_capture(self):
        self._capturing = False
        
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=5)
    
    def _continuous_capture(self):
        while self._capturing:
            try:
                entries = self._read_rtt_buffers()
                
                for entry in entries:
                    with self._lock:
                        self._log_entries.append(entry)
                    self._log_queue.put(entry)
                    self._invoke_callbacks(entry)
                
                time.sleep(0.01)
                
            except Exception as e:
                print(f"Capture error: {e}")
                time.sleep(0.1)
    
    def _read_rtt_buffers(self) -> List[RTTLogEntry]:
        entries = []
        
        command_file = self._create_rtt_command()
        
        try:
            result = subprocess.run(
                [self.jlink_path, "-CommandFile", command_file],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            entries = self._parse_rtt_output(result.stdout)
            
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            print(f"RTT read error: {e}")
        finally:
            if os.path.exists(command_file):
                os.remove(command_file)
        
        return entries
    
    def _create_rtt_command(self) -> str:
        commands = [
            f"device {self.device}",
            f"si {self.interface}",
            f"speed {self.speed}",
            "connect",
            "r",
            "g",
            "rtt",
            "rtt start",
        ]
        
        for i, config in enumerate(self._buffer_configs):
            commands.append(f"rtt setchan {i} {config.name}")
        
        commands.extend([
            "rtt read 0 100",
            "rtt read 1 100",
            "rtt read 2 100",
            "rtt stop",
            "exit"
        ])
        
        fd, path = tempfile.mkstemp(suffix='.jlink')
        with os.fdopen(fd, 'w') as f:
            f.write('\n'.join(commands))
        
        return path
    
    def _parse_rtt_output(self, output: str) -> List[RTTLogEntry]:
        entries = []
        timestamp = datetime.now().isoformat()
        
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            level = self._detect_log_level(line)
            
            entry = RTTLogEntry(
                timestamp=timestamp,
                level=level,
                buffer_index=self._get_buffer_index(level),
                message=line,
                raw_data=line,
                parsed_data=self._parse_log_content(line)
            )
            
            entries.append(entry)
        
        return entries
    
    def _detect_log_level(self, message: str) -> str:
        for level, pattern in self.LOG_PATTERNS.items():
            if pattern.search(message):
                return level
        return "info"
    
    def _get_buffer_index(self, level: str) -> int:
        level_map = {"error": 0, "warn": 1, "info": 2, "debug": 3}
        return level_map.get(level, 2)
    
    def _parse_log_content(self, message: str) -> Dict[str, Any]:
        parsed = {}
        
        timestamp_match = re.search(r'\[(\d{2}:\d{2}:\d{2}\.\d{3})\]', message)
        if timestamp_match:
            parsed["log_timestamp"] = timestamp_match.group(1)
        
        level_match = re.search(r'\[(ERROR|WARN|INFO|DEBUG)\]', message, re.IGNORECASE)
        if level_match:
            parsed["log_level"] = level_match.group(1).upper()
        
        module_match = re.search(r'\[([A-Za-z_]+)\]', message)
        if module_match:
            module = module_match.group(1)
            if module not in ["ERROR", "WARN", "INFO", "DEBUG"]:
                parsed["module"] = module
        
        hex_match = re.findall(r'0x[0-9A-Fa-f]+', message)
        if hex_match:
            parsed["hex_values"] = hex_match
        
        return parsed
    
    def read_logs(
        self,
        level: Optional[str] = None,
        count: int = 100
    ) -> List[RTTLogEntry]:
        with self._lock:
            entries = list(self._log_entries)
        
        if level:
            entries = [e for e in entries if e.level.lower() == level.lower()]
        
        return entries[-count:]
    
    def read_new_logs(self, timeout: float = 1.0) -> List[RTTLogEntry]:
        entries = []
        
        try:
            while True:
                entry = self._log_queue.get(timeout=timeout)
                entries.append(entry)
        except queue.Empty:
            pass
        
        return entries
    
    def get_log_stats(self) -> Dict[str, int]:
        stats = {
            "total": 0,
            "error": 0,
            "warn": 0,
            "info": 0,
            "debug": 0
        }
        
        with self._lock:
            for entry in self._log_entries:
                stats["total"] += 1
                level = entry.level.lower()
                if level in stats:
                    stats[level] += 1
        
        return stats
    
    def clear_logs(self):
        with self._lock:
            self._log_entries.clear()
        
        while not self._log_queue.empty():
            try:
                self._log_queue.get_nowait()
            except queue.Empty:
                break
    
    def export_logs(
        self,
        filepath: str,
        format: str = "json",
        level: Optional[str] = None
    ) -> bool:
        entries = self.read_logs(level=level)
        
        try:
            if format.lower() == "json":
                data = {
                    "export_time": datetime.now().isoformat(),
                    "total_logs": len(entries),
                    "logs": [
                        {
                            "timestamp": e.timestamp,
                            "level": e.level,
                            "message": e.message,
                            "parsed": e.parsed_data
                        }
                        for e in entries
                    ]
                }
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            
            elif format.lower() == "txt":
                with open(filepath, 'w', encoding='utf-8') as f:
                    for e in entries:
                        f.write(f"[{e.timestamp}] [{e.level.upper()}] {e.message}\n")
            
            return True
            
        except Exception as e:
            print(f"Export failed: {e}")
            return False
    
    def search_logs(
        self,
        pattern: str,
        level: Optional[str] = None,
        case_sensitive: bool = False
    ) -> List[RTTLogEntry]:
        entries = self.read_logs(level=level)
        
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
        
        return [e for e in entries if regex.search(e.message)]
    
    def filter_by_time(
        self,
        start_time: str,
        end_time: str
    ) -> List[RTTLogEntry]:
        entries = self.read_logs()
        
        filtered = []
        for entry in entries:
            if start_time <= entry.timestamp <= end_time:
                filtered.append(entry)
        
        return filtered
    
    def is_connected(self) -> bool:
        return self._connected
    
    def is_capturing(self) -> bool:
        return self._capturing


import tempfile


class RTTLogSimulator:
    def __init__(self):
        self._entries: List[RTTLogEntry] = []
        self._lock = threading.Lock()
    
    def add_log(self, level: str, message: str, module: str = ""):
        timestamp = datetime.now().isoformat()
        
        if module:
            full_message = f"[{module}] [{level.upper()}] {message}"
        else:
            full_message = f"[{level.upper()}] {message}"
        
        entry = RTTLogEntry(
            timestamp=timestamp,
            level=level.lower(),
            buffer_index=0,
            message=full_message,
            parsed_data={"module": module} if module else {}
        )
        
        with self._lock:
            self._entries.append(entry)
    
    def simulate_error(self, error_type: str, details: str = ""):
        messages = {
            "hardfault": f"HARDFAULT: {details or 'Invalid memory access at 0x08004567'}",
            "busfault": f"BUSFAULT: {details or 'Bus error on SPI transfer'}",
            "dma": f"DMA ERROR: {details or 'Transfer error on channel 3'}",
            "stack": f"STACK OVERFLOW: {details or 'Stack pointer at 0x2001FFF0'}",
        }
        
        message = messages.get(error_type.lower(), f"ERROR: {details}")
        self.add_log("error", message, "SYSTEM")
    
    def get_entries(self) -> List[RTTLogEntry]:
        with self._lock:
            return list(self._entries)


if __name__ == "__main__":
    simulator = RTTLogSimulator()
    
    simulator.add_log("info", "System initialized", "MAIN")
    simulator.add_log("debug", "Configuring peripherals", "INIT")
    simulator.simulate_error("hardfault", "PC: 0x08004567, LR: 0x08002345")
    simulator.add_log("warn", "Buffer nearly full", "UART")
    
    for entry in simulator.get_entries():
        print(f"[{entry.level.upper()}] {entry.message}")
