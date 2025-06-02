#!/usr/bin/env python3
import json
import sys

# Ajuste nomes caso necessário
audio_edl_file  = "video-teste-unfrag.edl.audio.json"
motion_edl_file = "video-teste-unfrag.edl.motion.json"
output_file     = "video-teste-unfrag.edl.combined.json"

def load_edl(path, which):
    """
    Lê o JSON completo e retorna a lista de segmentos.
    - if which == "audio": retorna data["a"][0]
    - if which == "motion": retorna data["v"][0]
    """
    with open(path, 'r') as f:
        data = json.load(f)

    if which == "audio":
        # Esperamos um dicionário que contenha a chave "a"
        if "a" not in data or not isinstance(data["a"], list):
            print(f"Erro: '{path}' não contém campo 'a' como lista.")
            sys.exit(1)
        inner = data["a"]
    else:  # which == "motion"
        if "v" not in data or not isinstance(data["v"], list):
            print(f"Erro: '{path}' não contém campo 'v' como lista.")
            sys.exit(1)
        inner = data["v"]

    # inner deve ser do tipo [ [ { … }, { … }, … ] ]
    if not inner or not isinstance(inner[0], list):
        print(f"Erro: '{path}' não está no formato esperado (campo '{which[0]}' sem sublista).")
        sys.exit(1)

    # Retorna a primeira sublista de segmentos
    return inner[0]


# 1) Carrega EDLs (audio → segment list em key "a",[0]; motion → segment list em key "v",[0])
edl_audio  = load_edl(audio_edl_file,  "audio")
edl_motion = load_edl(motion_edl_file, "motion")

# 2) Coleta todos os limites (start/end) de ambos os EDLs
boundaries = set()
for seg in edl_audio + edl_motion:
    # Cada seg é um dict com "start" e "dur"; o “end” = start + dur
    start = seg.get("start")
    dur   = seg.get("dur")
    if start is None or dur is None:
        print("Erro: segmento sem 'start' ou 'dur'.")
        sys.exit(1)
    boundaries.add(start)
    boundaries.add(start + dur)

bounds = sorted(boundaries)

# 3) Para cada intervalo [bounds[i], bounds[i+1]) decide o tipo
combined = []
for i in range(len(bounds) - 1):
    s   = bounds[i]
    e   = bounds[i + 1]
    mid = (s + e) / 2.0

    # Verifica se mid cai em algum segmento de áudio (fala)
    in_audio  = any(seg["start"] <= mid < seg["start"] + seg["dur"] for seg in edl_audio)
    # Verifica se mid cai em algum segmento de movimento (código)
    in_motion = any(seg["start"] <= mid < seg["start"] + seg["dur"] for seg in edl_motion)

    if in_audio:
        typ = "speech"
    elif in_motion:
        typ = "code"
    else:
        typ = "inactive"

    combined.append({"start": s, "end": e, "type": typ})

# 4) Salva o JSON combinado
with open(output_file, 'w') as f:
    json.dump(combined, f, indent=2)

print(f"Combined EDL salvo em: {output_file}")







# # Carrega EDLs
# with open(audio_edl_file, 'r') as f:
#     edl_audio = json.load(f)
# with open(motion_edl_file, 'r') as f:
#     edl_motion = json.load(f)

# # Reúne todos os limites (start/end) de ambos
# boundaries = set()
# for seg in edl_audio + edl_motion:
#     boundaries.add(seg["start"])
#     boundaries.add(seg["end"])
# bounds = sorted(boundaries)

# combined = []
# for i in range(len(bounds) - 1):
#     s = bounds[i]
#     e = bounds[i + 1]
#     mid = (s + e) / 2.0

#     in_audio  = any(seg["start"] <= mid < seg["end"] for seg in edl_audio)
#     in_motion = any(seg["start"] <= mid < seg["end"] for seg in edl_motion)

#     if in_audio:
#         typ = "speech"
#     elif in_motion:
#         typ = "code"
#     else:
#         typ = "inactive"

#     combined.append({"start": s, "end": e, "type": typ})

# with open(output_file, 'w') as f:
#     json.dump(combined, f, indent=2)

# print(f"Combined EDL salvo em: {output_file}")
