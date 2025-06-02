#!/usr/bin/env bash

echo "Unfrag (MOV → MP4)"
ffmpeg -i "video-teste.mov" -c:v copy -c:a copy -movflags +faststart "video-teste-unfrag.mp4"

echo "Extrair áudio"
ffmpeg -i "video-teste-unfrag.mp4" -vn -c:a pcm_s16le -ar 48000 -ac 2 "video-teste-audio.wav"

echo "EDL de áudio"
auto-editor "video-teste-unfrag.mp4" --edit audio -s 1 -v 1 --export v3 -o "video-teste-unfrag.edl.audio.json"
# Gera video-teste-unfrag.edl.audio.json

echo "EDL de movimento"
auto-editor "video-teste-unfrag.mp4" --edit motion -s 1 -v 1 --export v3 -o "video-teste-unfrag.edl.motion.json"
# Gera video-teste-unfrag.edl.motion.json

echo "Combinar EDLs"
# python3 combinar_edl_midpoint.py
python3 combinar_edl_overlap.py
# Gera video-teste-combined_edl.json

echo "Processar clipes via FFmpeg"
./processar_com_edl.sh
# Gera video-teste-final.mp4

echo "Processar direto com auto-editor"
# auto-editor "video-teste-unfrag.mp4" -s 8 -v 1 --cut-out -o "video-teste-auto-editor-1.mp4"

# auto-editor "video-teste-unfrag.mp4" \
#   -s 8 \            # acelera 8× os trechos “silenciosos” (sem fala)
#   -v 1 \            # mantém 1× (velocidade normal) os trechos com fala
#   --cut-out \       # remove completamente (ou deixa virtualmente instantâneo) os trechos sem fala nem movimento
#   -o "video-teste-final.mp4"

echo "Processar direto com auto-editor com margem na fala"
# auto-editor "video-teste-unfrag.mp4" -s 10 -v 1 -m 1 --cut-out -o "video-teste-auto-editor-2.mp4"

# auto-editor "video-teste-unfrag.mp4" \
#   -s 10 \           # acelera 10× quem estiver sem áudio
#   -v 1 \
#   -m 1 \            # adiciona 1 seg de “buffer” antes/depois de cada trecho com fala
#   --cut-out \
#   -o "video-teste-final-2.mp4"