# BFD Debug Interface Reference

## Tool Paths

| Tool | Path |
|------|------|
| J-Link | `D:\STM32CubeCLT\Segger\JLink_V864a\` |
| ST-Link | `D:\STM32CubeCLT\STLink-gdb-server\` |
| SVD Files | `D:\STM32CubeCLT\STMicroelectronics_CMSIS_SVD\` |

## J-Link Commander Commands

### Connection

```
JLink.exe -device STM32H743VI -if SWD -speed 4000
```

| Command | Description |
|---------|-------------|
| `connect` | Connect to target |
| `r` | Reset target |
| `g` | Go (resume execution) |
| `h` | Halt target |
| `?` | Show current state |

### Memory Operations

| Command | Description |
|---------|-------------|
| `mem <addr> <num>` | Read memory (bytes) |
| `mem8 <addr> <num>` | Read 8-bit values |
| `mem16 <addr> <num>` | Read 16-bit values |
| `mem32 <addr> <num>` | Read 32-bit values |
| `w1 <addr> <val>` | Write 8-bit value |
| `w2 <addr> <val>` | Write 16-bit value |
| `w4 <addr> <val>` | Write 32-bit value |
| `loadfile <file>` | Load hex/bin file |
| `loadbin <file> <addr>` | Load binary at address |

### Register Operations

| Command | Description |
|---------|-------------|
| `regs` | Display registers |
| `rreg <name>` | Read register |
| `wreg <name> <val>` | Write register |

### RTT Commands

| Command | Description |
|---------|-------------|
| `rtt` | Show RTT info |
| `rtt start` | Start RTT |
| `rtt stop` | Stop RTT |
| `rtt set terminal <n>` | Set terminal number |

### Breakpoint Commands

| Command | Description |
|---------|-------------|
| `bpset <addr>` | Set breakpoint |
| `bpclr <handle>` | Clear breakpoint |
| `bpclrall` | Clear all breakpoints |

## J-Link GDB Server

### Starting GDB Server

```bash
JLinkGDBServer.exe -device STM32H743VI -if SWD -speed 4000 -port 2331
```

### Common Options

| Option | Description |
|--------|-------------|
| `-device <name>` | Target device name |
| `-if <interface>` | Interface (SWD/JTAG) |
| `-speed <kHz>` | Communication speed |
| `-port <port>` | GDB server port |
| `-swoport <port>` | SWO port |
| `-telnetport <port>` | Telnet port |
| `-strict` | Strict mode |
| `-vd` | Verify download |
| `-nogui` | No GUI mode |

## ST-Link CLI Commands

### Starting GDB Server

```bash
ST-LINK_gdbserver.exe -p 61234 -m 1
```

### ST-LINK_CLI Commands

| Command | Description |
|---------|-------------|
| `-P <file>` | Program flash |
| `-V` | Verify after programming |
| `-Rst` | Reset target |
| `-Run` | Start execution |
| `-Halt` | Halt target |
| `-Mode <mode>` | Set debug mode |
| `-Freq <kHz>` | Set communication frequency |

## GDB Commands Reference

### Connection

```gdb
target remote localhost:2331    Connect to J-Link GDB server
target remote localhost:61234   Connect to ST-Link GDB server
file <elf_file>                 Load symbol file
load                            Load program to target
```

### Execution Control

| Command | Short | Description |
|---------|-------|-------------|
| `run` | `r` | Start execution |
| `continue` | `c` | Continue execution |
| `step` | `s` | Step into (source) |
| `stepi` | `si` | Step into (instruction) |
| `next` | `n` | Step over (source) |
| `nexti` | `ni` | Step over (instruction) |
| `finish` | | Run until function returns |
| `until` | `u` | Run until line/address |
| `jump <addr>` | `j` | Jump to address |

### Breakpoints

| Command | Description |
|---------|-------------|
| `break <func>` | Break at function |
| `break <file>:<line>` | Break at line |
| `break *<addr>` | Break at address |
| `break <func> if <cond>` | Conditional breakpoint |
| `tbreak <func>` | Temporary breakpoint |
| `hbreak <func>` | Hardware breakpoint |
| `info breakpoints` | List breakpoints |
| `delete <num>` | Delete breakpoint |
| `disable <num>` | Disable breakpoint |
| `enable <num>` | Enable breakpoint |
| `ignore <num> <count>` | Ignore N hits |
| `condition <num> <expr>` | Set condition |

### Watchpoints

| Command | Description |
|---------|-------------|
| `watch <var>` | Write watchpoint |
| `rwatch <var>` | Read watchpoint |
| `awatch <var>` | Access watchpoint |
| `info watchpoints` | List watchpoints |

### Variable Display

| Command | Description |
|---------|-------------|
| `print <var>` | Print variable |
| `print/x <var>` | Print in hex |
| `print/d <var>` | Print in decimal |
| `print/t <var>` | Print in binary |
| `print *<ptr>` | Print dereferenced pointer |
| `print <arr>[0]@<n>` | Print array elements |
| `display <var>` | Auto-display on stop |
| `undisplay <num>` | Remove auto-display |
| `info display` | List auto-displays |

### Memory Operations

| Command | Description |
|---------|-------------|
| `x/<n><f><s> <addr>` | Examine memory |
| `x/10x <addr>` | 10 words in hex |
| `x/20b <addr>` | 20 bytes |
| `x/5i <addr>` | 5 instructions |
| `x/s <addr>` | String |
| `set {int}<addr> = <val>` | Write word |
| `set {char}<addr> = <val>` | Write byte |

### Format Specifiers

| Specifier | Description |
|-----------|-------------|
| `x` | Hexadecimal |
| `d` | Decimal |
| `u` | Unsigned decimal |
| `o` | Octal |
| `t` | Binary |
| `a` | Address |
| `c` | Character |
| `f` | Floating-point |
| `i` | Instruction |
| `s` | String |

### Size Specifiers

| Specifier | Size |
|-----------|------|
| `b` | Byte (8-bit) |
| `h` | Halfword (16-bit) |
| `w` | Word (32-bit) |
| `g` | Giant (64-bit) |

### Registers

| Command | Description |
|---------|-------------|
| `info registers` | Show all registers |
| `info all-registers` | Include floating-point |
| `print $<reg>` | Print register |
| `set $<reg> = <val>` | Set register |

### Stack

| Command | Description |
|---------|-------------|
| `backtrace` | `bt` | Call stack |
| `backtrace full` | Stack with locals |
| `frame <n>` | Switch frame |
| `up` | Up one frame |
| `down` | Down one frame |
| `info frame` | Frame details |
| `info locals` | Local variables |
| `info args` | Function arguments |

### Monitor Commands

| Command | Description |
|---------|-------------|
| `monitor reset` | Reset target |
| `monitor reset halt` | Reset and halt |
| `monitor halt` | Halt target |
| `monitor go` | Resume execution |
| `monitor regs` | Show registers |
| `monitor memU32 <addr> <n>` | Read memory |
| `monitor semihosting enable` | Enable semihosting |
| `monitor flash breakpoints <0/1>` | Flash breakpoints |

## Cortex-M Fault Registers

### Fault Status Registers

| Register | Address | Description |
|----------|---------|-------------|
| CFSR | 0xE000ED28 | Configurable Fault Status |
| HFSR | 0xE000ED2C | HardFault Status |
| DFSR | 0xE000ED30 | Debug Fault Status |
| AFSR | 0xE000ED3C | Auxiliary Fault Status |
| MMFAR | 0xE000ED34 | MemManage Fault Address |
| BFAR | 0xE000ED38 | Bus Fault Address |

### CFSR Bit Fields

**MemManage Fault Status (Bits 0-7):**

| Bit | Name | Description |
|-----|------|-------------|
| 0 | IACCVIOL | Instruction access violation |
| 1 | DACCVIOL | Data access violation |
| 3 | MUNSTKERR | MemManage unstacking error |
| 4 | MSTKERR | MemManage stacking error |
| 5 | MLSPERR | MemManage FP lazy state error |
| 7 | MMARVALID | MMFAR valid |

**Bus Fault Status (Bits 8-15):**

| Bit | Name | Description |
|-----|------|-------------|
| 8 | IBUSERR | Instruction bus error |
| 9 | PRECISERR | Precise data bus error |
| 10 | IMPRECISERR | Imprecise data bus error |
| 11 | UNSTKERR | Bus unstacking error |
| 12 | STKERR | Bus stacking error |
| 13 | LSPERR | Bus FP lazy state error |
| 15 | BFARVALID | BFAR valid |

**Usage Fault Status (Bits 16-31):**

| Bit | Name | Description |
|-----|------|-------------|
| 16 | UNDEFINSTR | Undefined instruction |
| 17 | INVSTATE | Invalid state |
| 18 | INVPC | Invalid PC |
| 19 | NOCP | No coprocessor |
| 24 | UNALIGNED | Unaligned access |
| 25 | DIVBYZERO | Divide by zero |

### HFSR Bit Fields

| Bit | Name | Description |
|-----|------|-------------|
| 0 | VECTTBL | Vector table read fault |
| 1 | - | Reserved |
| 2 | FORCED | Forced HardFault |
| 30 | DEBUGEVT | Debug event |
| 31 | DEBUG_VT | Debug vector table read |

### HardFault Analysis Script

```gdb
define hardfault_analyze
  echo \n=== HardFault Analysis ===\n
  echo CFSR: 
  x/1x 0xE000ED28
  echo HFSR: 
  x/1x 0xE000ED2C
  echo MMFAR: 
  x/1x 0xE000ED34
  echo BFAR: 
  x/1x 0xE000ED38
  echo \nStacked Registers:\n
  echo R0: 
  x/1x $sp+0
  echo R1: 
  x/1x $sp+4
  echo R2: 
  x/1x $sp+8
  echo R3: 
  x/1x $sp+12
  echo R12: 
  x/1x $sp+16
  echo LR: 
  x/1x $sp+20
  echo PC: 
  x/1x $sp+24
  echo xPSR: 
  x/1x $sp+28
