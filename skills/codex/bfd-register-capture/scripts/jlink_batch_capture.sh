#!/bin/bash
################################################################################
# J-Link 高速寄存器采集脚本 (简化版)
# 使用 JLinkExe 批处理方式，预生成所有采集命令
################################################################################

# 默认参数
PERIPHERAL="${1:-USART1}"
DURATION="${2:-5}"
OUTPUT_FILE="${3:-}"
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
SPEED=4000

# 外设地址表
declare -A PERIPH_ADDR=(
    ["USART1"]="0x40013800" ["USART2"]="0x40004400" ["USART3"]="0x40004800"
    ["FDCAN1"]="0x4000A000" ["FDCAN2"]="0x4000A400" ["FDCAN3"]="0x4000A800"
)

# USART 寄存器偏移
declare -A USART_REGS=(
    ["CR1"]="0x00" ["CR2"]="0x04" ["CR3"]="0x08" ["ISR"]="0x1C"
    ["ICR"]="0x20" ["RDR"]="0x24" ["TDR"]="0x28"
)

# FDCAN 寄存器偏移
declare -A FDCAN_REGS=(
    ["CCCR"]="0x18" ["PSR"]="0x44" ["ECR"]="0x40" ["IR"]="0x50"
    ["TXBRP"]="0x108" ["TXBTO"]="0x10C" ["RXF0S"]="0x204"
)

# 检查外设
BASE="${PERIPH_ADDR[$PERIPHERAL]}"
if [ -z "$BASE" ]; then
    echo "错误：不支持的外设 $PERIPHERAL"
    exit 1
fi

# 选择寄存器
if [[ "$PERIPHERAL" == FDCAN* ]]; then
    REGS=("CCCR" "PSR" "ECR" "IR" "TXBRP" "TXBTO" "RXF0S")
    declare -n REGMAP=FDCAN_REGS
    NUM_REGS=${#REGS[@]}
else
    REGS=("ISR" "ICR" "RDR" "TDR" "CR1" "CR2" "CR3")
    declare -n REGMAP=USART_REGS
    NUM_REGS=${#REGS[@]}
fi

# 创建临时脚本文件
JLINK_SCRIPT=$(mktemp --suffix=.jlink)
CSV_FILE="${OUTPUT_FILE:-logs/debug/${PERIPHERAL,,}_capture_$(date +%Y%m%d_%H%M%S).csv}"
mkdir -p "$(dirname "$CSV_FILE")"

# 生成 J-Link 脚本
{
    echo "device $DEVICE"
    echo "speed $SPEED"
    echo "connect"
    echo "h"

    # 计算采样次数
    SAMPLES=$((DURATION * 10))

    for ((i=0; i<SAMPLES; i++)); do
        for reg in "${REGS[@]}"; do
            offset="${REGMAP[$reg]}"
            addr=$((BASE + offset))
            # 使用 mem32 命令，输出格式更清晰
            printf "mem32 0x%08X,1\n" $addr
        done
    done

    echo "exit"
} > "$JLINK_SCRIPT"

echo "========================================"
echo "J-Link 高速寄存器采集"
echo "========================================"
echo "设备：$DEVICE"
echo "外设：$PERIPHERAL (基址：$BASE)"
echo "寄存器：${REGS[*]}"
echo "采样数：$SAMPLES (约 ${DURATION}秒)"
echo "脚本：$JLINK_SCRIPT"
echo "输出：$CSV_FILE"
echo "========================================"

# 创建 CSV
HEADER="timestamp,${REGS[*]}"
HEADER="${HEADER// /,}"
START_TS=$(date +"%Y-%m-%dT%H:%M:%S.%3N%:z")
START_EPOCH=$(date +%s.%N)

{
    echo "# Device: $DEVICE"
    echo "# Peripheral: $PERIPHERAL"
    echo "# Base: $BASE"
    echo "# Start: $START_TS"
    echo "# Samples: $SAMPLES"
    echo "#"
    echo "$HEADER"
} > "$CSV_FILE"

# 执行采集
echo "执行采集..."

# 临时文件存储原始数据
RAW_DATA=$(mktemp)

# 执行 J-Link 脚本并保存原始输出
JLinkExe -device "$DEVICE" -if SWD -speed $SPEED -commandfile "$JLINK_SCRIPT" 2>&1 > "$RAW_DATA"

# 解析输出并生成 CSV
echo "解析数据..."
{
    VALUES=()
    NUM_REGS=${#REGS[@]}
    SAMPLE_COUNT=0

    while IFS= read -r line; do
        # 匹配 mem32 输出格式：地址 = 值
        # 例如：40013800 = 00000000
        if [[ "$line" =~ ^[[:space:]]*([0-9A-Fa-f]{8})[[:space:]]*=[[:space:]]*([0-9A-Fa-f]{8}) ]]; then
            hex="0x${BASH_REMATCH[2]}"
            VALUES+=("$hex")

            # 收集完一个样本的所有寄存器值
            if [ ${#VALUES[@]} -eq $NUM_REGS ]; then
                ts=$(date +"%Y-%m-%dT%H:%M:%S.%3N%:z")
                row="$ts"
                for v in "${VALUES[@]}"; do
                    row="$row,$v"
                done
                echo "$row" >> "$CSV_FILE"
                VALUES=()
                SAMPLE_COUNT=$((SAMPLE_COUNT + 1))

                # 进度显示
                if (( SAMPLE_COUNT % 10 == 0 )); then
                    printf "\r已采集：%d samples" $SAMPLE_COUNT
                fi
            fi
        fi
    done < "$RAW_DATA"

    echo ""
    echo "完成！总采样数：$SAMPLE_COUNT"
}

# 清理
rm -f "$JLINK_SCRIPT" "$RAW_DATA"

END_EPOCH=$(date +%s.%N)
ACTUAL_DURATION=$(echo "$END_EPOCH - $START_EPOCH" | bc)
SAMPLE_RATE=$(echo "scale=1; $SAMPLE_COUNT / $ACTUAL_DURATION" | bc)

echo "========================================"
echo "采集完成"
echo "========================================"
echo "输出文件：$CSV_FILE"
echo "总采样数：$SAMPLE_COUNT"
echo "实际时长：${ACTUAL_DURATION}s"
echo "采样率：${SAMPLE_RATE} samples/s"
echo "寄存器数：${NUM_REGS}"
echo "========================================"
