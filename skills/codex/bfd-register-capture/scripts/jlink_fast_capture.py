#!/usr/bin/env python3
################################################################################
# J-Link 高速寄存器采集脚本 (使用 J-Link Python API)
# 功能：通过 J-Link Python API 在单次连接中高速采集外设寄存器
################################################################################

import sys
import time
import argparse
import os
from datetime import datetime
from collections import OrderedDict

# 尝试导入 pylink
try:
    from pylink import JLink
    from pylink.enums import JLinkInterfaces
    PYLINK_AVAILABLE = True
except ImportError:
    PYLINK_AVAILABLE = False

DEFAULT_DEVICE = os.environ.get("STM32_DEVICE", "STM32H723VG")
DEFAULT_SPEED = int(os.environ.get("STM32_SPEED_KHZ", "4000"))

# STM32H723 外设地址表
PERIPHERAL_ADDRESSES = {
    "USART1": 0x40013800,
    "USART2": 0x40004400,
    "USART3": 0x40004800,
    "UART4": 0x40004C00,
    "UART5": 0x40005000,
    "UART7": 0x40018000,
    "UART8": 0x40018400,
    "FDCAN1": 0x4000A000,
    "FDCAN2": 0x4000A400,
    "FDCAN3": 0x4000A800,
    "SPI1": 0x40013000,
    "SPI2": 0x40003800,
    "SPI3": 0x40003C00,
    "I2C1": 0x40005400,
    "I2C2": 0x40005800,
    "I2C3": 0x40005C00,
}

# USART 寄存器偏移量
USART_REGISTERS = OrderedDict([
    ("CR1", 0x00),
    ("CR2", 0x04),
    ("CR3", 0x08),
    ("BRR", 0x0C),
    ("GTPR", 0x10),
    ("RTOR", 0x14),
    ("RQR", 0x18),
    ("ISR", 0x1C),
    ("ICR", 0x20),
    ("RDR", 0x24),
    ("TDR", 0x28),
])

# FDCAN 寄存器偏移量
FDCAN_REGISTERS = OrderedDict([
    ("CREL", 0x00),
    ("ENDN", 0x04),
    ("DBTP", 0x08),
    ("TEST", 0x0C),
    ("RWD", 0x10),
    ("CCCR", 0x18),
    ("NBTP", 0x1C),
    ("TSCC", 0x20),
    ("TSCV", 0x24),
    ("TOCC", 0x28),
    ("TOCV", 0x2C),
    ("ECR", 0x40),
    ("PSR", 0x44),
    ("IR", 0x50),
    ("IE", 0x54),
    ("ILS", 0x58),
    ("ILE", 0x5C),
    ("TXBC", 0x100),
    ("TXBRP", 0x108),
    ("TXBTO", 0x10C),
    ("RXF0C", 0x200),
    ("RXF0S", 0x204),
])


def get_timestamp():
    """获取 ISO 8601 格式时间戳"""
    now = datetime.now()
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}" + \
           time.strftime("%z", time.localtime())


def get_default_registers(peripheral):
    """获取外设的默认寄存器列表"""
    if peripheral.startswith("USART") or peripheral.startswith("UART"):
        return ["ISR", "ICR", "RDR", "TDR", "CR1", "CR2", "CR3"]
    elif peripheral.startswith("FDCAN"):
        return ["CCCR", "PSR", "ECR", "IR", "TXBRP", "TXBTO", "RXF0S"]
    else:
        return ["CR1", "CR2", "CR3"]


def get_register_offset(peripheral, reg_name):
    """获取寄存器偏移量"""
    if peripheral.startswith("USART") or peripheral.startswith("UART"):
        return USART_REGISTERS.get(reg_name, 0)
    elif peripheral.startswith("FDCAN"):
        return FDCAN_REGISTERS.get(reg_name, 0)
    return 0