end
```

## STM32H7 Memory Map

| Region | Start Address | End Address | Size | Description |
|--------|---------------|-------------|------|-------------|
| ITCM | 0x00000000 | 0x0000FFFF | 64KB | Instruction TCM |
| ITCM Flash Alias | 0x00200000 | 0x003FFFFF | 2MB | Flash in ITCM |
| AXI Flash | 0x08000000 | 0x081FFFFF | 2MB | AXI Flash |
| DTCM | 0x20000000 | 0x2001FFFF | 128KB | Data TCM |
| AXI SRAM | 0x24000000 | 0x2407FFFF | 512KB | AXI SRAM |
| SRAM1 | 0x30000000 | 0x3001FFFF | 128KB | AHB SRAM1 |
| SRAM2 | 0x30020000 | 0x3003FFFF | 128KB | AHB SRAM2 |
| SRAM3 | 0x30040000 | 0x30047FFF | 32KB | AHB SRAM3 |
| SRAM4 | 0x38000000 | 0x3800FFFF | 64KB | AHB SRAM4 |
| Backup SRAM | 0x38800000 | 0x38800FFF | 4KB | Backup SRAM |
| Peripheral | 0x40000000 | 0x5FFFFFFF | - | Peripheral region |

## Common Debug Scenarios

### HardFault Debugging

1. Set breakpoint on HardFault_Handler
2. When triggered, examine stacked registers
3. Check CFSR/HFSR for fault type
4. Check BFAR/MMFAR for fault address
5. Examine PC to find faulting instruction

### Peripheral Not Working

1. Check RCC clock enable for peripheral
2. Verify GPIO pin configuration
3. Check alternate function mapping
4. Verify peripheral registers configuration
5. Check NVIC interrupt enable

### Interrupt Issues

1. Verify NVIC enable for interrupt
2. Check interrupt priority settings
3. Verify vector table configuration
4. Check for interrupt masking
5. Verify peripheral interrupt flags

### Memory Corruption

1. Set watchpoint on corrupted memory
2. Check stack size and usage
3. Look for buffer overflows
4. Check DMA configuration
5. Verify memory protection settings

## Debug Session Checklist

- [ ] Connect debug probe
- [ ] Power on target
- [ ] Start GDB server
- [ ] Connect GDB client
- [ ] Load symbols (ELF file)
- [ ] Load program to target
- [ ] Set initial breakpoints
- [ ] Verify program execution
- [ ] Debug as needed
- [ ] Clean up on exit
