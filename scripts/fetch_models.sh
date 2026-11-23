#!/usr/bin/env bash
# Descarrega os modelos locais necessários à escuta por voz (não vão para o Git).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/data/models"
mkdir -p "$DEST"
if [ ! -s "$DEST/silero_vad.onnx" ]; then
  echo "A descarregar Silero VAD..."
  curl -fsSL -o "$DEST/silero_vad.onnx" \
    "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx"
fi
echo "Modelos prontos em $DEST"
