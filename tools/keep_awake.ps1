# Keep this machine awake while a long job runs, then let it sleep again.
#
# ASCII ONLY IN THIS FILE. Windows PowerShell 5.1 reads a BOM-less script as
# ANSI, so a UTF-8 em-dash or arrow in a COMMENT becomes stray bytes and the
# parser fails with "string is missing the terminator" pointing at an innocent
# line far below. Cost an hour once; keep it plain.
#
# WHY NOT powercfg. Editing the sleep timeout is a persistent machine change
# that must be remembered and reverted; if the run crashes the setting silently
# stays altered. SetThreadExecutionState is the documented API for this (what
# media players use) and the request dies with THIS process, so a crash cannot
# leave the machine unable to sleep.
#
# ES_SYSTEM_REQUIRED only, NOT ES_DISPLAY_REQUIRED. The system stays awake so
# training keeps running, but the monitor is still free to switch off. Holding
# a display on overnight for a job nobody is watching wastes power and risks
# burn-in on an OLED.
#
#   powershell -File tools/keep_awake.ps1 -MatchPattern "sdxl_train_network"
#
# Exits on its own once no process matches, so it never outlives the job.

param(
    [string]$MatchPattern = "sdxl_train_network",
    [int]$PollSeconds = 60,
    [int]$MaxHours = 12,
    # Consecutive misses before releasing. An unattended chain (train -> train
    # -> generate) has gaps of a minute or two between stages where no matching
    # process exists; exiting on the first miss would hand sleep back mid-chain
    # and strand the rest of the run.
    [int]$GraceChecks = 10
)

# Passed as a variable, not a here-string: PS 5.1 misparses the @'...'@ form
# here and blames a brace forty lines below.
$sig = '[DllImport("kernel32.dll", SetLastError=true)] public static extern uint SetThreadExecutionState(uint esFlags);'
Add-Type -Name Power -Namespace Win32 -MemberDefinition $sig -ErrorAction SilentlyContinue

# Decimal, NOT 0x80000000. PowerShell parses that literal as a signed Int32
# (-2147483648) BEFORE the [uint32] cast, so the cast throws, the flag is never
# applied, and the script looks like it worked while the machine still sleeps.
$ES_CONTINUOUS      = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]1

function Test-JobRunning {
    $p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
         Where-Object { $_.CommandLine -and $_.CommandLine -match $MatchPattern }
    return [bool]$p
}

function Stamp {
    return (Get-Date).ToString("HH:mm:ss")
}

if (-not (Test-JobRunning)) {
    Write-Output "No process matching '$MatchPattern' is running. Nothing to keep awake."
    exit 1
}

# ES_CONTINUOUS makes the request persist until cleared, rather than a one-shot
# nudge that would have to be re-sent on a timer.
$prev = [Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
if ($prev -eq 0) {
    Write-Output "WARNING: SetThreadExecutionState failed. Sleep is NOT suppressed."
    exit 1
}
$t = Stamp
Write-Output "$t  Sleep suppressed while '$MatchPattern' runs. Display may still turn off."

$deadline = (Get-Date).AddHours($MaxHours)
$done = $false
$misses = 0
try {
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds $PollSeconds
        if (Test-JobRunning) {
            $misses = 0
        } else {
            $misses++
            if ($misses -ge $GraceChecks) {
                $t = Stamp
                Write-Output "$t  No matching process for $GraceChecks checks. Releasing."
                $done = $true
                break
            }
        }
    }
    if (-not $done) {
        $t = Stamp
        Write-Output "$t  Hit the $MaxHours hour safety limit. Releasing while the job may still be running."
    }
}
finally {
    # ES_CONTINUOUS alone clears the request. In finally so Ctrl-C or a kill
    # still hands sleep back instead of pinning the machine awake.
    [void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)
    $t = Stamp
    Write-Output "$t  Sleep restored to normal."
}