def capture_with_pylink(peripheral, registers, duration, output_file, device, speed):
    """使用 pylink 进行高速采集"""
    if not PYLINK_AVAILABLE:
        print("错误：pylink 库未安装，请运行：pip install pylink-square")
        return False

    print(f"正在连接 {device}...")

    try:
        # 连接 J-Link
        jlink = JLink()
        jlink.open(serial_no=None)
        jlink.set_tif(JLinkInterfaces.SWD)
        jlink.set_speed(speed)
        jlink.connect(device, verbose=False)
        jlink.halt()

        print(f"J-Link 连接成功")
        print(f"采集时长：{duration}秒")

        # 获取外设基地址
        base_addr = PERIPHERAL_ADDRESSES.get(peripheral, 0)
        if base_addr == 0:
            print(f"错误：不支持的外设 '{peripheral}'")
            return False

        # 计算寄存器地址列表
        reg_addresses = []
        for reg_name in registers:
            offset = get_register_offset(peripheral, reg_name)
            reg_addresses.append((reg_name, base_addr + offset))

        # 创建 CSV 文件
        start_time = get_timestamp()
        header = "timestamp," + ",".join(registers)

        samples = []
        start_epoch = time.time()
        end_epoch = start_epoch + duration

        print(f"开始采集... (按 Ctrl+C 停止)")

        sample_count = 0
        while time.time() < end_epoch:
            timestamp = get_timestamp()
            row = [timestamp]

            # 读取所有寄存器
            for reg_name, addr in reg_addresses:
                try:
                    value = jlink.read_memory_32(addr)
                    row.append(f"0x{value:08X}")
                except Exception as e:
                    row.append("0x00000000")

            samples.append(",".join(row))
            sample_count += 1

            # 显示进度
            elapsed = time.time() - start_epoch
            progress = int((elapsed / duration) * 100)
            print(f"\r采集进度：{progress}% ({sample_count} samples)", end="", flush=True)

        # 写入 CSV 文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# Device: {device}\n")
            f.write(f"# Peripheral: {peripheral}\n")
            f.write(f"# Base Address: 0x{base_addr:08X}\n")
            f.write(f"# Capture Start: {start_time}\n")
            f.write(f"# Duration: {duration}s\n")
            f.write(f"#\n")
            f.write(header + "\n")
            for sample in samples:
                f.write(sample + "\n")

        end_time = get_timestamp()
        actual_duration = time.time() - start_epoch
        sample_rate = sample_count / actual_duration

        print(f"\n\n采集完成!")
        print(f"总采样数：{sample_count}")
        print(f"实际采样率：{sample_rate:.1f} samples/s")
        print(f"输出文件：{output_file}")

        jlink.close()
        return True

    except Exception as e:
        print(f"\n错误：{e}")
        return False


