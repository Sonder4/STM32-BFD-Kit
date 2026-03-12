# STM32 Flash 工具参考手册

## 工具路径

| 工具 | 路径 |
|------|------|
| J-Link | `D:\STM32CubeCLT\Segger\JLink_V864a\` |
| ST-Link GDB Server | `D:\STM32CubeCLT\STLink-gdb-server\` |
| STM32CubeProgrammer | `D:\STM32CubeCLT\STM32CubeProgrammer\` |

## STM32CubeProgrammer CLI

### 基本命令格式

```bash
STM32_Programmer_CLI.exe -c port=<PORT> [options] -w <FILE> <ADDR> [options]
```

### 连接选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `-c port=SWD` | SWD 连接 | `-c port=SWD` |
| `-c port=JTAG` | JTAG 连接 | `-c port=JTAG` |
| `-c port=COMx` | UART 连接 | `-c port=COM3` |
| `-c port=USB` | USB DFU 连接 | `-c port=USB` |
| `speed=<kHz>` | 连接速度 | `speed=4000` |
| `mode=Normal` | 正常模式 | `mode=Normal` |
| `mode=UR` | 复位模式 | `mode=UR` |
| `mode=HotPlug` | 热插拔模式 | `mode=HotPlug` |

### 擦除选项

| 选项 | 说明 |
|------|------|
| `-e all` | 全片擦除 |
| `-e sectors` | 扇区擦除 |
| `-e bank1` | Bank1 擦除 |
| `-e bank2` | Bank2 擦除 |

### 编程选项

| 选项 | 说明 |
|------|------|
| `-w <file> <addr>` | 写入文件到指定地址 |
| `-v` | 校验 |
| `-rst` | 复位 |
| `-run` | 运行 |
| `-s` | 跳过擦除 |

### 读取选项

| 选项 | 说明 |
|------|------|
| `-r <file> <addr> <size>` | 读取 Flash 到文件 |
| `-u <file>` | 读取选项字节 |

### 选项字节

| 选项 | 说明 |
|------|------|
| `-ob displ` | 显示选项字节 |
| `-ob <key>=<value>` | 设置选项字节 |

### 常用选项字节

| 选项 | 说明 | 值 |
|------|------|-----|
| RDP | 读保护 | 0xAA (解除), 0x55 (Level 1) |
| WRP | 写保护 | 扇区位掩码 |
| BOR_LEV | BOR 级别 | 0-3 |
| IWDG_SW | 独立看门狗 | 0 (硬件), 1 (软件) |
| WWDG_SW | 窗口看门狗 | 0 (硬件), 1 (软件) |
| SWAP_BANK | Bank 交换 | 0 (Bank1), 1 (Bank2) |

### 示例命令

```bash
STM32_Programmer_CLI.exe -c port=SWD -q

STM32_Programmer_CLI.exe -c port=SWD -e all -w firmware.bin 0x08000000 -v -rst

STM32_Programmer_CLI.exe -c port=SWD -r flash_dump.bin 0x08000000 0x10000

STM32_Programmer_CLI.exe -c port=SWD -ob displ

STM32_Programmer_CLI.exe -c port=SWD -ob RDP=0xAA

STM32_Programmer_CLI.exe -c port=SWD -ob SWAP_BANK=1

STM32_Programmer_CLI.exe -c port=COM3 -b 115200 -w firmware.bin 0x08000000 -v -rst

STM32_Programmer_CLI.exe -c port=USB -w firmware.bin 0x08000000 -v -rst
```

## J-Link CLI

### 基本命令格式

```bash
JLink.exe -device <DEVICE> -if <IF> -speed <SPEED> [options]
```

### 连接选项

| 选项 | 说明 |
|------|------|
| `-device <name>` | 目标设备 |
| `-if SWD/JTAG` | 调试接口 |
| `-speed <kHz>` | 连接速度 |
| `-autoconnect 1` | 自动连接 |
| `-CommandFile <file>` | 脚本文件 |

### 内部命令

| 命令 | 说明 |
|------|------|
| `connect` | 连接目标 |
| `r` | 硬件复位 |
| `rx` | 复位并停止 |
| `h` | 停止 |
| `g` | 运行 |
| `erase` | 全片擦除 |
| `loadfile <file> <addr>` | 加载文件 |
| `verifyfile <file> <addr>` | 校验文件 |
| `savebin <file> <addr> <size>` | 保存二进制 |
| `loadbin <file> <addr>` | 加载二进制 |

### 内存命令

| 命令 | 说明 |
|------|------|
| `mem <addr> <num>` | 读取内存 (32-bit) |
| `mem8 <addr> <num>` | 读取内存 (8-bit) |
| `mem16 <addr> <num>` | 读取内存 (16-bit) |
| `w1 <addr> <val>` | 写入 8-bit |
| `w2 <addr> <val>` | 写入 16-bit |
| `w4 <addr> <val>` | 写入 32-bit |

### 示例命令

```bash
JLink.exe -device STM32H743VI -if SWD -speed 4000 -autoconnect 1

