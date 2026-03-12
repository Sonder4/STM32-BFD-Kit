#!/bin/bash
################################################################################
#                 寄存器数据采集脚本 for Linux (改进版)
# 功能：通过 J-Link 采集 STM32 外设寄存器并导出为 CSV 格式
# 改进：支持首行显示寄存器名称、时间戳格式、可选外设
################################################################################

# 默认参数
PERIPHERAL="USART1"
REGISTERS=""
DURATION=10
OUTPUT_FILE=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
PROFILE_HELPER="${PROJECT_ROOT}/build_tools/jlink/profile_env.sh"
if [[ -f "${PROFILE_HELPER}" ]]; then
    # shellcheck source=build_tools/jlink/profile_env.sh
    source "${PROFILE_HELPER}"
    if load_stm32_profile_env "${PROJECT_ROOT}" >/dev/null 2>&1; then
        DEVICE="${STM32_DEVICE}"
    else
        DEVICE="STM32H723VG"
    fi
else
    DEVICE="STM32H723VG"
fi
INTERFACE="SWD"
SPEED=4000
STATUS_ONLY=false
SAMPLE_INTERVAL=0  # 0 表示不等待，JLink 最快速度采集

# STM32H723 外设地址表
declare -A PERIPHERAL_ADDRESSES=(
    ["USART1"]="0x40013800"
    ["USART2"]="0x40004400"
    ["USART3"]="0x40004800"
    ["UART4"]="0x40004C00"
    ["UART5"]="0x40005000"
    ["UART7"]="0x40018000"
    ["UART8"]="0x40018400"
    ["FDCAN1"]="0x4000A000"
    ["FDCAN2"]="0x4000A400"
    ["FDCAN3"]="0x4000A800"
    ["SPI1"]="0x40013000"
    ["SPI2"]="0x40003800"
    ["SPI3"]="0x40003C00"
    ["I2C1"]="0x40005400"
    ["I2C2"]="0x40005800"
    ["I2C3"]="0x40005C00"
)

# USART 寄存器偏移量和名称
declare -A USART_REGISTERS=(
    ["CR1"]="0x00|Control Register 1"
    ["CR2"]="0x04|Control Register 2"
    ["CR3"]="0x08|Control Register 3"
    ["BRR"]="0x0C|Baud Rate Register"
    ["GTPR"]="0x10|Guard Time and Prescaler Register"
    ["RTOR"]="0x14|Receiver Timeout Register"
    ["RQR"]="0x18|Request Register"
    ["ISR"]="0x1C|Interrupt and Status Register"
    ["ICR"]="0x20|Interrupt Flag Clear Register"
    ["RDR"]="0x24|Receive Data Register"
    ["TDR"]="0x28|Transmit Data Register"
)

# FDCAN 寄存器偏移量和名称 (STM32H7 系列)
declare -A FDCAN_REGISTERS=(
    ["CREL"]="0x00|Core Release Register"
    ["ENDN"]="0x04|Byte Swap Register"
    ["DBTP"]="0x08|Data Bit Timing Register"
    ["TEST"]="0x0C|Test Register"
    ["RWD"]="0x10|RAM Watchdog Register"
    ["CCCR"]="0x18|CCC Control Register"
    ["NBTP"]="0x1C|Nominal Bit Timing Register"
    ["TSCC"]="0x20|Timestamp Counter Configuration"
    ["TSCV"]="0x24|Timestamp Counter Value"
    ["TOCC"]="0x28|Timeout Counter Configuration"
    ["TOCV"]="0x2C|Timeout Counter Value"
    ["ECR"]="0x40|Error Counter Register"
    ["PSR"]="0x44|Protocol Status Register"
    ["IR"]="0x50|Interrupt Register"
    ["IE"]="0x54|Interrupt Enable"
    ["ILS"]="0x58|Interrupt Line Select"
    ["ILE"]="0x5C|Interrupt Line Enable"
    ["GTSC"]="0x80|Global Timestamp Configuration"
    ["TDCR"]="0x8C|Transmitter Delay Compensation"
    ["TXBC"]="0x100|TX Buffer Configuration"
    ["TXBRP"]="0x108|TX Buffer Request Pending"
    ["TXBTO"]="0x10C|TX Buffer Transmission Occurred"
    ["TXBCF"]="0x110|TX Buffer Cancellation Finished"
    ["TXBTIE"]="0x118|TX Buffer Transmission Interrupt Enable"
    ["RXF0C"]="0x200|RX FIFO 0 Configuration"
    ["RXF0S"]="0x204|RX FIFO 0 Status"
    ["RXF0A"]="0x208|RX FIFO 0 Acknowledge"
    ["RXBC"]="0x214|RX Buffer Configuration"
)

