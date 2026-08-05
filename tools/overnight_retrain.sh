#!/usr/bin/env bash
# Unattended: build both magenta datasets, train both LoRAs, regenerate all art.
#
# Runs start-to-finish with nobody watching, so every step is guarded and the
# log is the only record. Order matters: monsters train first because their
# fix (magenta cutout) is the one that unblocked this whole pass, so if the
# machine dies overnight the more valuable half is already done.
#
# Sleep is suppressed by tools/keep_awake.ps1, launched separately and watching
# for sdxl_train_network. It releases itself when training ends - which is why
# the GENERATION stage runs while training is still nominally "the" job: the
# python process for generation is not what keep_awake tracks. Launch keep_awake
# against THIS script's pid instead if that ever matters.
#
#   bash tools/overnight_retrain.sh
set -u

LOG_DIR="$(dirname "$0")/../../_overnight"
mkdir -p "$LOG_DIR"
CL="C:/Everspire/chatgpt-lora"
SD="C:/Everspire/sd-scripts"
LORAS="C:/Users/liamh/ComfyUI/models/loras"
export PYTHONIOENCODING=utf-8   # sd-scripts prints Japanese; cp1252 kills the run

say() { echo "[$(date +%H:%M:%S)] $*"; }

train() {   # $1=set  $2=output_name  $3=tag  $4=steps
  local set=$1 out=$2 tag=$3 steps=$4
  local data="$CL/$set/dataset_magenta"
  if [ ! -d "$data/10_$tag" ]; then say "SKIP $out - no dataset at $data"; return 1; fi
  local n; n=$(find "$data" -name '*.png' | wc -l)
  say "training $out on $n images, $steps steps"
  ( cd "$SD" && venv/Scripts/python.exe sdxl_train_network.py \
      --pretrained_model_name_or_path "$LORAS/../checkpoints/noobaiXLNAIXL_vPred10Version.safetensors" \
      --v_parameterization --zero_terminal_snr \
      --train_data_dir "$data" --output_dir "$LORAS" --output_name "$out" \
      --resolution 1024 --enable_bucket --min_bucket_reso 512 --max_bucket_reso 1536 \
      --network_module networks.lora --network_dim 32 --network_alpha 16 \
      --learning_rate 1e-4 --text_encoder_lr 5e-5 --lr_scheduler cosine --lr_warmup_steps 100 \
      --train_batch_size 2 --max_train_steps "$steps" --save_every_n_steps 500 \
      --mixed_precision bf16 --save_precision bf16 --sdpa \
      --cache_latents --cache_latents_to_disk --gradient_checkpointing \
      --min_snr_gamma 5 --noise_offset 0.0357 \
      --optimizer_type AdamW8bit --max_data_loader_n_workers 2 \
      --caption_extension .txt --shuffle_caption --keep_tokens 1 ) \
    >> "$LOG_DIR/$out.log" 2>&1
  if [ -f "$LORAS/$out.safetensors" ]; then say "OK $out"; return 0; fi
  say "FAILED $out - see $LOG_DIR/$out.log"; return 1
}

say "=== build datasets ==="
python "$CL/build_magenta_dataset.py" monsters 2>&1 | tee -a "$LOG_DIR/build.log"
python "$CL/build_magenta_dataset.py" heroes   2>&1 | tee -a "$LOG_DIR/build.log"

# 80 imgs x 10 repeats / batch 2 = 400 steps/epoch -> 4000 = 10 epochs
# 70 imgs x 10 repeats / batch 2 = 350 steps/epoch -> 3500 = 10 epochs
say "=== train monsters ==="
train monsters Everspire_Monsters_v3 everspire_mon 4000
MON=$?
say "=== train heroes ==="
train heroes  Everspire_Heroes_v2   everspire_hero 3500
HER=$?

say "=== ship whichever trained ==="
GEN="C:/Everspire/tower-gacha/generation/loras"
[ $MON -eq 0 ] && cp "$LORAS/Everspire_Monsters_v3.safetensors" "$GEN/" && say "shipped monsters v3"
[ $HER -eq 0 ] && cp "$LORAS/Everspire_Heroes_v2.safetensors"   "$GEN/" && say "shipped heroes v2"

say "=== regenerate art ==="
if [ $MON -eq 0 ]; then
  ( cd "C:/Everspire/tower-gacha" && \
    COMFY_LORA_MONSTER="Everspire_Monsters_v3.safetensors:0.75,AddMicroDetails_NoobAI_v5.safetensors:0.3" \
    python tools/gen_missing_enemies.py ) >> "$LOG_DIR/gen_enemies.log" 2>&1
  say "enemy regen done ($(find C:/Everspire/tower-gacha/backend/static/portraits/enemies -name '*.png' | wc -l) files)"
else
  say "skipped enemy regen - monster training failed"
fi

say "=== ALL DONE ==="
say "monsters=$MON heroes=$HER  (0 = ok)"
say "NOT switched live: MONSTER_LORA/HERO_LORA in portrait_cache.py still name the old versions."
say "A/B first:  python tools/ab_monster_lora.py --a Everspire_Monsters_v2.safetensors --b Everspire_Monsters_v3.safetensors"
