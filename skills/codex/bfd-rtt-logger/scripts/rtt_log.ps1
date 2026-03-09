#Requires -Version 7.0
<#
.SYNOPSIS
    RTT Logger - RTT 日志查看和采集工具
.DESCRIPTION
    通过 SEGGER J-Link RTT 功能实现实时日志查看和采集，支持 CSV 格式导出和时间戳记录。
.PARAMETER Duration
    采集时长（秒），默认 10 秒
.PARAMETER Output
    输出文件路径，默认 rtt_log.csv
.PARAMETER View
    仅查看不保存（Switch）
.PARAMETER Channel
    RTT 通道号（0-31），默认 0
.PARAMETER JLinkPath
    J-Link 工具路径，默认 D:\STM32CubeCLT\Segger\JLink_V864a
.EXAMPLE
    .\rtt_log.ps1 -Duration 10 -Output rtt_log.csv
.EXAMPLE
    .\rtt_log.ps1 -View -Duration 5
.EXAMPLE
    .\rtt_log.ps1 -Channel 0 -Duration 10
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [int]$Duration = 10,

    [Parameter(Mandatory = $false)]
    [string]$Output = "rtt_log.csv",

    [Parameter(Mandatory = $false)]
    [switch]$View,

    [Parameter(Mandatory = $false)]
    [int]$Channel = 0,

    [Parameter(Mandatory = $false)]
    [string]$JLinkPath = "D:\STM32CubeCLT\Segger\JLink_V864a"
)

# 错误码定义
$EXIT_SUCCESS = 0
$EXIT_CONNECTION_ERROR = 1
$EXIT_INVALID_CHANNEL = 2
$EXIT_FILE_WRITE_ERROR = 3

# J-Link  Commander 命令
$JLinkCommand = Join-Path $JLinkPath "JLink.exe"

# 验证 J-Link 路径
if (-not (Test-Path $JLinkCommand)) {
    Write-Error "[ERROR] J-Link not found at: $JLinkCommand"
    Write-Host "Please check J-Link installation path."
    exit $EXIT_CONNECTION_ERROR
}

# 验证通道号
if ($Channel -lt 0 -or $Channel -gt 31) {
    Write-Error "[ERROR] Invalid channel: $Channel. Must be 0-31."
    exit $EXIT_INVALID_CHANNEL
}

Write-Host "=== RTT Logger ==="
Write-Host "Device: STM32H723VGTx"
Write-Host "Channel: $Channel"
Write-Host "Duration: ${Duration}s"
Write-Host "Output: $Output"
Write-Host ""

# 生成 J-Link Commander 脚本
$ScriptFile = [System.IO.Path]::GetTempFileName()
$ScriptContent = @"
connect -device STM32H723VGTx -if SWD -speed 4000
rtt
rtt set terminal $Channel
rtt start
log
"@

try {
    Set-Content -Path $ScriptFile -Value $ScriptContent -Encoding UTF8

    # 执行 J-Link Commander 并捕获输出
    $StartTime = Get-Date
    $EndTime = $StartTime.AddSeconds($Duration)
    $LogEntries = @()

    Write-Host "Starting RTT capture..."

    # 使用 Start-Process 捕获输出
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

    # 读取输出直到超时
    while ((Get-Date) -lt $EndTime) {
        $Line = $Process.StandardOutput.ReadLine()
        if ($Line) {
            $Timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffzzz"

            # 解析日志级别
            $Level = "INFO"
            if ($Line -match "\[ERROR\]") { $Level = "ERROR" }
            elseif ($Line -match "\[WARNING\]") { $Level = "WARNING" }
            elseif ($Line -match "E:") { $Level = "ERROR" }
            elseif ($Line -match "W:") { $Level = "WARNING" }
            elseif ($Line -match "I:") { $Level = "INFO" }

            # 清理消息
            $Message = $Line -replace '^[IWE]:\s*', ''
            $Message = $Message -replace '"', '""'

            $LogEntry = [PSCustomObject]@{
                Timestamp = $Timestamp
                Level = $Level
                Message = $Message
            }
            $LogEntries += $LogEntry

            if ($View) {
                switch ($Level) {
                    "ERROR" { Write-Host $Line -ForegroundColor Red }
                    "WARNING" { Write-Host $Line -ForegroundColor Yellow }
                    "INFO" { Write-Host $Line -ForegroundColor Green }
                    default { Write-Host $Line }
                }
            }
        }
        Start-Sleep -Milliseconds 100
    }

    $Process.Kill()
    $Process.WaitForExit()

    # 保存到 CSV
    if (-not $View) {
        Write-Host ""
        Write-Host "Saving to CSV..."

        $CsvContent = @"
# Device: STM32H723VGTx
# Channel: $Channel
# Capture Start: $($StartTime.ToString("yyyy-MM-ddTHH:mm:ss.fffzzz"))
# Capture End: $((Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffzzz"))
# Duration: ${Duration}s
#
timestamp,level,message
"@

        foreach ($Entry in $LogEntries) {
            $CsvContent += "`"$($Entry.Timestamp)`",$($Entry.Level),`"$($Entry.Message)`"`n"
        }

        try {
            [System.IO.File]::WriteAllText(
                [System.IO.Path]::GetFullPath($Output),
                $CsvContent,
                [System.Text.Encoding]::UTF8
            )
            Write-Host "Saved $($LogEntries.Count) log entries to: $Output" -ForegroundColor Green
        } catch {
            Write-Error "[ERROR] Failed to write file: $_"
            exit $EXIT_FILE_WRITE_ERROR
        }
    }

    Write-Host ""
    Write-Host "=== RTT Logger Complete ===" -ForegroundColor Green
    Write-Host "Total entries: $($LogEntries.Count)"
    exit $EXIT_SUCCESS

} catch {
    Write-Error "[ERROR] RTT capture failed: $_"
    exit $EXIT_CONNECTION_ERROR
} finally {
    # 清理临时文件
    if (Test-Path $ScriptFile) {
        Remove-Item $ScriptFile -Force
    }
}