# FDCAN 关键状态寄存器位定义
declare -A FDCAN_STATUS_BITS=(
    ["PSR"]="Protocol Status: LEc[2:0]=LEC Error Code, ACT[1:0]=Activity State"
    ["ECR"]="Error Counter: TEC[7:0]=Tx Error Count, REC[15:8]=Rx Error Count"
    ["CCCR"]="Control: INIT=Init Mode, CCE=Config Enable, TEST=Test Mode"
    ["TXBTO"]="TX Status: All bits=1 means all buffers transmitted"
    ["RXF0S"]="RX FIFO 0 Status: F0FL[6:0]=FIFO Fill Level"
)

# 显示使用说明
show_help() {
    echo "STM32 寄存器数据采集工具 (改进版)"
    echo ""
    echo "用法：$0 [选项]"
    echo ""
    echo "选项:"
    echo "  -p, --peripheral NAME   外设名称，默认：USART1"
    echo "  -r, --registers LIST    寄存器列表（逗号分隔），默认：全部常用寄存器"
    echo "  -d, --duration SEC      采集时长（秒），默认：10"
    echo "  -o, --output FILE       输出文件路径"
    echo "  -i, --interval MS       采样间隔（毫秒），默认：0(JLink 最快速度)"
    echo "  -s, --status            快速查看 CAN 状态（仅 FDCAN）"
    echo "  -h, --help              显示帮助信息"
    echo ""
    echo "采集时长预设:"
    echo "  1 秒：  $0 -d 1"
    echo "  30 秒： $0 -d 30"
    echo "  1 分钟：$0 -d 60"
    echo ""
    echo "采样间隔说明:"
    echo "  -i 0    : JLink 最快速度采集 (推荐)"
    echo "  -i 10   : 10ms 间隔 (高速模式)"
    echo "  -i 100  : 100ms 间隔 (标准模式)"
    echo ""
    echo "支持的外设:"
    for key in "${!PERIPHERAL_ADDRESSES[@]}"; do
        echo "  $key - 基地址：${PERIPHERAL_ADDRESSES[$key]}"
    done
    echo ""
    echo "CAN 状态查看 (推荐):"
    echo "  # 查看 FDCAN1 状态"
    echo "  $0 -p FDCAN1 -s"
    echo ""
    echo "  # 查看 FDCAN2 状态"
    echo "  $0 -p FDCAN2 -s"
    echo ""
    echo "示例:"
    echo "  # 采集 USART1 寄存器 1 秒"
    echo "  $0 -p USART1 -d 1"
    echo ""
    echo "  # 采集 FDCAN1 状态寄存器"
    echo "  $0 -p FDCAN1 -r CCCR,PSR,ECR,IR,TXBRP,RXF0S -d 5"
    echo ""
    echo "  # 只采集 ISR 寄存器"
    echo "  $0 -p USART1 -r ISR -d 10"
    echo ""
    echo "  # 采集多个特定寄存器"
    echo "  $0 -p USART1 -r ISR,ICR,RDR,TDR -d 30"
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--peripheral)
            PERIPHERAL="$2"
            shift 2
            ;;
        -r|--registers)
            REGISTERS="$2"
            shift 2
            ;;
        -d|--duration)
            DURATION="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -i|--interval)
            SAMPLE_INTERVAL="$2"
            shift 2
            ;;
        -s|--status)
            STATUS_ONLY=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "未知选项：$1"
            show_help
            exit 1
            ;;
    esac
done

# 验证必需参数
if [ -z "$PERIPHERAL" ]; then
    echo "错误：必须指定外设名称 (-p)"
    show_help
    exit 1
fi

