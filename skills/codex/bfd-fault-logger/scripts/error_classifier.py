#!/usr/bin/env python3
"""
Error Classifier Module
Classifies hardware errors by severity, source, and timing context.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import re


class Severity(Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


class ErrorSource(Enum):
    CPU = "CPU"
    MEMORY = "Memory"
    BUS = "Bus"
    DMA = "DMA"
    PERIPHERAL = "Peripheral"
    CLOCK = "Clock"
    POWER = "Power"
    SYSTEM = "System"
    UNKNOWN = "Unknown"


class TimingContext(Enum):
    STARTUP = "Startup"
    RUNTIME = "Runtime"
    INTERRUPT = "Interrupt"
    LOW_POWER = "LowPower"
    SHUTDOWN = "Shutdown"
    UNKNOWN = "Unknown"


@dataclass
class ErrorClassification:
    severity: Severity
    source: ErrorSource
    timing: TimingContext
    category: str
    subcategory: Optional[str] = None
    confidence: float = 1.0
    related_errors: List[str] = None
    
    def __post_init__(self):
        if self.related_errors is None:
            self.related_errors = []


class ErrorClassifier:
    FAULT_SEVERITY_MAP = {
        "HardFault": Severity.CRITICAL,
        "MemManageFault": Severity.CRITICAL,
        "BusFault": Severity.HIGH,
        "UsageFault": Severity.HIGH,
        "DMAError": Severity.HIGH,
        "PeripheralError": Severity.MEDIUM,
        "WatchdogTimeout": Severity.CRITICAL,
        "StackOverflow": Severity.CRITICAL,
        "ClockError": Severity.HIGH,
        "PowerError": Severity.CRITICAL,
        "Unknown": Severity.LOW,
    }
    
    FAULT_SOURCE_MAP = {
        "HardFault": ErrorSource.CPU,
        "MemManageFault": ErrorSource.MEMORY,
        "BusFault": ErrorSource.BUS,
        "UsageFault": ErrorSource.CPU,
        "DMAError": ErrorSource.DMA,
        "PeripheralError": ErrorSource.PERIPHERAL,
        "WatchdogTimeout": ErrorSource.SYSTEM,
        "StackOverflow": ErrorSource.MEMORY,
        "ClockError": ErrorSource.CLOCK,
        "PowerError": ErrorSource.POWER,
        "Unknown": ErrorSource.UNKNOWN,
    }
    
    CFSR_PATTERNS = {
        "IACCVIOL": (0x01, "Instruction access violation"),
        "DACCVIOL": (0x02, "Data access violation"),
        "MUNSTKERR": (0x08, "MemManage unstacking fault"),
        "MSTKERR": (0x10, "MemManage stacking fault"),
        "IBUSERR": (0x100, "Instruction bus error"),
        "PRECISERR": (0x200, "Precise data bus error"),
        "IMPRECISERR": (0x400, "Imprecise data bus error"),
        "UNSTKERR": (0x800, "BusFault unstacking fault"),
        "STKERR": (0x1000, "BusFault stacking fault"),
        "UNDEFINSTR": (0x10000, "Undefined instruction"),
        "INVSTATE": (0x20000, "Invalid state"),
        "INVPC": (0x40000, "Invalid PC load"),
        "NOCP": (0x80000, "No coprocessor"),
        "UNALIGNED": (0x1000000, "Unaligned access"),
        "DIVBYZERO": (0x2000000, "Divide by zero"),
    }
    
    PERIPHERAL_ERROR_PATTERNS = {
        "UART": ["ORE", "FE", "NE", "PE"],
        "SPI": ["MODF", "OVR", "CRCERR"],
        "I2C": ["BERR", "ARLO", "OVR", "TIMEOUT"],
        "DMA": ["TEIF", "DMEIF"],
        "ADC": ["OVR", "AWD"],
        "TIM": ["CC", "UIF"],
    }
    
    def __init__(self):
        self._startup_time: Optional[datetime] = None
        self._interrupt_depth = 0
        self._low_power_mode = False
    
    def set_startup_time(self, startup_time: datetime):
        self._startup_time = startup_time
    
    def set_interrupt_context(self, depth: int):
        self._interrupt_depth = depth
    
    def set_low_power_mode(self, enabled: bool):
        self._low_power_mode = enabled
    
    def classify(
        self,
        fault_type: str,
        registers: Dict[str, str],
        fault_status: Dict[str, str],
        description: str = "",
        timestamp: Optional[str] = None
    ) -> ErrorClassification:
        severity = self._determine_severity(fault_type, fault_status)
        source = self._determine_source(fault_type, fault_status)
        timing = self._determine_timing(timestamp)
        subcategory = self._determine_subcategory(fault_type, fault_status, description)
        
        category = f"{source.value}_{severity.value}"
        
        return ErrorClassification(
            severity=severity,
            source=source,
            timing=timing,
            category=category,
            subcategory=subcategory
        )
    
    def _determine_severity(
        self,
        fault_type: str,
        fault_status: Dict[str, str]
    ) -> Severity:
        base_severity = self.FAULT_SEVERITY_MAP.get(fault_type, Severity.LOW)
        
        if fault_status:
            cfsr = fault_status.get("CFSR", "0x00000000")
            hfsr = fault_status.get("HFSR", "0x00000000")
            
            try:
                cfsr_val = int(cfsr, 16)
                hfsr_val = int(hfsr, 16)
                
                if hfsr_val & (1 << 30):
                    return Severity.CRITICAL
                
                critical_bits = [
                    0x01, 0x02, 0x10000, 0x20000
                ]
                for bit in critical_bits:
                    if cfsr_val & bit:
                        return Severity.CRITICAL
                        
            except ValueError:
                pass
        
        return base_severity
    
    def _determine_source(
        self,
        fault_type: str,
        fault_status: Dict[str, str]
    ) -> ErrorSource:
        base_source = self.FAULT_SOURCE_MAP.get(fault_type, ErrorSource.UNKNOWN)
        
        if fault_status:
            cfsr = fault_status.get("CFSR", "0x00000000")
            
            try:
                cfsr_val = int(cfsr, 16)
                
                if cfsr_val & 0x000000FF:
                    return ErrorSource.MEMORY
                if cfsr_val & 0x0000FF00:
                    return ErrorSource.BUS
                if cfsr_val & 0x00FF0000:
                    return ErrorSource.CPU
                    
            except ValueError:
                pass
        
        return base_source
    
    def _determine_timing(self, timestamp: Optional[str]) -> TimingContext:
        if self._interrupt_depth > 0:
            return TimingContext.INTERRUPT
        
        if self._low_power_mode:
            return TimingContext.LOW_POWER
        
        if timestamp and self._startup_time:
            try:
                ts = datetime.fromisoformat(timestamp)
                delta = (ts - self._startup_time).total_seconds()
                
                if delta < 5:
                    return TimingContext.STARTUP
                elif delta < 30:
                    return TimingContext.STARTUP
            except ValueError:
                pass
        
        return TimingContext.RUNTIME
    
    def _determine_subcategory(
        self,
        fault_type: str,
        fault_status: Dict[str, str],
        description: str
    ) -> Optional[str]:
        if fault_status:
            cfsr = fault_status.get("CFSR", "0x00000000")
            
            try:
                cfsr_val = int(cfsr, 16)
                
                for name, (bit, desc) in self.CFSR_PATTERNS.items():
                    if cfsr_val & bit:
                        return f"{name}: {desc}"
                        
            except ValueError:
                pass
        
        for periph, errors in self.PERIPHERAL_ERROR_PATTERNS.items():
            for error in errors:
                if error in description.upper():
                    return f"{periph}_{error}"
        
        return None
    
    def analyze_stack_trace(
        self,
        stack_trace: List[str],
        symbol_table: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, str]]:
        analyzed = []
        
        for addr in stack_trace:
            entry = {
                "address": addr,
                "symbol": None,
                "file": None,
                "line": None
            }
            
            if symbol_table:
                symbol = symbol_table.get(addr)
                if symbol:
                    entry["symbol"] = symbol
            
            analyzed.append(entry)
        
        return analyzed
    
    def estimate_error_impact(
        self,
        classification: ErrorClassification,
        error_count: int = 1
    ) -> Dict[str, any]:
        impact_score = 0
        
        severity_scores = {
            Severity.CRITICAL: 100,
            Severity.HIGH: 50,
            Severity.MEDIUM: 20,
            Severity.LOW: 5,
            Severity.INFO: 1,
        }
        
        impact_score += severity_scores.get(classification.severity, 0)
        impact_score *= min(error_count, 10)
        
        if classification.timing == TimingContext.INTERRUPT:
            impact_score *= 1.5
        elif classification.timing == TimingContext.STARTUP:
            impact_score *= 1.3
        
        return {
            "impact_score": impact_score,
            "severity_level": classification.severity.value,
            "requires_immediate_attention": impact_score >= 100,
            "recommended_action": self._get_recommended_action(classification)
        }
    
    def _get_recommended_action(self, classification: ErrorClassification) -> str:
        actions = {
            Severity.CRITICAL: "立即停止系统运行，检查错误现场，分析寄存器状态",
            Severity.HIGH: "尽快分析错误原因，检查相关外设配置",
            Severity.MEDIUM: "记录错误信息，在下次维护时处理",
            Severity.LOW: "观察是否重复出现，记录日志",
            Severity.INFO: "仅作记录，无需立即处理",
        }
        
        base_action = actions.get(classification.severity, "未知错误级别")
        
        if classification.subcategory:
            base_action += f" ({classification.subcategory})"
        
        return base_action
    
    def find_related_errors(
        self,
        error_record: Dict,
        all_errors: List[Dict],
        time_window_seconds: float = 60.0
    ) -> List[str]:
        related = []
        
        try:
            error_time = datetime.fromisoformat(error_record.get("timestamp", ""))
        except ValueError:
            return related
        
        for other in all_errors:
            if other.get("id") == error_record.get("id"):
                continue
            
            try:
                other_time = datetime.fromisoformat(other.get("timestamp", ""))
                delta = abs((error_time - other_time).total_seconds())
                
                if delta <= time_window_seconds:
                    related.append(other.get("id"))
            except ValueError:
                continue
        
        return related


if __name__ == "__main__":
    classifier = ErrorClassifier()
    classifier.set_startup_time(datetime.now())
    
    test_classification = classifier.classify(
        fault_type="HardFault",
        registers={"PC": "0x08004567"},
        fault_status={"CFSR": "0x00000200", "HFSR": "0x40000000"},
        description="Precise data bus error"
    )
    
    print(f"Severity: {test_classification.severity.value}")
    print(f"Source: {test_classification.source.value}")
    print(f"Category: {test_classification.category}")
    print(f"Subcategory: {test_classification.subcategory}")
    
    impact = classifier.estimate_error_impact(test_classification)
    print(f"Impact Score: {impact['impact_score']}")
    print(f"Action: {impact['recommended_action']}")