JLink.exe -device STM32H743VI -if SWD -CommandFile flash.jlink

JLink.exe -device STM32H743VI -if SWD -speed 4000 -autoconnect 1 -CommanderScript flash.jlink
```

### J-Link 脚本示例

```
connect
device STM32H743VI
si swd
speed 4000
r
h
erase
loadfile firmware.bin 0x08000000
verifyfile firmware.bin 0x08000000
r
g
exit
```

## OpenOCD

### 基本命令格式

```bash
openocd -f <interface.cfg> -f <target.cfg> [options]
```

### 常用配置文件

| 配置 | 说明 |
|------|------|
| `interface/stlink.cfg` | ST-Link 接口 |
| `interface/jlink.cfg` | J-Link 接口 |
| `target/stm32h7x.cfg` | STM32H7 目标 |

### 命令行选项

| 选项 | 说明 |
|------|------|
| `-f <file>` | 加载配置文件 |
| `-c <cmd>` | 执行命令 |
| `-s <dir>` | 搜索目录 |
| `-d <level>` | 调试级别 |
| `-l <file>` | 日志文件 |

### Telnet 命令

| 命令 | 说明 |
|------|------|
| `reset halt` | 复位并停止 |
| `reset run` | 复位并运行 |
| `halt` | 停止 |
| `resume` | 继续 |
| `flash write_image erase <file> <addr>` | 写入并擦除 |
| `flash erase_sector <bank> <first> <last>` | 擦除扇区 |
| `verify_image <file> <addr>` | 校验镜像 |
| `dump_image <file> <addr> <size>` | 导出镜像 |

### 示例命令

```bash
openocd -f interface/stlink.cfg -f target/stm32h7x.cfg

openocd -f interface/stlink.cfg -f target/stm32h7x.cfg -c "init; reset halt; flash write_image erase firmware.bin 0x08000000; verify_image firmware.bin 0x08000000; reset run; shutdown"

openocd -f interface/jlink.cfg -f target/stm32h7x.cfg -c "init; reset halt; flash erase_sector 0 0 last; shutdown"
```

## UART Bootloader

### 进入 Bootloader 模式

1. 设置 BOOT0 = 1, BOOT1 = 0
2. 复位目标
3. 通过 UART 连接

### STM32CubeProgrammer UART 命令

```bash
STM32_Programmer_CLI.exe -c port=COM3 -b 115200 -w firmware.bin 0x08000000 -v -rst
```

### UART Bootloader 协议

| 命令 | 代码 | 说明 |
|------|------|------|
| Get | 0x00 | 获取命令列表 |
| Get ID | 0x02 | 获取芯片 ID |
| Read Memory | 0x11 | 读取内存 |
| Go | 0x21 | 跳转执行 |
| Write Memory | 0x31 | 写入内存 |
| Erase | 0x43 | 擦除 |
| Read Protect | 0x82 | 读保护 |
| Read Unprotect | 0x92 | 解除读保护 |

## USB DFU

### 进入 DFU 模式

1. 设置 BOOT0 = 1, BOOT1 = 0
2. 连接 USB
3. 复位目标

### STM32CubeProgrammer DFU 命令

```bash
STM32_Programmer_CLI.exe -c port=USB -w firmware.bin 0x08000000 -v -rst
```

### dfu-util 命令

```bash
dfu-util -l

dfu-util -a 0 -D firmware.bin

dfu-util -a 0 -D firmware.bin -s 0x08000000
```

## STM32H7 特殊配置

### Flash 内存映射

| 区域 | 地址范围 | 大小 |
|------|----------|------|
| Bank 1 | 0x08000000 - 0x080FFFFF | 1 MB |
| Bank 2 | 0x08100000 - 0x081FFFFF | 1 MB |
| ITCM | 0x00000000 - 0x0000FFFF | 64 KB |
| AXIM | 0x08000000 - 0x081FFFFF | 2 MB |

### 扇区大小

- 每个扇区 128 KB
- Bank 1: 8 个扇区 (Sector 0-7)
- Bank 2: 8 个扇区 (Sector 8-15)

### 双 Bank 操作

```bash
STM32_Programmer_CLI.exe -c port=SWD -e bank1 -w firmware_bank1.bin 0x08000000

