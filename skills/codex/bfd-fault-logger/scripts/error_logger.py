#!/usr/bin/env python3
"""
Hardware Error Logger Module
Records and manages hardware fault information from STM32 devices.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import threading
import queue


class FaultType(Enum):
    HARD_FAULT = "HardFault"
    BUS_FAULT = "BusFault"
    USAGE_FAULT = "UsageFault"
    MEM_MANAGE_FAULT = "MemManageFault"
    DMA_ERROR = "DMAError"
    PERIPHERAL_ERROR = "PeripheralError"
    WATCHDOG_TIMEOUT = "WatchdogTimeout"
    STACK_OVERFLOW = "StackOverflow"
    UNKNOWN = "Unknown"


class Severity(Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


@dataclass
class RegisterState:
    R0: str = "0x00000000"
    R1: str = "0x00000000"
    R2: str = "0x00000000"
    R3: str = "0x00000000"
    R4: str = "0x00000000"
    R5: str = "0x00000000"
    R6: str = "0x00000000"
    R7: str = "0x00000000"
    R8: str = "0x00000000"
    R9: str = "0x00000000"
    R10: str = "0x00000000"
    R11: str = "0x00000000"
    R12: str = "0x00000000"
    SP: str = "0x00000000"
    LR: str = "0x00000000"
    PC: str = "0x00000000"
    xPSR: str = "0x00000000"
    MSP: str = "0x00000000"
    PSP: str = "0x00000000"


@dataclass
class FaultStatusRegisters:
    CFSR: str = "0x00000000"
    HFSR: str = "0x00000000"
    DFSR: str = "0x00000000"
    AFSR: str = "0x00000000"
    MMFAR: str = "0x00000000"
    BFAR: str = "0x00000000"


@dataclass
class ErrorRecord:
    id: str
    timestamp: str
    fault_type: str
    severity: str
    description: str
    registers: Dict[str, str]
    fault_status: Dict[str, str]
    stack_trace: List[str]
    source: str
    context: Dict[str, Any] = field(default_factory=dict)
    raw_data: Optional[str] = None


class HardwareErrorLogger:
    def __init__(self, storage_path: str = "logs/hw_error"):
        self.storage_path = storage_path
        self.error_queue: queue.Queue = queue.Queue()
        self.error_records: List[ErrorRecord] = []
        self._lock = threading.Lock()
        self._counter = 0
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self):
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)
    
    def _generate_error_id(self) -> str:
        self._counter += 1
        date_str = datetime.now().strftime("%Y%m%d")
        return f"ERR_{date_str}_{self._counter:04d}"
    
    def _determine_severity(self, fault_type: FaultType) -> Severity:
        severity_map = {
            FaultType.HARD_FAULT: Severity.CRITICAL,
            FaultType.MEM_MANAGE_FAULT: Severity.CRITICAL,
            FaultType.BUS_FAULT: Severity.HIGH,
            FaultType.USAGE_FAULT: Severity.HIGH,
            FaultType.DMA_ERROR: Severity.HIGH,
            FaultType.PERIPHERAL_ERROR: Severity.MEDIUM,
            FaultType.WATCHDOG_TIMEOUT: Severity.CRITICAL,
            FaultType.STACK_OVERFLOW: Severity.CRITICAL,
            FaultType.UNKNOWN: Severity.LOW,
        }
        return severity_map.get(fault_type, Severity.LOW)
    
    def _determine_source(self, fault_type: FaultType) -> str:
        source_map = {
            FaultType.HARD_FAULT: "CPU",
            FaultType.MEM_MANAGE_FAULT: "Memory",
            FaultType.BUS_FAULT: "Bus",
            FaultType.USAGE_FAULT: "CPU",
            FaultType.DMA_ERROR: "DMA",
            FaultType.PERIPHERAL_ERROR: "Peripheral",
            FaultType.WATCHDOG_TIMEOUT: "System",
            FaultType.STACK_OVERFLOW: "Memory",
            FaultType.UNKNOWN: "Unknown",
        }
        return source_map.get(fault_type, "Unknown")
    
    def record_fault(
        self,
        fault_type: str,
        registers: Dict[str, str],
        fault_status: Optional[Dict[str, str]] = None,
        stack_trace: Optional[List[str]] = None,
        description: str = "",
        context: Optional[Dict[str, Any]] = None,
        raw_data: Optional[str] = None
    ) -> ErrorRecord:
        try:
            ftype = FaultType(fault_type)
        except ValueError:
            ftype = FaultType.UNKNOWN
        
        severity = self._determine_severity(ftype)
        source = self._determine_source(ftype)
        
        record = ErrorRecord(
            id=self._generate_error_id(),
            timestamp=datetime.now().isoformat(),
            fault_type=ftype.value,
            severity=severity.value,
            description=description or f"{ftype.value} detected",
            registers=registers,
            fault_status=fault_status or {},
            stack_trace=stack_trace or [],
            source=source,
            context=context or {},
            raw_data=raw_data
        )
        
        with self._lock:
            self.error_records.append(record)
            self._save_record(record)
        
        return record
    
    def record_hard_fault(
        self,
        registers: Dict[str, str],
        cfsr: str = "0x00000000",
        hfsr: str = "0x00000000",
        stack_trace: Optional[List[str]] = None
    ) -> ErrorRecord:
        fault_status = {
            "CFSR": cfsr,
            "HFSR": hfsr,
        }
        
        description = self._analyze_hard_fault(cfsr, hfsr)
        
        return self.record_fault(
            fault_type="HardFault",
            registers=registers,
            fault_status=fault_status,
            stack_trace=stack_trace,
            description=description
        )
    
    def record_bus_fault(
        self,
        registers: Dict[str, str],
        bfsr: str = "0x00000000",
        bfar: str = "0x00000000",
        stack_trace: Optional[List[str]] = None
    ) -> ErrorRecord:
        fault_status = {
            "BFSR": bfsr,
            "BFAR": bfar,
        }
        
        description = self._analyze_bus_fault(bfsr, bfar)
        
        return self.record_fault(
            fault_type="BusFault",
            registers=registers,
            fault_status=fault_status,
            stack_trace=stack_trace,
            description=description
        )
    
    def _analyze_hard_fault(self, cfsr: str, hfsr: str) -> str:
        try:
            cfsr_val = int(cfsr, 16)
            hfsr_val = int(hfsr, 16)
        except ValueError:
            return "HardFault - Unable to parse status registers"
        
        reasons = []
        
        if hfsr_val & (1 << 30):
            reasons.append("FORCED: Escalated from configurable fault")
        if hfsr_val & (1 << 1):
            reasons.append("VECTTBL: Vector table read fault")
        
        if cfsr_val & (1 << 0):
            reasons.append("IACCVIOL: Instruction access violation")
        if cfsr_val & (1 << 1):
            reasons.append("DACCVIOL: Data access violation")
        if cfsr_val & (1 << 3):
            reasons.append("MUNSTKERR: MemManage unstacking fault")
        if cfsr_val & (1 << 4):
            reasons.append("MSTKERR: MemManage stacking fault")
        if cfsr_val & (1 << 5):
            reasons.append("MLSPERR: MemManage FP lazy state fault")
        
        if cfsr_val & (1 << 8):
            reasons.append("IBUSERR: Instruction bus error")
        if cfsr_val & (1 << 9):
            reasons.append("PRECISERR: Precise data bus error")
        if cfsr_val & (1 << 10):
            reasons.append("IMPRECISERR: Imprecise data bus error")
        if cfsr_val & (1 << 11):
            reasons.append("UNSTKERR: BusFault unstacking fault")
        if cfsr_val & (1 << 12):
            reasons.append("STKERR: BusFault stacking fault")
        if cfsr_val & (1 << 13):
            reasons.append("LSPERR: BusFault FP lazy state fault")
        
        if cfsr_val & (1 << 16):
            reasons.append("UNDEFINSTR: Undefined instruction")
        if cfsr_val & (1 << 17):
            reasons.append("INVSTATE: Invalid state (Thumb bit)")
        if cfsr_val & (1 << 18):
            reasons.append("INVPC: Invalid PC load")
        if cfsr_val & (1 << 19):
            reasons.append("NOCP: No coprocessor")
        if cfsr_val & (1 << 24):
            reasons.append("UNALIGNED: Unaligned access")
        if cfsr_val & (1 << 25):
            reasons.append("DIVBYZERO: Divide by zero")
        
        if reasons:
            return f"HardFault - {', '.join(reasons)}"
        return "HardFault - Unknown cause"
    
    def _analyze_bus_fault(self, bfsr: str, bfar: str) -> str:
        try:
            bfsr_val = int(bfsr, 16)
        except ValueError:
            return "BusFault - Unable to parse status register"
        
        reasons = []
        
        if bfsr_val & (1 << 0):
            reasons.append("IBUSERR: Instruction bus error")
        if bfsr_val & (1 << 1):
            reasons.append("PRECISERR: Precise data bus error")
        if bfsr_val & (1 << 2):
            reasons.append("IMPRECISERR: Imprecise data bus error")
        if bfsr_val & (1 << 3):
            reasons.append("UNSTKERR: Unstacking fault")
        if bfsr_val & (1 << 4):
            reasons.append("STKERR: Stacking fault")
        if bfsr_val & (1 << 5):
            reasons.append("LSPERR: FP lazy state fault")
        if bfsr_val & (1 << 7):
            reasons.append(f"BFARVALID: Fault address valid ({bfar})")
        
        if reasons:
            return f"BusFault - {', '.join(reasons)}"
        return "BusFault - Unknown cause"
    
    def _save_record(self, record: ErrorRecord):
        filename = f"{record.id}.json"
        filepath = os.path.join(self.storage_path, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(record), f, indent=2, ensure_ascii=False)
    
    def load_records(self) -> List[ErrorRecord]:
        records = []
        for filename in os.listdir(self.storage_path):
            if filename.endswith('.json'):
                filepath = os.path.join(self.storage_path, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    records.append(ErrorRecord(**data))
        
        records.sort(key=lambda x: x.timestamp)
        with self._lock:
            self.error_records = records
        return records
    
    def get_all_records(self) -> List[ErrorRecord]:
        with self._lock:
            return list(self.error_records)
    
    def clear_records(self):
        with self._lock:
            self.error_records = []
            for filename in os.listdir(self.storage_path):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.storage_path, filename)
                    os.remove(filepath)


if __name__ == "__main__":
    logger = HardwareErrorLogger()
    
    test_registers = {
        "R0": "0x20001234",
        "R1": "0x00000001",
        "PC": "0x08004567",
        "LR": "0x08002345",
        "SP": "0x2001FFF0"
    }
    
    record = logger.record_hard_fault(
        registers=test_registers,
        cfsr="0x00000200",
        hfsr="0x40000000",
        stack_trace=["0x08004567", "0x08002345", "0x08001234"]
    )
    
    print(f"Recorded error: {record.id}")
    print(f"Description: {record.description}")
