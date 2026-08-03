# Stop every art-generation process and release the GPU.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools/stop_generation.ps1
#
# WHY THIS EXISTS. `pkill -f build_base_pool` from Git Bash does NOT reliably
# match these processes, and worse, `ps -W | grep -c` reports 0 for processes
# that are plainly running — so a "stopped" check passes while two runs
# continue in the background. That combination cost real time: a queue kept
# generating for hours after being "paused", competing for the GPU and dropping
# frames in-game. Match on the real command line via WMI instead.
#
# ComfyUI is included deliberately. Killing the generation scripts alone leaves
# it resident with a 7GB checkpoint in VRAM — the GPU stays busy and it looks
# like something is still generating, because effectively it is.

$patterns = 'build_base_pool|regen_monsters|regen_zone_floors|gen_equipment_sample|' +
            'build_pool|queue_all|ComfyUI\\main\.py|ComfyUI\\venv'

function Get-GenProcs {
    Get-CimInstance Win32_Process |
        # Only real generators. Restricting by process NAME first matters:
        # matching on command line alone also hits any powershell/cmd whose
        # arguments merely MENTION these tools — a monitor running a duplicate
        # check, or this script itself — which produced phantom "still alive"
        # warnings and made a clean stop look failed.
        Where-Object { $_.Name -in @('python.exe', 'pythonw.exe', 'bash.exe') } |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $patterns } |
        Where-Object { $_.ProcessId -ne $PID }
}

# ORDER IS LOAD-BEARING: the queue SHELL dies first.
#
# run_art_queue.sh runs its stages in sequence, so killing only the current
# child hands control back to the shell, which immediately starts the next
# stage — and that stage relaunches ComfyUI. Killing children in a loop looks
# like processes "respawning with new PIDs" and never converges. Kill the
# parent, then the children.
$shells = @(Get-GenProcs | Where-Object { $_.Name -eq 'bash.exe' })
foreach ($p in $shells) {
    Write-Output ("  killing queue shell {0}" -f $p.ProcessId)
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
if ($shells.Count -gt 0) { Start-Sleep -Seconds 3 }

$found = @(Get-GenProcs)
if ($found.Count -eq 0 -and $shells.Count -eq 0) {
    Write-Output "nothing generating"
} else {
    foreach ($p in $found) {
        $cmd = $p.CommandLine.Substring(0, [Math]::Min(80, $p.CommandLine.Length))
        Write-Output ("  killing {0}  {1}" -f $p.ProcessId, $cmd)
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 5
}

$left = @(Get-GenProcs)
if ($left.Count -gt 0) {
    Write-Output ("WARNING still alive: " + ($left.ProcessId -join ','))
} else {
    Write-Output "all generation stopped"
}

# Report the GPU so "stopped" can be verified rather than trusted.
$gpu = (nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader) -join ''
Write-Output "GPU after stop: $gpu"
Write-Output "(remaining usage is your own apps - games, Wallpaper Engine, browsers)"
