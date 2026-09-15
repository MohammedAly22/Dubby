#!/usr/bin/env bash
# Dubby 🐨 setup (Linux / macOS)
#   ./scripts/setup.sh                    core env only
#   ./scripts/setup.sh --qwen             + Qwen3-ASR / QwenCleo-ASR / Qwen3-TTS env
#   ./scripts/setup.sh --nemo             + NVIDIA Parakeet env
#   ./scripts/setup.sh --indic            + IndicTrans2 / IndicF5 (Hindi) env
#   ./scripts/setup.sh --cpu              CPU-only PyTorch wheels
set -euo pipefail
cd "$(dirname "$0")/.."

QWEN=0; NEMO=0; INDIC=0; CPU=0
for arg in "$@"; do
  case "$arg" in
    --qwen) QWEN=1 ;;
    --nemo) NEMO=1 ;;
    --indic) INDIC=1 ;;
    --cpu) CPU=1 ;;
  esac
done

say() { printf "\n\033[1;97m🐨 %s\033[0m\n" "$*"; }

command -v conda >/dev/null || { echo "conda not found — install Miniconda first"; exit 1; }

create_env() {  # $1 = yml, $2 = env name
  local yml="$1"
  if [ "$CPU" = 1 ]; then
    sed 's#whl/cu128#whl/cpu#' "$yml" > ".${yml}.cpu.yml"; yml=".${yml}.cpu.yml"
  fi
  if conda env list | grep -qE "^$2\s"; then
    say "Updating env $2"; conda env update -n "$2" -f "$yml" --prune
  else
    say "Creating env $2"; conda env create -f "$yml"
  fi
}

create_env environment.yml dubby
if [ "$QWEN" = 1 ]; then
  create_env environment-qwen.yml dubby-qwen
  conda run -n dubby-qwen pip install qwencleo-asr --no-deps
  conda run -n dubby-qwen pip install qwen-tts --no-deps
  conda run -n dubby-qwen pip install onnxruntime einops sox
fi
[ "$NEMO" = 1 ] && create_env environment-nemo.yml dubby-nemo
if [ "$INDIC" = 1 ]; then
  create_env environment-indic.yml dubby-indic
  conda run -n dubby-indic pip install "git+https://github.com/ai4bharat/IndicF5.git" "transformers<4.50"
fi

say "Building the web UI"
conda run -n dubby --no-capture-output dubby build-ui

say "Checking engines"
conda run -n dubby --no-capture-output dubby doctor

say "Done! Start the studio with:  conda activate dubby && dubby serve"
