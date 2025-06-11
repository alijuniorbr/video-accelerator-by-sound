# pv_step_01_audio_segment.py
import os
import json
import sys
import math
import subprocess
import shutil # Adicionado import que faltava
import argparse # Adicionado import que faltava
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
from pydub.silence import detect_silence

# As funções de pv_utils não são mais necessárias para esta versão simplificada do Step 1

def segment_video( video_path, 
                   output_dir, 
                   json_file_name, 
                   min_silence_len_ms, 
                   silence_thresh_dbfs, 
                   speech_start_padding_ms,
                   apply_fade=False): # Parâmetro para controlar o fade
    """
    Segmenta o vídeo baseado em análise de áudio, re-codificando cada segmento.
    Esta versão é otimizada para ser mais rápida e robusta, sem a lógica de keyframes.
    Retorna: (caminho_video_usado, caminho_json_indice, None, lista_segmentos_do_json)
    """
    
    os.makedirs(output_dir, exist_ok=True) 
    output_json_path = os.path.join(output_dir, json_file_name)
    print(f"--- Iniciando Etapa 1: Segmentação (Modo Re-codificação) para '{os.path.basename(video_path)}' ---")
    print(f"   Segmentos e índice serão salvos em: '{os.path.abspath(output_dir)}'")

    # Inicializa variáveis para garantir que sempre existam
    video_clip_obj = None
    sound_index_content = []

    try:
        # Usa MoviePy para info inicial e para ter o objeto pronto para extração de áudio
        video_clip_obj = VideoFileClip(video_path)
        fps = video_clip_obj.fps
        duration_s = video_clip_obj.duration
        if not all([duration_s, fps]): raise ValueError("Duração ou FPS inválidos retornados pelo MoviePy.")
        duration_ms = int(duration_s * 1000)
        print(f"Vídeo carregado: {os.path.basename(video_path)}, Duração: {duration_s:.2f}s, FPS: {fps:.2f}")
    except Exception as e:
        print(f"Falha crítica ao carregar o vídeo '{os.path.basename(video_path)}': {e}")
        if video_clip_obj: video_clip_obj.close()
        return video_path, None, None, None

    # Extração de Áudio para Pydub
    temp_audio_path = os.path.join(output_dir, f"temp_audio_{os.path.splitext(os.path.basename(video_path))[0]}.wav")
    try:
        print(f"Extraindo áudio para Pydub...")
        video_clip_obj.audio.write_audiofile(temp_audio_path, codec='pcm_s16le', logger=None)
        full_audio_segment = AudioSegment.from_wav(temp_audio_path)
    except Exception as e:
        print(f"Erro ao extrair áudio: {e}")
        if video_clip_obj: video_clip_obj.close()
        return video_path, None, None, None
    finally:
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)

    # Detecção de Silêncio
    print(f"Detectando silêncio (min_len: {min_silence_len_ms}ms, threshold: {silence_thresh_dbfs}dBFS)...")
    silent_chunks_ms = detect_silence(full_audio_segment, min_silence_len_ms, silence_thresh_dbfs, 1)
    print(f"Detectados {len(silent_chunks_ms)} trechos de silêncio.")

    # 1. Gerar lista inicial de segmentos contíguos
    initial_segments = []
    current_time_ms = 0
    if duration_ms > 0:
        if not silent_chunks_ms:
            initial_segments.append({"start_ms": 0, "end_ms": duration_ms, "type": "speech"})
        else:
            for silent_start, silent_end in silent_chunks_ms:
                if silent_start > current_time_ms:
                    initial_segments.append({"start_ms": current_time_ms, "end_ms": silent_start, "type": "speech"})
                if silent_end > silent_start:
                    initial_segments.append({"start_ms": silent_start, "end_ms": silent_end, "type": "silent"})
                current_time_ms = silent_end
            if current_time_ms < duration_ms:
                initial_segments.append({"start_ms": current_time_ms, "end_ms": duration_ms, "type": "speech"})
        initial_segments = [s for s in initial_segments if s["end_ms"] > s["start_ms"]]
        if not initial_segments:
            initial_segments.append({"start_ms": 0, "end_ms": duration_ms, "type": "speech"})
    
    # 2. Aplicar padding e ajustar contiguidade
    padded_segments = []
    if initial_segments:
        padded_segments = [s.copy() for s in initial_segments] # Começa com uma cópia

        for i in range(len(padded_segments)):
            if padded_segments[i]['type'] == "speech":
                # Aplica padding recuando o início da fala
                original_start = padded_segments[i]['start_ms']
                padded_start = max(0, original_start - speech_start_padding_ms)
                padded_segments[i]['start_ms'] = padded_start
                
                # Ajusta o final do segmento de silêncio anterior (se houver)
                if i > 0 and padded_segments[i-1]['type'] == 'silent':
                    padded_segments[i-1]['end_ms'] = max(padded_segments[i-1]['start_ms'], padded_start)

    # 3. Refiltrar e fatiar o áudio com base nos tempos finais com padding
    final_segments_props = []
    if padded_segments:
        for seg in padded_segments:
            start = seg['start_ms']
            end = seg['end_ms']
            if end > start: # Apenas se tiver duração positiva após todos os ajustes
                chunk_start = max(0, min(start, duration_ms))
                chunk_end = max(0, min(end, duration_ms))
                audio_chunk = full_audio_segment[chunk_start:chunk_end] if chunk_end > chunk_start else AudioSegment.empty()
                final_segments_props.append({
                    "start_ms": start, "end_ms": end,
                    "type": seg['type'], "audio_chunk": audio_chunk
                })
    print(f"Gerados {len(final_segments_props)} segmentos de áudio com padding.")
    
    # 4. Loop de criação de vídeos com FFmpeg
    for seg_prop_index, seg_info in enumerate(final_segments_props):
        start_ms, end_ms, segment_type, pydub_audio_chunk = seg_info.values()

        start_time_s = start_ms / 1000.0
        actual_end_time_s = min(end_ms / 1000.0, duration_s)
        duration_of_segment_s = actual_end_time_s - start_time_s

        if duration_of_segment_s <= 0.001: continue
        
        actual_segment_index = len(sound_index_content) # Usa o tamanho atual da lista para o próximo índice
        filename = f"{actual_segment_index:06d}_{segment_type}.mp4"
        output_path = os.path.join(output_dir, filename)
        print(f"  Processando segmento {seg_prop_index+1}/{len(final_segments_props)}: {filename} (Duração: {duration_of_segment_s:.3f}s)")
        
        ffmpeg_command = [
            'ffmpeg', '-y', '-i', video_path, '-ss', str(start_time_s),
            '-t', str(duration_of_segment_s), '-map', '0:v:0?', '-map', '0:a:0?', 
            '-c:v', 'libx264', '-preset', 'ultrafast', 
            '-force_key_frames', "expr:eq(n,0)", '-c:a', 'aac', '-b:a', '192k',
            '-ar', '48000', '-ac', '2',
        ]
        
        if apply_fade:
            fade_duration_s = 0.02
            if duration_of_segment_s > (2 * fade_duration_s):
                fade_out_start = duration_of_segment_s - fade_duration_s
                audio_filter = f"afade=t=in:st=0:d={fade_duration_s},afade=t=out:st={fade_out_start:.3f}:d={fade_duration_s}"
                ffmpeg_command.extend(['-af', audio_filter])
        
        ffmpeg_command.append(output_path)
        
        try:
            result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                # ... (cálculo de metadata como antes) ...
                frame_start = math.floor(start_time_s * fps)
                frame_end = math.floor(actual_end_time_s * fps) - 1
                metadata = {
                    "index": actual_segment_index, "file": filename,
                    "frame_start": frame_start, "frame_end": frame_end,
                    "time_start": round(start_time_s, 3), "time_end": round(actual_end_time_s, 3),
                    "fps": round(float(fps), 2),
                    "db_min": f"{pydub_audio_chunk.dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}", 
                    "db_max": f"{pydub_audio_chunk.max_dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}",
                    "result": segment_type,
                    "processing_mode": "recode"
                }
                sound_index_content.append(metadata)
            else:
                print(f"  !! Erro FFmpeg para {filename} (cód: {result.returncode}): {result.stderr[:500]}...")
        except FileNotFoundError:
            print(f"!! ERRO CRÍTICO: 'ffmpeg' não encontrado."); video_clip_obj.close(); return None, None, None, None
        except Exception as e:
            print(f"  !! Erro subprocesso com FFmpeg para {filename}: {e}")

    if video_clip_obj: video_clip_obj.close()

    try:
        with open(output_json_path, 'w') as f: json.dump(sound_index_content, f, indent=2)
        print(f"Etapa 1 concluída para '{os.path.basename(video_path)}'. Índice salvo em '{output_json_path}'.")
    except Exception as e:
        print(f"Erro ao escrever JSON '{output_json_path}': {e}")
        return video_path, None, None, sound_index_content

    return video_path, output_json_path, None, sound_index_content

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Teste direto do script de segmentação (modo re-codificação).")
    parser.add_argument("video_path", help="Caminho para o vídeo de teste.")
    parser.add_argument("--fade", action='store_true', help="Aplicar fades de áudio.")
    args_test = parser.parse_args()

    test_output_dir = os.path.splitext(os.path.basename(args_test.video_path))[0] + "_s1_recode_test"
    print(f"--- Teste Direto: pv_step_01_audio_segment.py (Modo Re-codificação) ---")

    if os.path.exists(test_output_dir):
        print(f"Limpando dir de teste: {test_output_dir}...")
        shutil.rmtree(test_output_dir)
    os.makedirs(test_output_dir)

    MIN_SILENCE_LEN_MS = 3000
    SILENCE_THRESH_DBFS = -42
    SPEECH_START_PADDING_MS = 200

    segment_video(
        video_path_param=args_test.video_path,
        output_dir=test_output_dir,
        json_file_name_in_output_dir="sound_index_test.json",
        min_silence_len_ms=MIN_SILENCE_LEN_MS,
        silence_thresh_dbfs=SILENCE_THRESH_DBFS,
        speech_start_padding_ms=SPEECH_START_PADDING_MS,
        apply_fade=args_test.fade
    )