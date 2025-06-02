#!/usr/bin/env python3
import json
import sys

audio_edl_file  = "video-teste-unfrag.edl.audio.json"
motion_edl_file = "video-teste-unfrag.edl.motion.json"
output_file     = "video-teste-unfrag.edl.combined.json"

def load_edl(path, which):
    with open(path, 'r') as f:
        data = json.load(f)

    if which == "audio":
        if "a" not in data or not isinstance(data["a"], list):
            print(f"Erro: '{path}' não contém 'a' como lista.")
            sys.exit(1)
        inner = data["a"]
    else:
        if "v" not in data or not isinstance(data["v"], list):
            print(f"Erro: '{path}' não contém 'v' como lista.")
            sys.exit(1)
        inner = data["v"]

    if not inner or not isinstance(inner[0], list):
        print(f"Erro: '{path}' não está no formato esperado (campo sem sublista).")
        sys.exit(1)

    return inner[0]  # retorna lista de dicionários [{ "start":…, "dur":… }, …]

# Carrega EDLs
edl_audio  = load_edl(audio_edl_file,  "audio")
edl_motion = load_edl(motion_edl_file, "motion")

# Coleta todos os boundaries (início/fim)
boundaries = set()
for seg in edl_audio + edl_motion:
    s = seg.get("start")
    d = seg.get("dur")
    if s is None or d is None:
        print("Erro: segmento sem 'start' ou 'dur'.")
        sys.exit(1)
    boundaries.add(s)
    boundaries.add(s + d)

bounds = sorted(boundaries)

combined = []
# Para cada pedaço [bounds[i], bounds[i+1]):
for i in range(len(bounds) - 1):
    s = bounds[i]
    e = bounds[i+1]

    # Checa se [s,e) overlap com ANY trecho de áudio
    overlaps_audio = any(not (e <= a["start"] or s >= a["start"] + a["dur"]) for a in edl_audio)
    # Se não for áudio, checa overlap com movimento
    overlaps_motion = any(not (e <= m["start"] or s >= m["start"] + m["dur"]) for m in edl_motion)

    if overlaps_audio:
        typ = "speech"
    elif overlaps_motion:
        typ = "code"
    else:
        typ = "inactive"

    combined.append({"start": s, "end": e, "type": typ})

with open(output_file, 'w') as f:
    json.dump(combined, f, indent=2)

print(f"Combined EDL by overlap salvo em: {output_file}")
