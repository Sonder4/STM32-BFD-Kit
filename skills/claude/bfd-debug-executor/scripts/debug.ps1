#Requires -Version 7.0
<#
.SYNOPSIS
    Debug Tool - J-Link 调试命令执行工具
.DESCRIPTION
    通过 SEGGER J-Link Commander 实现调试命令执行，支持断点设置、单步执行和寄存器查看。
.PARAMETER Command
    调试命令 (step/continue/regs/bl/reset/halt/go)
.PARAMETER Breakpoint
    断点位置 (main/file.c:line/*address)
.PARAMETER AfterHit
    断点后执行的命令
.PARAMETER Device
    设备型号，默认 STM32H723VGTx
.PARAMETER Speed
    调试速度 (kHz)，默认 4000
.PARAMETER JLinkPath
    J-Link 工具路径，默认 D:\STM32CubeCLT\Segger\JLink_V864a
.EXAMPLE
    .\debug.ps1 -Breakpoint "main" -AfterHit "regs"
.EXAMPLE
    .\debug.ps1 -Command "step"
.EXAMPLE
    .\debug.ps1 -Command "regs"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Command,

    [Parameter(Mandatory = $false)]
    [string]$Breakpoint,

    [Parameter(Mandatory = $false)]
    [string]$AfterHit,

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
$EXIT_COMMAND_ERROR = 2
$EXIT_BREAKPOINT_ERROR = 3

# J-Link Commander 路径
$JLinkCommand = Join-Path $JLinkPath "JLink.exe"

# 验证 J-Link 路径
if (-not (Test-Path $JLinkCommand)) {
    Write-Error "[ERROR] J-Link not found at: $JLinkCommand"
    Write-Host "Please check J-Link installation path."
    exit $EXIT_CONNECTION_ERROR
}

# 命令映射表
$CommandMap = @{
    "breakpoint" = "bs"
    "bp" = "bs"
    "step" = "step"
    "next" = "next"
    "continue" = "go"
    "regs" = "regs"
    "bl" = "bl"
    "reset" = "reset"
    "halt" = "halt"
    "go" = "go"
}

# 构建 J-Link 命令脚本
$JLinkCommands = @()
$JLinkCommands += "connect -device $Device -if SWD -speed $Speed"

# 处理断点
if ($Breakpoint) {
    Write-Host "Setting breakpoint at: $Breakpoint"
    $JLinkCommands += "bs $Breakpoint"

    # 如果有 AfterHit 命令，添加命令序列
    if ($AfterHit) {
        $AfterCommands = $AfterHit -split ';' | ForEach-Object { $_.Trim() }
        foreach ($Cmd in $AfterCommands) {
            if ($CommandMap.ContainsKey($Cmd)) {
                $JLinkCommands += $CommandMap[$Cmd]
            } else {
                $JLinkCommands += $Cmd
            }
        }
    }
}

# 处理直接命令
if ($Command) {
    if ($CommandMap.ContainsKey($Command)) {
        $JLinkCommands += $CommandMap[$Command]
    } else {
        $JLinkCommands += $Command
    }
}

# 添加退出命令
$JLinkCommands += "exit"

# 生成临时脚本文件
$ScriptFile = [System.IO.Path]::GetTempFileName()
$ScriptContent = $JLinkCommands -join "`n"

Write-Host "=== Debug Tool ==="
Write-Host "Device: $Device"
Write-Host "Speed: ${Speed}kHz"
if ($Breakpoint) { Write-Host "Breakpoint: $Breakpoint" }
if ($Command) { Write-Host "Command: $Command" }
if ($AfterHit) { Write-Host "After Hit: $AfterHit" }
Write-Host ""

try {
    Set-Content -Path $ScriptFile -Value $ScriptContent -Encoding UTF8

    Write-Host "Executing J-Link commands..."
    Write-Host "---"

    # 执行 J-Link Commander
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

    # 读取并显示输出
    $Output = $Process.StandardOutput.ReadToEnd()
    $ErrorOutput = $Process.StandardError.ReadToEnd()

    $Process.WaitForExit()

    # 显示输出
    Write-Host $Output

    if ($ErrorOutput) {
        Write-Host $ErrorOutput -ForegroundColor Red
    }

    # 检查退出码
    if ($Process.ExitCode -ne 0) {
        Write-Error "[ERROR] J-Link command failed with exit code: $($Process.ExitCode)"
        exit $EXIT_COMMAND_ERROR
    }

    Write-Host "---"
    Write-Host "=== Debug Tool Complete ===" -ForegroundColor Green
    exit $EXIT_SUCCESS

} catch {
    Write-Error "[ERROR] Debug command failed: $_"
    exit $EXIT_COMMAND_ERROR
} finally {
    # 清理临时文件
    if (Test-Path $ScriptFile) {
        Remove-Item $ScriptFile -Force
    }
}
