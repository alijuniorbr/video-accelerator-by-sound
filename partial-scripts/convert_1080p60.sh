#!/usr/bin/env bash

# Diretório alvo (se quiser processar a pasta atual, deixe só ".")
DIR="${1:-.}"

# Para cada arquivo .mov ou .mp4 dentro de $DIR
for f in "$DIR"/*.{mov,mp4}; do
  # Se não existir nenhum arquivo com essas extensões, sai
  [[ -e "$f" ]] || { echo "Nenhum .mov ou .mp4 em '$DIR'."; break; }

  # Nome base (sem extensão) e diretório
  filename="$(basename -- "$f")"
  base="${filename%.*}"
  dirpath="$(dirname -- "$f")"

  # Define saída com sufixo “-1080p60.mp4” no mesmo diretório
  output="${dirpath}/${base}-1080p60.mp4"

  echo "Convertendo '$f' → '$output'…"
  ffmpeg -i "$f" \
    -vf "scale=1920:1080" \
    -r 60 \
    -c:v libx264 \
    -preset medium \
    -crf 23 \
    -c:a aac \
    -b:a 128k \
    "$output"

  if [[ $? -ne 0 ]]; then
    echo "  ⚠️  Falha ao converter '$f'. Pulando."
  else
    echo "  ✓ Concluído: '$output'"
  fi
done

echo "Processamento finalizado."
