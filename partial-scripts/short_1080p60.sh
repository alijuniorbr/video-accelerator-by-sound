#!/usr/bin/env bash

# auto-editor   meu_video.mp4   -s 8   -v 1    --cut-out  -o meu_video_processado.mp4

# Se for passado um diretório como primeiro argumento, use-o; caso contrário, use o diretório atual.
DIR="${1:-.}"

# Verifica se o diretório existe
if [[ ! -d "$DIR" ]]; then
  echo "Erro: '$DIR' não é um diretório válido."
  exit 1
fi

# Itera sobre todos os arquivos .mp4 dentro de $DIR
for f in "$DIR"/*.go.mp4; do
  # Verifica se realmente existe algum arquivo (para o caso de não haver .mp4)
  [[ -e "$f" ]] || { echo "Nenhum arquivo .mp4 encontrado em '$DIR'."; break; }

  # Extrai o nome base (sem extensão) e a pasta de cada arquivo
  filename="$(basename -- "$f")"          # exemplo: meu_video.mp4
  base="${filename%.*}"                    # exemplo: meu_video
  dirpath="$(dirname -- "$f")"             # caminho até a pasta, ex: /Users/fulano/Vídeos

  # Define o nome de saída: <base>-processado.mp4 (na mesma pasta do original)
  output="${dirpath}/${base}-processado.mp4"

  echo "Processando '$f' → '$output' …"
  auto-editor "$f" -s 8 -v 1 --cut-out -o "$output"

  # Testa se o comando teve sucesso
  if [[ $? -ne 0 ]]; then
    echo "  ⚠️  Falha ao processar '$f'. Pulando para o próximo."
  else
    echo "  ✓ Concluído: '$output'"
  fi
done

echo "Fim do processamento."