def capture_with_jlink_exe(peripheral, registers, duration, output_file, device, speed):
    """使用 JLinkExe 进行采集 (备选方案)"""
    import subprocess
    import tempfile
    import os

    # 获取外设基地址
    base_addr = PERIPHERAL_ADDRESSES.get(peripheral, 0)
    if base_addr == 0:
        print(f"错误：不支持的外设 '{peripheral}'")
        return False

    # 计算寄存器地址列表
    reg_addresses = []
    for reg_name in registers:
        offset = get_register_offset(peripheral, reg_name)
        reg_addresses.append((reg_name, base_addr + offset))

    # 创建 CSV 文件
    start_time = get_timestamp()
    header = "timestamp," + ",".join(registers)

    samples = []
    start_epoch = time.time()
    end_epoch = start_epoch + duration

    print(f"开始采集... (按 Ctrl+C 停止)")

    sample_count = 0

    # 创建临时 J-Link 脚本文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jlink', delete=False) as f:
        jlink_script = f.name
        f.write(f"device {device}\n")
        f.write(f"speed {speed}\n")
        f.write("connect\n")
        f.write("h\n")

        # 添加寄存器读取命令
        for reg_name, addr in reg_addresses:
            f.write(f"w4 0x{addr:08X}\n")

        f.write("exit\n")

    try:
        while time.time() < end_epoch:
            timestamp = get_timestamp()

            # 执行 J-Link 脚本
            result = subprocess.run(
                ["JLinkExe", "-device", device, "-if", "SWD", "-speed", str(speed),
                 "-commandfile", jlink_script],
                capture_output=True, text=True
            )

            # 解析输出
            row = [timestamp]
            for line in result.stdout.split('\n'):
                if '0x' in line:
                    # 提取十六进制值
                    import re
                    matches = re.findall(r'0x[0-9A-Fa-f]+', line)
                    for match in matches:
                        row.append(match.upper())

            # 补齐缺失的值
            while len(row) < len(registers) + 1:
                row.append("0x00000000")

            samples.append(",".join(row[:len(registers) + 1]))
            sample_count += 1

            # 显示进度
            elapsed = time.time() - start_epoch
            progress = int((elapsed / duration) * 100)
            print(f"\r采集进度：{progress}% ({sample_count} samples)", end="", flush=True)

    except KeyboardInterrupt:
        print("\n用户中断采集")
    finally:
        os.unlink(jlink_script)

    # 写入 CSV 文件
    end_time = get_timestamp()
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# Device: {device}\n")
        f.write(f"# Peripheral: {peripheral}\n")
        f.write(f"# Base Address: 0x{base_addr:08X}\n")
        f.write(f"# Capture Start: {start_time}\n")
        f.write(f"# Capture End: {end_time}\n")
        f.write(f"# Duration: {duration}s\n")
        f.write(f"#\n")
        f.write(header + "\n")
        for sample in samples:
            f.write(sample + "\n")

    actual_duration = time.time() - start_epoch
    sample_rate = sample_count / actual_duration if actual_duration > 0 else 0

    print(f"\n\n采集完成!")
    print(f"总采样数：{sample_count}")
    print(f"实际采样率：{sample_rate:.1f} samples/s")
    print(f"输出文件：{output_file}")

    return True


def main():
    parser = argparse.ArgumentParser(description='J-Link 高速寄存器采集工具')
    parser.add_argument('-p', '--peripheral', type=str, required=True,
                        help='外设名称 (如 USART1, FDCAN1)')
    parser.add_argument('-r', '--registers', type=str, default='',
                        help='寄存器列表 (逗号分隔)，默认使用常用寄存器')
    parser.add_argument('-d', '--duration', type=int, default=10,
                        help='采集时长 (秒)，默认 10')
    parser.add_argument('-o', '--output', type=str, default='',
                        help='输出文件路径')
    parser.add_argument('--device', type=str, default=DEFAULT_DEVICE,
                        help=f'设备型号，默认 {DEFAULT_DEVICE}')
    parser.add_argument('--speed', type=int, default=DEFAULT_SPEED,
                        help=f'J-Link 速度 (kHz)，默认 {DEFAULT_SPEED}')
    parser.add_argument('--method', type=str, choices=['pylink', 'jlink_exe'],
                        default='pylink',
                        help='采集方法：pylink (Python API) 或 jlink_exe (命令行)')

    args = parser.parse_args()

    # 设置输出文件
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"{args.peripheral.lower()}_capture_{timestamp}.csv"

    # 确定寄存器列表
    if args.registers:
        registers = args.registers.split(',')
    else:
        registers = get_default_registers(args.peripheral)

    print("==================================")
    print("J-Link 高速寄存器采集工具")
    print("==================================")
    print(f"设备：{args.device}")
    print(f"外设：{args.peripheral}")
    print(f"寄存器：{', '.join(registers)}")
    print(f"采集方法：{args.method}")
    print("==================================")
    print()

    # 选择采集方法
    if args.method == 'pylink':
        if PYLINK_AVAILABLE:
            success = capture_with_pylink(
                args.peripheral, registers, args.duration,
                args.output, args.device, args.speed
            )
        else:
            print("pylink 库未安装，切换到 jlink_exe 方法...")
            success = capture_with_jlink_exe(
                args.peripheral, registers, args.duration,
                args.output, args.device, args.speed
            )
    else:
        success = capture_with_jlink_exe(
            args.peripheral, registers, args.duration,
            args.output, args.device, args.speed
        )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
