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
        Where-Object { $_.CommandLine -and $_.CommandLine -match $patterns } |
        # Never match this script's own PowerShell host — its command line
        # contains the pattern string, so an unfiltered kill suicides and
        # reports a false failure.
        Where-Object { $_.ProcessId -ne $PID }
}

$found = @(Get-GenProcs)
if ($found.Count -eq 0) {
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