# 检查外设是否存在
if [ -z "${PERIPHERAL_ADDRESSES[$PERIPHERAL]}" ]; then
    echo "错误：不支持的外设 '$PERIPHERAL'"
    echo "支持的外设列表:"
    for key in "${!PERIPHERAL_ADDRESSES[@]}"; do
        echo "  $key"
    done
    exit 1
fi

# 获取外设基地址
BASE_ADDRESS="${PERIPHERAL_ADDRESSES[$PERIPHERAL]}"

# 设置输出文件
if [ -z "$OUTPUT_FILE" ]; then
    OUTPUT_FILE="logs/debug/${PERIPHERAL,,}_capture_$(date +%Y%m%d_%H%M%S).csv"
fi
mkdir -p "$(dirname "$OUTPUT_FILE")"

# 检查 J-Link 是否安装
if ! command -v JLinkExe &> /dev/null; then
    echo "错误：未找到 JLinkExe，请确保 J-Link 软件已安装"
    exit 1
fi

# 获取当前时间戳 (ISO 8601 格式)
get_timestamp() {
    date +"%Y-%m-%dT%H:%M:%S.%3N%:z"
}

# FDCAN 状态解码函数
decode_fdcan_status() {
    local cccr=$1
    local psr=$2
    local ecr=$3
    local ir=$4
    local txbrp=$5
    local txbto=$6
    local rxf0s=$7

    echo ""
    echo "========== FDCAN 状态分析 =========="

    # CCCR - 控制寄存器
    local init=$(( (cccr & 0x01) ))
    local cce=$(( (cccr & 0x02) >> 1 ))
    echo "[CCCR 控制寄存器]"
    if [ $init -eq 1 ]; then
        echo "  - INIT=1: CAN 处于初始化模式 (未开启)"
    else
        echo "  - INIT=0: CAN 已正常工作"
    fi
    echo "  - CCE=$cce: 配置使能位"

    # PSR - 协议状态寄存器
    local lec=$(( psr & 0x07 ))
    local act=$(( (psr >> 4) & 0x03 ))
    echo ""
    echo "[PSR 协议状态寄存器]"
    case $lec in
        0) echo "  - LEC=0: 无错误" ;;
        1) echo "  - LEC=1: Bit 错误 (Stuff/Bit 错误)" ;;
        2) echo "  - LEC=2: Form 错误" ;;
        3) echo "  - LEC=3: ACK 错误" ;;
        4) echo "  - LEC=4: CRC 错误" ;;
        5) echo "  - LEC=5: Bit0 错误" ;;
        6) echo "  - LEC=6: Bit1 错误" ;;
        7) echo "  - LEC=7: Timeout" ;;
        *) echo "  - LEC=$lec: 其他错误" ;;
    esac

    case $act in
        0) echo "  - ACT=0: 同步到 CAN 总线 (正常)" ;;
        1) echo "  - ACT=1: 正在发送" ;;
        2) echo "  - ACT=2: 正在接收" ;;
        3) echo "  - ACT=3: 离线/恢复中" ;;
    esac

    # ECR - 错误计数器
    local tec=$(( ecr & 0xFF ))
    local rec=$(( (ecr >> 8) & 0x7F ))
    echo ""
    echo "[ECR 错误计数器]"
    echo "  - TEC (发送错误计数): $tec"
    echo "  - REC (接收错误计数): $rec"
    if [ $tec -gt 127 ] || [ $rec -gt 127 ]; then
        echo "  ⚠️  警告：错误计数较高!"
    fi
    if [ $tec -gt 255 ]; then
        echo "  ⚠️  严重：发送单元处于 Bus Off 状态!"
    fi

    # TXBRP/TXBTO - 发送状态
    echo ""
    echo "[TX 发送状态]"
    if [ "$txbrp" = "0x00000000" ]; then
        echo "  - 所有发送邮箱空闲"
    else
        echo "  - 有待发送的邮箱：$txbrp"
    fi
    if [ "$txbto" = "0x00000000" ]; then
        echo "  - 最近无发送完成"
    else
        echo "  - 发送完成邮箱：$txbto"
    fi

    # RXF0S - 接收 FIFO 状态
    local f0fl=$(( rxf0s & 0x07 ))
    echo ""
    echo "[RXF0 接收 FIFO 0 状态]"
    echo "  - 待处理消息数：$f0fl"
    if [ $f0fl -gt 0 ]; then
        echo "  ✓ 有数据可读取"
    fi

    echo ""
    echo "===================================="
}

