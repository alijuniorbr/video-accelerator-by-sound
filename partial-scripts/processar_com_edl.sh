#!/usr/bin/env bash

VIDEO="video-teste-unfrag.mp4"
EDL_JSON="video-teste-unfrag.edl.combined.json"
TMPDIR="tmp_segments"
LIST="$TMPDIR/list.txt"

mkdir -p "$TMPDIR"
rm -f "$TMPDIR"/segment-* "$LIST"

index=0
for seg in $(jq -c '.[]' "$EDL_JSON"); do
  fr_start=$(echo "$seg" | jq -r '.start')
  fr_end=$(echo "$seg"   | jq -r '.end')
  typ=$(echo "$seg"      | jq -r '.type')

  start=$(echo "scale=6; $fr_start/60" | bc -l)
  end=$(echo "scale=6; $fr_end/60"   | bc -l)
  duration=$(echo "scale=6; $end - $start" | bc -l)

  if [[ "$typ" == "inactive" ]]; then
    continue
  fi

  #out="$TMPDIR/segment-${index}.mp4"
  out="$TMPDIR/segment-$(printf "%06d" "$index").mp4"

  if [[ "$typ" == "speech" ]]; then
    ffmpeg -y \
      -ss "$start" -i "$VIDEO" \
      -t "$duration" \
      -c:v copy -c:a copy \
      "$out" \
      &>/dev/null

  elif [[ "$typ" == "code" ]]; then
    ffmpeg -y \
      -ss "$start" -i "$VIDEO" \
      -t "$duration" \
      -filter_complex "\
        [0:v]trim=start=${start}:end=${end}, setpts=PTS/8 [v]; \
        [0:a]atrim=start=${start}:end=${end}, asetpts=PTS/1, atempo=2,atempo=2,atempo=2 [a]" \
      -map "[v]" -map "[a]" \
      -c:v libx264 -crf 23 -preset medium \
      -c:a aac -b:a 128k \
      "$out" \
      &>/dev/null
  fi

  if [[ -s "$out" ]]; then
    echo "file '$PWD/$out'" >> "$LIST"
    ((index++))
  else
    rm -f "$out"
  fi
done

if [[ ! -s "$LIST" ]]; then
  echo "Nenhum segmento válido foi criado. Verifique seu EDL e o vídeo original."
  exit 1
fi

# ffmpeg -y \
#   -f concat -safe 0 \
#   -i "$LIST" \
#   -c copy \
#   "video-teste-final.mp4"

ffmpeg -y \
  -f concat -safe 0 \
  -i "$LIST" \
  -c:v libx264 -crf 23 -preset medium \
  -c:a aac -b:a 128k \
  "video-teste-final.mp4"


echo "▶ Vídeo final gerado: video-teste-final.mp4"
