#!/usr/bin/env python3
"""
STM32 ST-Link Flash Programmer
使用 STM32CubeProgrammer CLI 进行 Flash 编程
"""

import argparse
import subprocess
import sys
import os
import shutil
from pathlib import Path
from typing import Optional, List

DEFAULT_STM32_PROGRAMMER_CLI = (
    os.environ.get("STM32_PROGRAMMER_CLI")
    or shutil.which("STM32_Programmer_CLI")
    or "STM32_Programmer_CLI"
)
DEFAULT_SPEED = int(os.environ.get("STM32_SPEED_KHZ", "4000"))

class STLinkFlasher:
    def __init__(self, speed: int = DEFAULT_SPEED, verbose: bool = False, cli_path: str = DEFAULT_STM32_PROGRAMMER_CLI):
        self.speed = speed
        self.verbose = verbose
        self.cli_path = cli_path

        if os.path.isabs(self.cli_path):
            if not os.path.exists(self.cli_path):
                raise FileNotFoundError(f"STM32CubeProgrammer CLI not found: {self.cli_path}")
        else:
            resolved = shutil.which(self.cli_path)
            if not resolved:
                raise FileNotFoundError(f"STM32CubeProgrammer CLI not found in PATH: {self.cli_path}")
            self.cli_path = resolved
    
    def _run_command(self, args: List[str]) -> tuple:
        cmd = [self.cli_path] + args
        if self.verbose:
            print(f"Executing: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
    
    def connect(self, mode: str = "Normal") -> bool:
        print(f"Connecting to target via ST-Link (mode: {mode})...")
        
        args = [
            "-c", f"port=SWD",
            f"speed={self.speed}",
            f"mode={mode}"
        ]
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print("Connected successfully")
            if self.verbose:
                print(stdout)
            return True
        else:
            print(f"Connection failed: {stderr}")
            return False
    
    def detect_device(self) -> Optional[dict]:
        print("Detecting target device...")
        
        args = ["-c", "port=SWD", "-q"]
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            device_info = {}
            lines = stdout.split('\n')
            for line in lines:
                if 'Device ID' in line:
                    device_info['device_id'] = line.split(':')[1].strip()
                elif 'Device name' in line:
                    device_info['device_name'] = line.split(':')[1].strip()
                elif 'Flash size' in line:
                    device_info['flash_size'] = line.split(':')[1].strip()
            
            if device_info:
                print(f"Device detected: {device_info}")
            return device_info
        else:
            print(f"Device detection failed: {stderr}")
            return None
    
    def erase(self, mode: str = "all") -> bool:
        print(f"Erasing Flash (mode: {mode})...")
        
        args = [
            "-c", "port=SWD",
            "-e", mode
        ]
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print("Erase completed successfully")
            return True
        else:
            print(f"Erase failed: {stderr}")
            return False
    
    def flash(self, firmware_path: str, address: int = 0x08000000, 
              erase: bool = True, verify: bool = True) -> bool:
        firmware_path = os.path.abspath(firmware_path)
        
        if not os.path.exists(firmware_path):
            print(f"Firmware file not found: {firmware_path}")
            return False
        
        file_size = os.path.getsize(firmware_path)
        print(f"Flashing firmware: {firmware_path}")
        print(f"File size: {file_size} bytes")
        print(f"Target address: 0x{address:08X}")
        
        args = [
            "-c", "port=SWD", f"speed={self.speed}",
        ]
        
        if erase:
            args.extend(["-e", "all"])
        
        args.extend([
            "-w", firmware_path, f"0x{address:08X}",
        ])
        
        if verify:
            args.append("-v")
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print("Flash programming completed successfully")
            if self.verbose:
                print(stdout)
            return True
        else:
            print(f"Flash programming failed: {stderr}")
            print(stdout)
            return False
    
    def verify(self, firmware_path: str, address: int = 0x08000000) -> bool:
        firmware_path = os.path.abspath(firmware_path)
        
        if not os.path.exists(firmware_path):
            print(f"Firmware file not found: {firmware_path}")
            return False
        
        print(f"Verifying firmware at 0x{address:08X}...")
        
        args = [
            "-c", "port=SWD",
            "-v", firmware_path, f"0x{address:08X}"
        ]
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print("Verification passed")
            return True
        else:
            print(f"Verification failed: {stderr}")
            return False
    
    def reset(self) -> bool:
        print("Resetting target...")
        
        args = [
            "-c", "port=SWD",
            "-rst"
        ]
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print("Target reset successfully")
            return True
        else:
            print(f"Reset failed: {stderr}")
            return False
    
    def run(self) -> bool:
        print("Starting target execution...")
        
        args = [
            "-c", "port=SWD",
            "-run"
        ]
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print("Target started successfully")
            return True
        else:
            print(f"Start failed: {stderr}")
            return False
    
    def read_flash(self, output_path: str, address: int, size: int) -> bool:
        print(f"Reading Flash: 0x{address:08X}, size: {size} bytes")
        
        args = [
            "-c", "port=SWD",
            "-r", output_path, f"0x{address:08X}", str(size)
        ]
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print(f"Flash read completed: {output_path}")
            return True
        else:
            print(f"Flash read failed: {stderr}")
            return False
    
    def get_option_bytes(self) -> Optional[str]:
        print("Reading option bytes...")
        
        args = [
            "-c", "port=SWD",
            "-ob", "displ"
        ]
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print("Option bytes:")
            print(stdout)
            return stdout
        else:
            print(f"Failed to read option bytes: {stderr}")
            return None
    
    def set_option_bytes(self, options: dict) -> bool:
        print(f"Setting option bytes: {options}")
        
        args = [
            "-c", "port=SWD",
            "-ob"
        ]
        
        for key, value in options.items():
            args.append(f"{key}={value}")
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print("Option bytes updated successfully")
            return True
        else:
            print(f"Failed to update option bytes: {stderr}")
            return False
    
    def unlock(self) -> bool:
        print("Unlocking device...")
        
        args = [
            "-c", "port=SWD", "mode=UR",
            "-ob", "RDP=0xAA"
        ]
        
        ret, stdout, stderr = self._run_command(args)
        
        if ret == 0:
            print("Device unlocked successfully")
            return True
        else:
            print(f"Unlock failed: {stderr}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description="STM32 ST-Link Flash Programmer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --firmware firmware.bin
  %(prog)s --firmware firmware.bin --address 0x08000000 --erase --verify
  %(prog)s --detect
  %(prog)s --unlock
  %(prog)s --read flash_dump.bin --address 0x08000000 --size 0x10000
        """
    )
    
    parser.add_argument("--firmware", "-f", help="Firmware file path")
    parser.add_argument("--address", "-a", type=lambda x: int(x, 0), 
                       default=0x08000000, help="Target address (default: 0x08000000)")
    parser.add_argument("--speed", "-s", type=int, default=DEFAULT_SPEED, 
                       help=f"Connection speed in kHz (default: {DEFAULT_SPEED})")
    parser.add_argument("--erase", "-e", action="store_true", default=True,
                       help="Erase before flashing (default: True)")
    parser.add_argument("--no-erase", dest="erase", action="store_false",
                       help="Skip erase before flashing")
    parser.add_argument("--verify", "-v", action="store_true", default=True,
                       help="Verify after flashing (default: True)")
    parser.add_argument("--no-verify", dest="verify", action="store_false",
                       help="Skip verification")
    parser.add_argument("--reset", "-r", action="store_true", default=True,
                       help="Reset after flashing (default: True)")
    parser.add_argument("--no-reset", dest="reset", action="store_false",
                       help="Skip reset after flashing")
    parser.add_argument("--detect", "-d", action="store_true",
                       help="Detect target device")
    parser.add_argument("--unlock", "-u", action="store_true",
                       help="Unlock device (remove read protection)")
    parser.add_argument("--read", help="Read flash to file")
    parser.add_argument("--size", type=lambda x: int(x, 0),
                       help="Size to read (required with --read)")
    parser.add_argument("--option-bytes", "-ob", action="store_true",
                       help="Display option bytes")
    parser.add_argument("--verbose", "-V", action="store_true",
                       help="Verbose output")
    
    args = parser.parse_args()
    
    try:
        flasher = STLinkFlasher(speed=args.speed, verbose=args.verbose)
        
        if args.detect:
            device = flasher.detect_device()
            if device:
                print(f"\nDevice Information:")
                for key, value in device.items():
                    print(f"  {key}: {value}")
            else:
                sys.exit(1)
        
        elif args.unlock:
            if flasher.unlock():
                print("Device unlocked. Note: Flash has been erased.")
            else:
                sys.exit(1)
        
        elif args.read:
            if not args.size:
                print("Error: --size is required with --read")
                sys.exit(1)
            if not flasher.read_flash(args.read, args.address, args.size):
                sys.exit(1)
        
        elif args.option_bytes:
            if not flasher.get_option_bytes():
                sys.exit(1)
        
        elif args.firmware:
            if not flasher.connect():
                sys.exit(1)
            
            if not flasher.flash(args.firmware, args.address, 
                                args.erase, args.verify):
                sys.exit(1)
            
            if args.reset:
                if not flasher.reset():
                    sys.exit(1)
            
            print("\nFlash programming completed successfully!")
        
        else:
            parser.print_help()
            sys.exit(1)
    
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
