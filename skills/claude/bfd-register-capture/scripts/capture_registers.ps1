#Requires -Version 7.0
<#
.SYNOPSIS
    Register Capture - 外设寄存器数据采集工具
.DESCRIPTION
    通过 SEGGER J-Link Commander 读取 STM32 外设寄存器并导出为 CSV 格式，支持时间戳记录和寄存器位域解码。
.PARAMETER Peripheral
    外设名称 (USART1, USART2, USART3, UART7, FDCAN1, FDCAN2, FDCAN3, SPI1, SPI2)
.PARAMETER Registers
    寄存器列表 (逗号分隔)，默认读取全部
.PARAMETER Interval
    采集间隔 (毫秒)，默认 100ms
.PARAMETER Count
    采集次数，默认 10 次
.PARAMETER Output
    输出文件路径，默认 {peripheral}_capture.csv
.PARAMETER Device
    设备型号，默认 STM32H723VGTx
.PARAMETER Speed
    调试速度 (kHz)，默认 4000
.PARAMETER JLinkPath
    J-Link 工具路径，默认 D:\STM32CubeCLT\Segger\JLink_V864a
.EXAMPLE
    .\capture_registers.ps1 -Peripheral USART1 -Interval 100 -Count 10
.EXAMPLE
    .\capture_registers.ps1 -Peripheral USART1 -Registers ISR,CR1,BRR -Output usart1_data.csv
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Peripheral,

    [Parameter(Mandatory = $false)]
    [string[]]$Registers,

    [Parameter(Mandatory = $false)]
    [int]$Interval = 100,

    [Parameter(Mandatory = $false)]
    [int]$Count = 10,

    [Parameter(Mandatory = $false)]
    [string]$Output,

    [Parameter(Mandatory = $false)]
    [string]$Device = "STM32H723VGTx",

    [Parameter(Mandatory = $false)]
    [int]$Speed = 4000,

    [Parameter(Mandatory = $false)]
    [string]$JLinkPath = "D:\STM32CubeCLT\Segger\JLink_V864a"
)

# 错误码定义
$EXIT_SUCCESS = 0
$EXIT_CONNECTION_ERROR = 1
$EXIT_INVALID_PERIPHERAL = 2
$EXIT_READ_ERROR = 3
$EXIT_FILE_WRITE_ERROR = 4

# J-Link Commander 路径
$JLinkCommand = Join-Path $JLinkPath "JLink.exe"

# 外设地址映射表
$PeripheralMap = @{
    "USART1" = 0x40013800
    "USART2" = 0x40004400
    "USART3" = 0x40004800
    "UART7"  = 0x40018000
    "FDCAN1" = 0x4000A000
    "FDCAN2" = 0x4000A400
    "FDCAN3" = 0x4000A800
    "SPI1"   = 0x40013000
    "SPI2"   = 0x40003800
}

# 寄存器偏移表 (按外设分类)
$RegisterOffsetMap = @{
    "USART" = @{
        "CR1"   = 0x00
        "CR2"   = 0x04
        "CR3"   = 0x08
        "BRR"   = 0x0C
        "GTPR"  = 0x10
        "RTOR"  = 0x14
        "RQR"   = 0x18
        "ISR"   = 0x1C
        "ICR"   = 0x20
        "RDR"   = 0x24
        "TDR"   = 0x28
    }
    "FDCAN" = @{
        "CCCR"  = 0x00
        "NBTP"  = 0x04
        "DBTP"  = 0x08
        "TSDC"  = 0x0C
        "IR"    = 0x50
        "IE"    = 0x54
        "ILS"   = 0x58
        "ILE"   = 0x5C
    }
    "SPI" = @{
        "CR1"   = 0x00
        "CR2"   = 0x04
        "SR"    = 0x08
        "DR"    = 0x0C
        "CRCPR" = 0x10
    }
}

