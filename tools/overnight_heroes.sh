#!/usr/bin/env bash
# Stage 2 of the overnight run: regenerate the hero base pool on Heroes_v2.
#
# SEPARATE FILE, not an edit to overnight_retrain.sh, because that script is
# already running. Bash reads a script by byte offset as it executes, so editing
# a live one makes it resume at the wrong place in the new text - silent and
# very hard to diagnose.
#
# Waits for Heroes_v2 to exist AND for training to have exited, then rebuilds
# the pool. The old pool is archived rather than deleted: if v2 turns out worse
# than v1 there is no way back otherwise, and 264 images is ~2h of GPU.
set -u

LOG="C:/Everspire/_overnight"
LORAS="C:/Users/liamh/ComfyUI/models/loras"
GAME="C:/Everspire/tower-gacha"
POOL="$GAME/backend/static/portraits/cutouts_heroes"
say() { echo "[$(date +%H:%M:%S)] $*"; }

say "waiting for Everspire_Heroes_v2 + training to finish..."
for i in $(seq 1 720); do            # 720 x 30s = 6h ceiling
  if [ -f "$LORAS/Everspire_Heroes_v2.safetensors" ] \
     && ! (ps -W 2>/dev/null | grep -q sdxl_train_network) \
     && ! (powershell -NoProfile -Command \
            "if (Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'sdxl_train_network' }) { exit 0 } else { exit 1 }" 2>/dev/null); then
    say "Heroes_v2 ready and training finished"
    break
  fi
  sleep 30
done

if [ ! -f "$LORAS/Everspire_Heroes_v2.safetensors" ]; then
  say "ABORT - Heroes_v2 never appeared. Pool left untouched."
  exit 1
fi

# Let the enemy regeneration in stage 1 finish first; two ComfyUI clients
# queueing at once just thrash VRAM.
for i in $(seq 1 240); do
  powershell -NoProfile -Command \
    "if (Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'gen_missing_enemies' }) { exit 0 } else { exit 1 }" 2>/dev/null \
    || break
  sleep 30
done
say "enemy regen clear - starting hero pool"

if [ -d "$POOL" ]; then
  ARCH="$GAME/backend/static/portraits/_pool_v1_archive"
  rm -rf "$ARCH"; mv "$POOL" "$ARCH"
  say "archived old pool -> _pool_v1_archive ($(find "$ARCH" -name '*.png' | wc -l) files)"
fi

cd "$GAME" || exit 1
COMFY_LORA_HERO="Everspire_Heroes_v2.safetensors:0.75,AddMicroDetails_NoobAI_v5.safetensors:0.3" \
  python tools/build_base_pool.py --variants 2 >> "$LOG/pool.log" 2>&1
RC=$?

say "pool build exit=$RC, $(find "$GAME/backend/static/portraits/_base_pool_staging" -name '*.png' 2>/dev/null | wc -l) staged"
say "NOT adopted automatically - review the staging folder, then copy into"
say "cutouts_heroes/ to make it live. Old pool is in _pool_v1_archive."
say "=== HEROES DONE ==="