# FDCAN 快速状态查看函数
fdcan_quick_status() {
    echo "=================================="
    echo "FDCAN 快速状态查看"
    echo "=================================="
    echo "设备：$DEVICE"
    echo "外设：$PERIPHERAL (基地址：$BASE_ADDRESS)"
    echo "=================================="
    echo ""

    # 读取所有状态寄存器
    declare -A reg_values

    for reg in "${REG_ARRAY[@]}"; do
        local reg_info="${FDCAN_REGISTERS[$reg]}"
        local offset=$(echo "$reg_info" | cut -d'|' -f1)
        local address=$((BASE_ADDRESS + offset))

        local value=$(JLinkExe -device "$DEVICE" -if "$INTERFACE" -speed "$SPEED" <<EOF 2>/dev/null
connect
h
w4 $(printf "0x%08X" $address)
exit
EOF
)
        local hex_value=$(echo "$value" | grep -oP '0x[0-9A-Fa-f]+' | tail -1)
        if [ -z "$hex_value" ]; then
            hex_value="0x00000000"
        fi
        reg_values[$reg]=$hex_value
    done

    echo "寄存器原始值:"
    for reg in "${!reg_values[@]}"; do
        echo "  $reg = ${reg_values[$reg]}"
    done

    # 解码状态
    decode_fdcan_status \
        $((16#${reg_values[CCCR]#0x})) \
        $((16#${reg_values[PSR]#0x})) \
        $((16#${reg_values[ECR]#0x})) \
        $((16#${reg_values[IR]#0x})) \
        ${reg_values[TXBRP]} \
        ${reg_values[TXBTO]} \
        ${reg_values[RXF0S]}
}

echo "=================================="
echo "寄存器数据采集 (改进版)"
echo "=================================="
echo "设备：$DEVICE"
echo "外设：$PERIPHERAL (基地址：$BASE_ADDRESS)"
echo "时长：${DURATION}秒"
echo "输出：$OUTPUT_FILE"
echo "=================================="
echo ""

# 确定要采集的寄存器
if [ -n "$REGISTERS" ]; then
    IFS=',' read -ra REG_ARRAY <<< "$REGISTERS"
else
    # 默认采集常用寄存器
    case $PERIPHERAL in
        USART*|UART*)
            REG_ARRAY=("ISR" "ICR" "RDR" "TDR" "CR1" "CR2" "CR3")
            ;;
        FDCAN*)
            # FDCAN 关键状态寄存器
            REG_ARRAY=("CCCR" "PSR" "ECR" "IR" "TXBRP" "TXBTO" "RXF0S")
            ;;
        *)
            REG_ARRAY=("CR1" "CR2" "CR3")
            ;;
    esac
fi

# 快速状态查看模式 (仅 FDCAN)
if [ "$STATUS_ONLY" = true ]; then
    if [[ "$PERIPHERAL" != FDCAN* ]]; then
        echo "错误：--status 参数仅支持 FDCAN 外设"
        exit 1
    fi
    REG_ARRAY=("CCCR" "PSR" "ECR" "IR" "TXBRP" "TXBTO" "RXF0S" "ILE")
    echo "快速查看 FDCAN 状态..."
fi

echo "采集寄存器：${REG_ARRAY[*]}"
if [ "$SAMPLE_INTERVAL" -eq 0 ]; then
    echo "采样间隔：无 (JLink 最快速度采集)"
else
    echo "采样间隔：${SAMPLE_INTERVAL}ms"
fi
echo ""

# 快速状态查看模式
if [ "$STATUS_ONLY" = true ]; then
    fdcan_quick_status
    exit 0
fi

# 创建 CSV 文件
START_TIME=$(get_timestamp)

# 构建 CSV 表头 - 首行显示时间戳和寄存器名称
HEADER="timestamp"
for reg in "${REG_ARRAY[@]}"; do
    HEADER="$HEADER,$reg"
done

cat > "$OUTPUT_FILE" <<EOF
# Device: $DEVICE
# Peripheral: $PERIPHERAL
# Base Address: $BASE_ADDRESS
# Capture Start: $START_TIME
# Duration: ${DURATION}s
# Interval: ${SAMPLE_INTERVAL}ms
#
$HEADER
EOF

# 开始采集
echo "开始采集..."
echo "按 Ctrl+C 可随时停止"
echo ""

# 记录开始时间 (epoch 秒)
START_EPOCH=$(date +%s.%N)
END_EPOCH=$(echo "$START_EPOCH + $DURATION" | bc)
SAMPLE_COUNT=0

# 基于时间的采集循环
while true; do
    CURRENT_EPOCH=$(date +%s.%N)
    ELAPSED=$(echo "$CURRENT_EPOCH - $START_EPOCH" | bc)

    # 检查是否达到采集时长
    if (( $(echo "$ELAPSED >= $DURATION" | bc -l) )); then
        break
    fi

    TIMESTAMP=$(get_timestamp)
    ROW="$TIMESTAMP"

    # 构建 J-Link 命令脚本 (一次读取所有寄存器)
    JLINK_CMDS="connect\nh\n"
    for reg in "${REG_ARRAY[@]}"; do
        # 获取寄存器偏移量
        offset="0x00"

        # 根据外设类型获取寄存器偏移量
        if [[ "$PERIPHERAL" == FDCAN* ]]; then
            reg_info="${FDCAN_REGISTERS[$reg]}"
        elif [[ "$PERIPHERAL" == USART* ]] || [[ "$PERIPHERAL" == UART* ]]; then
            reg_info="${USART_REGISTERS[$reg]}"
        fi

        if [ -n "$reg_info" ]; then
            offset=$(echo "$reg_info" | cut -d'|' -f1)
        fi

        # 计算寄存器地址
        address=$((BASE_ADDRESS + offset))
        JLINK_CMDS+="w4 $(printf "0x%08X" $address)\n"
    done
    JLINK_CMDS+="exit\n"

    # 执行 J-Link 命令并读取所有寄存器
    value=$(JLinkExe -device "$DEVICE" -if "$INTERFACE" -speed "$SPEED" <<EOF 2>/dev/null
$JLINK_CMDS
EOF
)

    # 解析 J-Link 输出，提取所有寄存器值
    for reg in "${REG_ARRAY[@]}"; do
        hex_value=$(echo "$value" | grep -oP '0x[0-9A-Fa-f]+' | head -n ${SAMPLE_COUNT} | tail -1)
        if [ -z "$hex_value" ]; then
            hex_value="0x00000000"
        fi
        ROW="$ROW,$hex_value"
    done

    echo "$ROW" >> "$OUTPUT_FILE"
    SAMPLE_COUNT=$((SAMPLE_COUNT + 1))

    # 显示进度 (每秒更新一次)
    if (( $(echo "$ELAPSED * 10 % 10 == 0" | bc -l) )); then
        progress=$(echo "($ELAPSED * 100) / $DURATION" | bc)
        printf "\r采集进度：%d%% (%.1fs/%ds)" $progress $ELAPSED $DURATION
    fi

    # 如果设置了采样间隔，则等待
    if [ "$SAMPLE_INTERVAL" -gt 0 ]; then
        sleep $(echo "scale=3; $SAMPLE_INTERVAL / 1000" | bc)
    fi
done

# 完成采集
END_TIME=$(get_timestamp)

# 更新 CSV 头部（添加结束时间）
TEMP_FILE=$(mktemp)
sed "s/# Duration: ${DURATION}s/# Capture End: $END_TIME\n# Duration: ${DURATION}s/" "$OUTPUT_FILE" > "$TEMP_FILE"
mv "$TEMP_FILE" "$OUTPUT_FILE"

echo ""
echo ""
echo "=================================="
echo "采集完成"
echo "=================================="
echo "输出文件：$OUTPUT_FILE"
echo "开始时间：$START_TIME"
echo "结束时间：$END_TIME"
echo "总采样数：$SAMPLE_COUNT"
echo "实际采样率：$(echo "scale=2; $SAMPLE_COUNT / $DURATION" | bc)  samples/s"
echo "=================================="

# 显示 CSV 文件前几行预览
echo ""
echo "CSV 文件预览 (前 5 行):"
echo "----------------------------------------"
head -n 6 "$OUTPUT_FILE"
echo "----------------------------------------"

exit 0