# 寄存器位域解码表
$RegisterFieldMap = @{
    "ISR" = @{
        "TXE"  = @{ Bit = 0; Mask = 0x01; Desc = "Transmit data register empty" }
        "TXC"  = @{ Bit = 1; Mask = 0x02; Desc = "Transmission complete" }
        "RXNE" = @{ Bit = 3; Mask = 0x08; Desc = "Read data register not empty" }
        "IDLE" = @{ Bit = 5; Mask = 0x20; Desc = "Idle line detected" }
    }
}

# 验证 J-Link 路径
if (-not (Test-Path $JLinkCommand)) {
    Write-Error "[ERROR] J-Link not found at: $JLinkCommand"
    Write-Host "Please check J-Link installation path."
    exit $EXIT_CONNECTION_ERROR
}

# 验证外设名称
if (-not $PeripheralMap.ContainsKey($Peripheral)) {
    Write-Error "[ERROR] Invalid peripheral: $Peripheral"
    Write-Host "Supported peripherals: $($PeripheralMap.Keys -join ', ')"
    exit $EXIT_INVALID_PERIPHERAL
}

# 确定外设类型
$PeripheralType = $Peripheral -replace '\d+', ''
$BaseAddress = $PeripheralMap[$Peripheral]

# 确定要读取的寄存器
if (-not $Registers -or $Registers.Count -eq 0) {
    if ($RegisterOffsetMap.ContainsKey($PeripheralType)) {
        $Registers = @($RegisterOffsetMap[$PeripheralType].Keys)
    } else {
        $Registers = @("CR1", "CR2", "SR", "DR")
    }
}

# 设置默认输出文件
if (-not $Output) {
    $Output = "${Peripheral}_capture.csv"
}

Write-Host "=== Register Capture ==="
Write-Host "Device: $Device"
Write-Host "Peripheral: $Peripheral (Base: 0x$($BaseAddress.ToString("X8")))"
Write-Host "Registers: $($Registers -join ', ')"
Write-Host "Interval: ${Interval}ms"
Write-Host "Count: $Count"
Write-Host "Output: $Output"
Write-Host ""

# 生成 J-Link 脚本
$ScriptFile = [System.IO.Path]::GetTempFileName()

