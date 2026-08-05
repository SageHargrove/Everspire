#!/usr/bin/env bash
# Run every art-generation stage back to back.
#
#   bash tools/run_art_queue.sh
#   powershell -File tools/stop_generation.ps1     # to stop it, reliably
#
# SINGLE INSTANCE, enforced by lockfile. Two copies of this queue ended up
# running at once more than once, and the failure is quiet and expensive: they
# fight over one GPU, halve each other's throughput, interleave writes into the
# same staging dir, and the count keeps rising so nothing looks wrong. A stale
# lock from a killed run is detected and cleared rather than blocking forever.
#
# RESUMABLE: every stage skips files that already exist, so a killed run picks
# up where it stopped instead of redoing hours of work.
#
# COMFYUI IS SHUT DOWN AT THE END. It holds a 7GB checkpoint in VRAM, so
# leaving it resident after the queue finishes reads to the user as "something
# is still generating" — because for GPU purposes, it is.

set -uo pipefail          # deliberately not -e: one stage failing must not
                          # cancel the rest of the night's work

ROOT=/c/Everspire/tower-gacha
cd "$ROOT"
PY=./backend/venv/Scripts/python.exe
LOCK=/tmp/everspire_art_queue.lock

if [ -f "$LOCK" ]; then
    OLD=$(cat "$LOCK" 2>/dev/null || echo "")
    if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
        echo "REFUSING TO START: queue already running as PID $OLD"
        echo "Stop it first:  powershell -File tools/stop_generation.ps1"
        exit 1
    fi
    echo "clearing stale lock from PID ${OLD:-unknown}"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

stage () {
    echo
    echo "=============== $1 ==============="
    echo "started $(date '+%H:%M:%S')"
}

stage "1/4  HERO BASE POOL (176)"
$PY tools/build_base_pool.py 2>&1 | grep -viE "warn|^\[Cutout\]" | tail -25

stage "2/4  ZONE FLOORS (11)"
$PY tools/regen_zone_floors.py 2>&1 | grep -viE warn | tail -16

stage "3/4  MONSTERS (139)"
$PY tools/regen_monsters.py 2>&1 | grep -viE "warn|^\[Cutout\]" | tail -25

stage "4/4  EQUIPMENT SAMPLE (8)"
$PY tools/gen_equipment_sample.py 2>&1 | grep -viE warn | tail -12

echo
echo "releasing the GPU (shutting ComfyUI down)"
powershell -NoProfile -ExecutionPolicy Bypass -File tools/stop_generation.ps1 2>&1 | tail -4

echo
echo "=============== ALL QUEUED WORK DONE $(date '+%H:%M:%S') ==============="
