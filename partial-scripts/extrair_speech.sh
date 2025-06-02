#!/usr/bin/env bash

# 1) Vídeo “unfrag” gerado pelo FFmpeg
VIDEO="video-teste-unfrag.mp4"

# 2) EDL de áudio (lista em ["a"][0])
EDL_AUDIO="video-teste-unfrag.edl.audio.json"

# 3) Pasta de saída
OUTDIR="speech_segments"
mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/segment-*.mp4

index=0
# Itera sobre cada objeto em a[0]
for seg in $(jq -c '.a[0][]' "$EDL_AUDIO"); do
  fr_start=$(echo "$seg" | jq -r '.start')
  fr_dur=$(echo "$seg"   | jq -r '.dur')

  # Converte frames → segundos (timebase 60)
  start=$(echo "scale=6; $fr_start/60" | bc -l)
  duration=$(echo "scale=6; $fr_dur/60"   | bc -l)

  out="$OUTDIR/segment-${index}.mp4"
  ffmpeg -y \
    -ss "$start" -i "$VIDEO" \
    -t "$duration" \
    -c:v copy -c:a copy \
    "$out" \
    &>/dev/null

  if [[ -s "$out" ]]; then
    ((index++))
  else
    rm -f "$out"
  fi
done

echo "▶ Trechos de fala extraídos em: $OUTDIR (total de $index arquivos)"
