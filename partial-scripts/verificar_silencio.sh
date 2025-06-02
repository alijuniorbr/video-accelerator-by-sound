#!/usr/bin/env bash

INDIR="speech_segments"
OUT_SOM="speech_com_som"
OUT_SILENCIO="speech_silencioso"
LIMIAR_DB=-30.0   # quem tiver max_volume < LIMIAR_DB dB será considerado silêncio

mkdir -p "$OUT_SOM" "$OUT_SILENCIO"

echo "Iniciando verificação de silêncio em cada arquivo de $INDIR ..."
for f in "$INDIR"/segment-*.mp4; do
  # Extrai o campo max_volume do log do FFmpeg (em dB)
  max_vol=$(ffmpeg -hide_banner -i "$f" -af "volumedetect" -f null /dev/null 2>&1 \
    | grep "max_volume" \
    | awk '{print $5}' \
    | sed 's/dB//')

  # Se não conseguiu extrair nada, marca como silêncio por precaução
  if [[ -z "$max_vol" ]]; then
    echo "[AVISO] Não foi possível detectar volume em '$f' → movendo para $OUT_SILENCIO"
    mv "$f" "$OUT_SILENCIO/"
    continue
  fi

  # Compara numericamento (usa bc para floats)
  is_silencio=$(echo "$max_vol < $LIMIAR_DB" | bc -l)
  if [[ "$is_silencio" -eq 1 ]]; then
    echo "[SILÊNCIO] '$f'  (max_volume=${max_vol} dB ≤ ${LIMIAR_DB} dB)"
    mv "$f" "$OUT_SILENCIO/"
  else
    echo "[COM SOM] '$f'  (max_volume=${max_vol} dB)"
    mv "$f" "$OUT_SOM/"
  fi
done

echo "Verificação finalizada."
echo "  → Segmentos com som estão em:    $OUT_SOM/"
echo "  → Segmentos silenciosos estão em: $OUT_SILENCIO/"