STM32_Programmer_CLI.exe -c port=SWD -e bank2 -w firmware_bank2.bin 0x08100000

STM32_Programmer_CLI.exe -c port=SWD -ob SWAP_BANK=1
```

### Flash 寄存器

| 寄存器 | 地址 | 说明 |
|--------|------|------|
| FLASH_ACR | 0x52002000 | 访问控制 |
| FLASH_KEYR | 0x52002004 | 密钥 |
| FLASH_OPTKEYR | 0x52002008 | 选项密钥 |
| FLASH_SR | 0x5200200C | 状态 |
| FLASH_CR | 0x52002010 | 控制 |
| FLASH_OPTCR | 0x52002014 | 选项控制 |

### 解锁 Flash

```bash
# 使用 STM32CubeProgrammer
STM32_Programmer_CLI.exe -c port=SWD -ob SEC=0xAA

# 使用 OpenOCD
mww 0x52002004 0x45670123
mww 0x52002004 0xCDEF89AB
```

## 错误代码

### STM32CubeProgrammer 错误

| 错误代码 | 说明 | 解决方案 |
|----------|------|----------|
| T_SWO_ERR | SWO 配置错误 | 检查 SWV 配置 |
| T_IF_ERR | 接口错误 | 检查连接 |
| T_AP_ERR | 访问端口错误 | 检查调试接口 |
| T_DP_ERR | 调试端口错误 | 检查硬件连接 |
| T_MEM_ERR | 内存访问错误 | 检查地址范围 |
| T_SEC_ERR | 安全错误 | 解除安全保护 |
| T_RDY_ERR | 目标未就绪 | 复位后重试 |

### J-Link 错误

| 错误 | 说明 | 解决方案 |
|------|------|----------|
| ERROR: Could not find device | 未找到调试器 | 检查 USB 连接 |
| ERROR: Could not connect to target | 无法连接目标 | 检查目标供电和连接 |
| ERROR: Flash download failed | Flash 下载失败 | 先擦除再下载 |
| ERROR: Verification failed | 校验失败 | 重新下载 |

## 性能优化

### 下载速度

| 接口 | 典型速度 | 最大速度 |
|------|----------|----------|
| SWD | 4000 kHz | 8000 kHz |
| JTAG | 4000 kHz | 12000 kHz |
| UART | 115200 bps | 4000000 bps |
| USB DFU | ~1 MB/s | ~2 MB/s |

### 优化建议

1. 使用 SWD 接口 (比 JTAG 快)
2. 提高时钟速度 (最高 8 MHz)
3. 使用全片擦除 (比扇区擦除快)
4. 禁用校验 (调试时)
5. 使用批量命令 (减少连接开销)

## 安全注意事项

### 读保护级别

| 级别 | RDP 值 | 说明 |
|------|--------|------|
| Level 0 | 0xAA | 无保护 |
| Level 1 | 0x55-0xFA | 读保护 |
| Level 2 | 0xCC | 永久保护 |

### 安全配置

```bash
# 启用读保护 (Level 1)
STM32_Programmer_CLI.exe -c port=SWD -ob RDP=0x55

# 启用写保护
STM32_Programmer_CLI.exe -c port=SWD -ob WRP=0xFF

# 启用安全启动
STM32_Programmer_CLI.exe -c port=SWD -ob SEC=0x55

# 注意: Level 2 保护不可逆!
STM32_Programmer_CLI.exe -c port=SWD -ob RDP=0xCC
```

## 故障排除

### 连接问题

1. **检查硬件连接**
   - SWDIO, SWCLK, GND, VCC
   - 目标供电正常
   - 调试器工作正常

2. **检查目标状态**
   - 是否处于低功耗模式
   - 是否被读保护
   - 是否需要复位

3. **降低连接速度**
   - 从 4000 kHz 降到 1000 kHz
   - 使用复位模式连接

### 编程问题

1. **擦除失败**
   - 检查 Flash 锁定状态
   - 解锁 Flash
   - 检查电源稳定性

2. **写入失败**
   - 确保先擦除
   - 检查地址正确性
   - 检查固件大小

3. **校验失败**
   - 重新烧录
   - 检查 Flash 完整性
   - 检查电源稳定性

### 调试技巧

1. **使用详细日志**
   ```bash
   STM32_Programmer_CLI.exe -c port=SWD -l 1
   ```

2. **检查设备信息**
   ```bash
   STM32_Programmer_CLI.exe -c port=SWD -q
   ```

3. **读取 Flash 内容**
   ```bash
   STM32_Programmer_CLI.exe -c port=SWD -r flash.bin 0x08000000 0x1000
   ```
