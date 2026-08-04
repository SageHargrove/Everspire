#!/usr/bin/env bash
# Everspire_Monsters_v2 LoRA training (2026-08-04).
#
# REPLACES the 2026-07-16 script, which predated the Everspire migration and
# was stale in three ways that would each have wasted a 2-hour run:
#   - output_name was "ToE_Monsters_v2", the RETIRED manhwa lineage
#   - --train_data_dir pointed at ../training_data, which no longer exists
#     (the dataset builds to chatgpt-lora/monsters/dataset/10_everspire_mon)
#   - 2500 steps was tuned for the 40-image set; the set is now 80
#
# WHY v2 AT ALL. v1 trained on 40 ChatGPT creatures spanning 13 body plans —
# about 3 examples per plan, against 34 per plan for heroes (one plan, 34
# images). That ~11x density gap is the best explanation for monster art
# lagging hero art: quadrupeds rendered bipedal, aberrants collapsed into
# generic demons, species features dropped. The Aug-04 top-up doubles the set
# to 80, roughly 6 per plan.
#
# NoobAI XL is a vpred model: --v_parameterization + --zero_terminal_snr are
# load-bearing, do not remove.
#
# STEPS. The dataset folder is "10_everspire_mon" = 10 repeats per image.
#   80 images x 10 repeats / batch 2 = 400 steps per epoch
#   4000 steps = 10 epochs
# v1 ran 12.5 epochs over half the data. Fewer epochs over more data is the
# right trade here: the risk with 80 images is overfitting onto the specific
# creatures, which shows up as the roster collapsing back onto these 80 instead
# of generalising to the 87 in ROSTER.md. --save_every_n_steps 500 keeps
# intermediates so an overcooked final can be rolled back to an earlier epoch
# without retraining.
set -e

DATASET="C:/Everspire/chatgpt-lora/monsters/dataset"
if [ ! -d "$DATASET/10_everspire_mon" ]; then
  echo "No dataset at $DATASET/10_everspire_mon"
  echo "Run: python C:/Everspire/chatgpt-lora/build_monster_dataset.py"
  exit 1
fi
echo "training on $(find "$DATASET" -name '*.png' | wc -l) images"

# sd-scripts prints Japanese status strings ("学習開始"). When stdout is a
# console that is fine, but redirected to a file Python picks cp1252 and the
# run dies with UnicodeEncodeError the moment training actually starts — after
# it has loaded the dataset, so it looks like a data problem and is not.
export PYTHONIOENCODING=utf-8

cd "C:/Everspire/sd-scripts"
venv/Scripts/python.exe sdxl_train_network.py \
  --pretrained_model_name_or_path "C:/Users/liamh/ComfyUI/models/checkpoints/noobaiXLNAIXL_vPred10Version.safetensors" \
  --v_parameterization --zero_terminal_snr \
  --train_data_dir "$DATASET" \
  --output_dir "C:/Users/liamh/ComfyUI/models/loras" \
  --output_name "Everspire_Monsters_v2" \
  --resolution 1024 --enable_bucket --min_bucket_reso 512 --max_bucket_reso 1536 \
  --network_module networks.lora --network_dim 32 --network_alpha 16 \
  --learning_rate 1e-4 --text_encoder_lr 5e-5 --lr_scheduler cosine --lr_warmup_steps 100 \
  --train_batch_size 2 --max_train_steps 4000 --save_every_n_steps 500 \
  --mixed_precision bf16 --save_precision bf16 --sdpa \
  --cache_latents --cache_latents_to_disk --gradient_checkpointing \
  --min_snr_gamma 5 --noise_offset 0.0357 \
  --optimizer_type AdamW8bit --max_data_loader_n_workers 2 \
  --caption_extension .txt --shuffle_caption --keep_tokens 1

echo
echo "Done. Everspire_Monsters_v2.safetensors is in ComfyUI/models/loras."
echo "NOT live yet — MONSTER_LORA in portrait_cache.py still names v1."
echo "A/B them before switching, and copy the winner into generation/loras/"
echo "or every player renders with the base model instead."
