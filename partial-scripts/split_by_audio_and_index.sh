#!/usr/bin/env bash
set -euo pipefail

#############################################
# split_by_audio_and_index.sh (corte preciso + correção de timestamps)
#
# Descrição:
#   - Detecta silêncios com silencedetect (–30dB, min 0.5s).
#   - Ordena numericamente todos os intervalos de silêncio.
#   - Intercala “speech” / “silent” para criar segmentos.
#   - Corta usando “-i <input> -ss <start> -t <dur>” + flags:
#       -fflags +genpts -avoid_negative_ts make_zero
#     para forçar geração correta de PTS/DTS e evitar pedaços em preto.
#   - Cria JSON (“sound_index.json”) com metadados de cada clipe:
#       index, file, frame_start, frame_end, time_start, time_end, fps,
#       db_min, db_max, result (“speech” ou “silent”).
#
# Uso: ./split_by_audio_and_index.sh video.mp4
#############################################

if [[ $# -ne 1 ]]; then
  echo "Uso: $0 <arquivo.mp4>"
  exit 1
fi

VIDEO="$1"
OUTDIR="audio_segments"
TMP_LOG="silence_detect.log"
INDEX_JSON="sound_index.json"

# 1) Limpar saídas antigas
mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/segment-*.mp4 "$TMP_LOG" "$INDEX_JSON"

# 2) Detectar silêncios: abaixo de –30dB por pelo menos 0.5s
LIMIAR="-30dB"
MIN_SIL_DUR="0.5"

echo "→ Detectando silêncios em '$VIDEO' (limiar=$LIMIAR, min_dur=${MIN_SIL_DUR}s)..."
ffmpeg -hide_banner -nostats -i "$VIDEO" \
  -af "silencedetect=noise=$LIMIAR:d=$MIN_SIL_DUR" \
  -f null /dev/null 2> "$TMP_LOG"


# 3) Extrair pares “silence_start: X” e “silence_end: Y”
declare -a SIL_INTERVALS=()
cur_sil_start=""

while read -r line; do
  if [[ $line =~ silence_start:\ ([0-9]+\.[0-9]+) ]]; then
    cur_sil_start="${BASH_REMATCH[1]}"
  elif [[ $line =~ silence_end:\ ([0-9]+\.[0-9]+) ]]; then
    end_time="${BASH_REMATCH[1]}"
    if [[ -z "$cur_sil_start" ]]; then
      # silêncio começou em 0
      SIL_INTERVALS+=( "0.000000:$end_time" )
    else
      SIL_INTERVALS+=( "$cur_sil_start:$end_time" )
    fi
    cur_sil_start=""
  fi
done < <(grep -E "silence_start|silence_end" "$TMP_LOG")

# 4) Se terminou com “silence_start” sem “silence_end”, fecha até o fim
VIDEO_DUR=$(ffprobe -v error -show_entries format=duration \
  -of default=nokey=1:noprint_wrappers=1 "$VIDEO")
if [[ -n "$cur_sil_start" ]]; then
  SIL_INTERVALS+=( "$cur_sil_start:$VIDEO_DUR" )
fi

# 5) Se nenhum silêncio, todo o vídeo será “speech”
if (( ${#SIL_INTERVALS[@]} == 0 )); then
  echo "→ Nenhum silêncio detectado → todo o arquivo será segmentado como 'speech'."
fi

# 6) Ordenar numericamente pelos “start” (campo antes dos “:”), usando float
IFS=$'\n' sorted=($(printf '%s\n' "${SIL_INTERVALS[@]}" | sort -t ':' -k1,1g))
unset IFS
SIL_INTERVALS=("${sorted[@]}")

echo "→ Silences detectados (em ordem numérica):"
for interval in "${SIL_INTERVALS[@]}"; do
  echo "   $interval"
done

# 7) Intercala “speech” / “silent”
declare -a SEG_START=()
declare -a SEG_END=()
declare -a SEG_TYPE=()

prev="0.000000"
for interval in "${SIL_INTERVALS[@]}"; do
  IFS=":" read -r sstart send <<< "$interval"
  unset IFS

  # se houver fala antes deste silêncio
  if (( $(bc -l <<< "$sstart > $prev") )); then
    SEG_START+=( "$prev" )
    SEG_END+=(   "$sstart" )
    SEG_TYPE+=(  "speech" )
  fi

  # em seguida, este silêncio
  SEG_START+=( "$sstart" )
  SEG_END+=(   "$send" )
  SEG_TYPE+=(  "silent" )

  prev="$send"
done

# se sobrar fala após o último silêncio
if (( $(bc -l <<< "$VIDEO_DUR > $prev") )); then
  SEG_START+=( "$prev" )
  SEG_END+=(   "$VIDEO_DUR" )
  SEG_TYPE+=(  "speech" )
fi

# se não houve silêncios, cria um único speech
if (( ${#SIL_INTERVALS[@]} == 0 )); then
  SEG_START=( "0.000000" )
  SEG_END=(   "$VIDEO_DUR" )
  SEG_TYPE=(  "speech" )
fi

total_segments=${#SEG_START[@]}
echo "→ Total de segmentos calculados: $total_segments"

# 8) Extrair FPS “3 casas decimais”
FPS_RAW=$(ffprobe -v error -select_streams v:0 \
  -show_entries stream=avg_frame_rate -of default=nokey=1:noprint_wrappers=1 "$VIDEO")
IFS='/' read -r FR_NUM FR_DEN <<< "$FPS_RAW"
FPS=$(bc -l <<< "scale=3; $FR_NUM / $FR_DEN")
unset IFS
echo "→ FPS (3 casas): $FPS"

# 9) Agora corta CADA segment(o), mesmo que comece em non-keyframe
echo "[" >> "$INDEX_JSON"
file_idx=0

for ((i=0; i<total_segments; i++)); do
  start="${SEG_START[i]}"
  end="${SEG_END[i]}"
  typ="${SEG_TYPE[i]}"

  # (a) duração exata em 6 casas
  dur=$(bc -l <<< "scale=6; $end - $start")
  if (( $(bc -l <<< "$dur <= 0") )); then
    continue
  fi

  pad=$(printf "%06d" "$file_idx")
  filename="${pad}_${typ}.mp4"
  out="$OUTDIR/$filename"

  # (b) cortar com geração correta de PTS/DTS
  ffmpeg -y \
    -i "$VIDEO" \
    -ss "$start" \
    -t "$dur" \
    -fflags +genpts -avoid_negative_ts make_zero \
    -c:v copy -c:a copy \
    "$out" \
    &>/dev/null

  # (c) converter tempo→quadro (descarta decimal)
  frame_start=$(bc <<< "($start * $FPS)/1")
  frame_end=$(bc   <<< "($end   * $FPS)/1")

  # (d) extrair db_min e db_max
  vd_log=$(mktemp)
  ffmpeg -hide_banner -nostats -i "$out" \
    -af "volumedetect" -f null /dev/null 2> "$vd_log"
  db_min=$(grep "mean_volume" "$vd_log" | awk '{print $5}')
  db_max=$(grep "max_volume"  "$vd_log" | awk '{print $5}')
  rm -f "$vd_log"

  # (e) preencher JSON (com vírgula se não for o primeiro)
  if [[ $file_idx -eq 0 ]]; then
    comma=""
  else
    comma=","
  fi

  cat >> "$INDEX_JSON" <<EOF
  ${comma}{
    "index":       $file_idx,
    "file":        "$filename",
    "frame_start": $frame_start,
    "frame_end":   $frame_end,
    "time_start":  "$start",
    "time_end":    "$end",
    "fps":         "$FPS",
    "db_min":      "$db_min",
    "db_max":      "$db_max",
    "result":      "$typ"
  }
EOF

  ((file_idx++))
done

echo "]" >> "$INDEX_JSON"

echo "→ Segmentos gerados em '$OUTDIR/' (total: $file_idx arquivos)"
echo "→ Índice JSON salvo em '$INDEX_JSON'"