try {
    # 连接并停止目标
    $InitCommands = @(
        "connect -device $Device -if SWD -speed $Speed",
        "halt"
    )

    Set-Content -Path $ScriptFile -Value ($InitCommands -join "`n") -Encoding UTF8

    Write-Host "Connecting to target..."
    $ProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
    $ProcessInfo.FileName = $JLinkCommand
    $ProcessInfo.Arguments = "-scriptfile `"$ScriptFile`""
    $ProcessInfo.RedirectStandardOutput = $true
    $ProcessInfo.RedirectStandardError = $true
    $ProcessInfo.UseShellExecute = $false
    $ProcessInfo.CreateNoWindow = $true

    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $ProcessInfo
    $Process.Start() | Out-Null
    $Process.WaitForExit()

    if ($Process.ExitCode -ne 0) {
        Write-Error "[ERROR] Failed to connect to target"
        exit $EXIT_CONNECTION_ERROR
    }

    # 开始采集
    Write-Host "Starting register capture..."
    $Samples = @()
    $StartTime = Get-Date

    for ($i = 0; $i -lt $Count; $i++) {
        $SampleTime = Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffzzz"
        $SampleData = @{
            timestamp = $SampleTime
            sample_num = $i
        }

        foreach ($Reg in $Registers) {
            # 获取寄存器偏移
            $Offset = 0
            if ($RegisterOffsetMap.ContainsKey($PeripheralType)) {
                if ($RegisterOffsetMap[$PeripheralType].ContainsKey($Reg)) {
                    $Offset = $RegisterOffsetMap[$PeripheralType][$Reg]
                }
            }

            $Address = $BaseAddress + $Offset

            # 生成读取命令
            $ReadCommand = "memU32 0x$($Address.ToString("X8")) 1"
            Set-Content -Path $ScriptFile -Value $ReadCommand -Encoding UTF8

            $Process = New-Object System.Diagnostics.Process
            $Process.StartInfo = $ProcessInfo
            $Process.Start() | Out-Null
            $Output = $Process.StandardOutput.ReadToEnd()
            $Process.WaitForExit()

            # 解析输出 (格式：0xXXXXXXXX: 0xYYYYYYYY)
            $Value = 0
            if ($output -match '0x[0-9A-Fa-f]+:\s*(0x[0-9A-Fa-f]+)') {
                $Value = [Convert]::ToInt32($Matches[1], 16)
            }

            $SampleData["$($Peripheral)_$Reg"] = $Value
            $SampleData["$($Peripheral)_$Reg`_hex"] = $Value.ToString("X8")
            $SampleData["$($Peripheral)_$Reg`_dec"] = $Value
            $SampleData["$($Peripheral)_$Reg`_addr"] = "0x$($Address.ToString("X8"))"

            # 位域解码
            if ($RegisterFieldMap.ContainsKey($Reg)) {
                $FieldDecoded = ""
                foreach ($FieldName in $RegisterFieldMap[$Reg].Keys) {
                    $Field = $RegisterFieldMap[$Reg][$FieldName]
                    $FieldValue = ($Value -band $Field.Mask) -shr $Field.Bit
                    if ($FieldValue -gt 0) {
                        if ($FieldDecoded) { $FieldDecoded += "," }
                        $FieldDecoded += "$FieldName=$FieldValue"
                    }
                }
                $SampleData["$($Peripheral)_$Reg`_decoded"] = $FieldDecoded
            }
        }

        $Samples += $SampleData

        if ($i -lt $Count - 1) {
            Start-Sleep -Milliseconds $Interval
        }
    }

    # 停止目标并断开连接
    Set-Content -Path $ScriptFile -Value "exit" -Encoding UTF8
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $ProcessInfo
    $Process.Start() | Out-Null
    $Process.WaitForExit()

    # 生成 CSV
    Write-Host ""
    Write-Host "Saving to CSV..."

    $EndTime = Get-Date
    $CsvHeader = @"
# Device: $Device
# Peripheral: $Peripheral
# Capture Start: $($StartTime.ToString("yyyy-MM-ddTHH:mm:ss.fffzzz"))
# Capture End: $($EndTime.ToString("yyyy-MM-ddTHH:mm:ss.fffzzz"))
# Interval: ${Interval}ms
# Samples: $Count
#
timestamp,sample_num,"$(($Registers | ForEach-Object { "$Peripheral`_$_hex" }) -join ',')"

"@

    $CsvLines = @()
    foreach ($Sample in $Samples) {
        $Line = "$($Sample.timestamp),$($Sample.sample_num)"
        foreach ($Reg in $Registers) {
            $HexKey = "$($Peripheral)_$($Reg)_hex"
            $Line += ",0x$($Sample[$HexKey])"
        }
        $CsvLines += $Line
    }

    $CsvContent = $CsvHeader + ($CsvLines -join "`n")

    try {
        [System.IO.File]::WriteAllText(
            [System.IO.Path]::GetFullPath($Output),
            $CsvContent,
            [System.Text.Encoding]::UTF8
        )
        Write-Host "Saved $Count samples to: $Output" -ForegroundColor Green
    } catch {
        Write-Error "[ERROR] Failed to write file: $_"
        exit $EXIT_FILE_WRITE_ERROR
    }

    Write-Host ""
    Write-Host "=== Register Capture Complete ===" -ForegroundColor Green
    exit $EXIT_SUCCESS

} catch {
    Write-Error "[ERROR] Register capture failed: $_"
    exit $EXIT_READ_ERROR
} finally {
    # 清理临时文件
    if (Test-Path $ScriptFile) {
        Remove-Item $ScriptFile -Force
    }
}
