# pv_step_01_audio_segment.py
import os
import json
import sys
import math
import subprocess
import shutil 
import argparse 
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
from pydub.silence import detect_silence

try:
    import pv_utils
except ImportError:
    print("AVISO: pv_utils.py não encontrado.")
    pv_utils = None

def segment_video(video_path_param, 
                  output_dir, 
                  json_file_name_in_output_dir, 
                  min_silence_len_ms, 
                  silence_thresh_dbfs, 
                  speech_start_padding_ms,
                  speech_end_padding_ms, # NOVO
                  apply_fade=False,
                  fade_duration_ms=20): # NOVO
    """
    Segmenta o vídeo baseado em análise de áudio, re-codificando cada segmento.
    """
    
    os.makedirs(output_dir, exist_ok=True) 
    output_json_path = os.path.join(output_dir, json_file_name_in_output_dir)
    print(f"--- Iniciando Etapa 1: Segmentação para '{os.path.basename(video_path_param)}' ---")
    print(f"   Padding Fala: {speech_start_padding_ms}ms (início), {speech_end_padding_ms}ms (fim)")

    video_clip_obj = None
    try:
        if pv_utils:
            video_info = pv_utils.get_extended_video_info(video_path_param)
            if video_info.get("error") and not (video_info.get("duration_s") and video_info.get("fps")):
                 raise ValueError(f"Falha via pv_utils: {video_info.get('error')}")
            duration_s, fps = video_info["duration_s"], video_info["fps"]
        else:
            video_clip_obj = VideoFileClip(video_path_param)
            duration_s, fps = video_clip_obj.duration, video_clip_obj.fps

        if not fps or fps <= 0: fps = 30.0
        if not duration_s or duration_s <= 0: raise ValueError("Duração inválida.")
        
        duration_ms = int(duration_s * 1000)
        print(f"Processando vídeo: {os.path.basename(video_path_param)}, Duração: {duration_s:.2f}s, FPS: {fps:.2f}")
    except Exception as e:
        if video_clip_obj: video_clip_obj.close()
        print(f"Falha crítica ao carregar info do vídeo: {e}")
        return None, None, None, None

    if not video_clip_obj: video_clip_obj = VideoFileClip(video_path_param)
    temp_audio_path = os.path.join(output_dir, f"temp_audio_{os.path.splitext(os.path.basename(video_path_param))[0]}.wav")
    try:
        print("Extraindo áudio para Pydub...")
        video_clip_obj.audio.write_audiofile(temp_audio_path, codec='pcm_s16le', logger=None)
        full_audio_segment = AudioSegment.from_wav(temp_audio_path)
    except Exception as e:
        print(f"Erro ao extrair áudio: {e}")
        if video_clip_obj: video_clip_obj.close(); 
        return None, None, None, None
    finally:
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
    
    print(f"Detectando silêncio (min_len: {min_silence_len_ms}ms, threshold: {silence_thresh_dbfs}dBFS)...")
    silent_chunks_ms = detect_silence(full_audio_segment, min_silence_len_ms, silence_thresh_dbfs, 1)
    
    # 1. Gerar lista inicial de segmentos contíguos
    initial_segments = []
    current_time_ms = 0
    if duration_ms > 0:
        if not silent_chunks_ms:
            initial_segments.append({"start_ms": 0, "end_ms": duration_ms, "type": "speech"})
        else:
            for silent_start, silent_end in silent_chunks_ms:
                if silent_start > current_time_ms: initial_segments.append({"start_ms": current_time_ms, "end_ms": silent_start, "type": "speech"})
                if silent_end > silent_start: initial_segments.append({"start_ms": silent_start, "end_ms": silent_end, "type": "silent"})
                current_time_ms = silent_end
            if current_time_ms < duration_ms: initial_segments.append({"start_ms": current_time_ms, "end_ms": duration_ms, "type": "speech"})
        initial_segments = [s for s in initial_segments if s["end_ms"] > s["start_ms"]]
        if not initial_segments: initial_segments.append({"start_ms": 0, "end_ms": duration_ms, "type": "speech"})
    
    # 2. Aplicar padding e criar a lista final de segmentos
    final_segments_props = []
    if initial_segments:
        # Expande todos os trechos de fala com o padding
        expanded_speech_segments = []
        for seg in initial_segments:
            if seg['type'] == "speech":
                expanded_start = max(0, seg['start_ms'] - speech_start_padding_ms)
                expanded_end = min(duration_ms, seg['end_ms'] + speech_end_padding_ms)
                expanded_speech_segments.append({"start_ms": expanded_start, "end_ms": expanded_end, "type": "speech"})
        
        # Junta segmentos de fala que se sobrepuseram
        if expanded_speech_segments:
            merged_speech_segments = [expanded_speech_segments[0].copy()]
            for i in range(1, len(expanded_speech_segments)):
                if expanded_speech_segments[i]['start_ms'] < merged_speech_segments[-1]['end_ms']:
                    merged_speech_segments[-1]['end_ms'] = max(merged_speech_segments[-1]['end_ms'], expanded_speech_segments[i]['end_ms'])
                else:
                    merged_speech_segments.append(expanded_speech_segments[i].copy())
        else: # Nenhum trecho de fala detectado
            merged_speech_segments = []

        # Preenche os buracos com silêncio
        last_end_time_ms = 0
        for speech_seg in merged_speech_segments:
            if speech_seg['start_ms'] > last_end_time_ms:
                final_segments_props.append({"start_ms": last_end_time_ms, "end_ms": speech_seg['start_ms'], "type": "silent"})
            final_segments_props.append(speech_seg)
            last_end_time_ms = speech_seg['end_ms']
        if last_end_time_ms < duration_ms:
            final_segments_props.append({"start_ms": last_end_time_ms, "end_ms": duration_ms, "type": "silent"})
        if not final_segments_props and duration_ms > 0:
            final_segments_props.append({"start_ms": 0, "end_ms": duration_ms, "type": "silent" if not speech_segments else "speech"})
    
    print(f"Gerados {len(final_segments_props)} segmentos finais com padding.")
    
    # Atribui o audio_chunk a cada segmento final
    for seg in final_segments_props:
        start_ms, end_ms = seg['start_ms'], seg['end_ms']
        chunk_start, chunk_end = max(0, min(start_ms, duration_ms)), max(0, min(end_ms, duration_ms))
        seg['audio_chunk'] = full_audio_segment[chunk_start:chunk_end] if chunk_end > chunk_start else AudioSegment.empty()

    # 3. Loop de criação de vídeos com FFmpeg
    sound_index_content = []
    # ... (o resto da lógica de criação de vídeo, metadados e salvamento do JSON é o mesmo) ...
    # (Vou colar o resto para ser completo)
    for seg_prop_index, seg_info in enumerate(final_segments_props):
        start_ms, end_ms, segment_type, pydub_audio_chunk = seg_info.values()
        start_time_s = start_ms / 1000.0
        actual_end_time_s = min(end_ms / 1000.0, duration_s)
        duration_of_segment_s = actual_end_time_s - start_time_s
        if duration_of_segment_s <= 0.001: continue
        
        actual_segment_index = len(sound_index_content)
        filename = f"{actual_segment_index:06d}_{segment_type}.mp4"
        output_path = os.path.join(output_dir, filename)
        print(f"  Processando segmento {seg_prop_index+1}/{len(final_segments_props)}: {filename} ({duration_of_segment_s:.3f}s)")
        
        ffmpeg_command = [
            'ffmpeg', '-y', '-i', video_path_param, '-ss', str(start_time_s),
            '-t', str(duration_of_segment_s), '-map', '0:v:0?', '-map', '0:a:0?', 
            '-c:v', 'libx264', '-preset', 'ultrafast', 
            '-force_key_frames', "expr:eq(n,0)", '-c:a', 'aac', '-b:a', '192k',
            '-ar', '48000', '-ac', '2',
        ]
        
        if apply_fade:
            fade_duration_s = fade_duration_ms / 1000.0
            if duration_of_segment_s > (2 * fade_duration_s):
                fade_out_start = duration_of_segment_s - fade_duration_s
                audio_filter = f"afade=t=in:st=0:d={fade_duration_s},afade=t=out:st={fade_out_start:.3f}:d={fade_duration_s}"
                ffmpeg_command.extend(['-af', audio_filter])
        
        ffmpeg_command.append(output_path)
        
        try:
            result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                metadata = {
                    "index": actual_segment_index, "file": filename,
                    "frame_start": math.floor(start_time_s * fps), "frame_end": math.floor(actual_end_time_s * fps) -1,
                    "time_start": round(start_time_s, 3), "time_end": round(actual_end_time_s, 3), "fps": round(float(fps), 2),
                    "db_min": f"{pydub_audio_chunk.dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}", 
                    "db_max": f"{pydub_audio_chunk.max_dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}",
                    "result": seg_info['type'],
                }
                sound_index_content.append(metadata)
            else:
                print(f"  !! Erro FFmpeg para {filename} (cód: {result.returncode}): {result.stderr[:500]}...")
        except Exception as e:
            print(f"  !! Erro subprocesso com FFmpeg para {filename}: {e}")

    if video_clip_obj: video_clip_obj.close()
    try:
        with open(output_json_path, 'w') as f: json.dump(sound_index_content, f, indent=2)
        print(f"Etapa 1 concluída. Índice salvo em '{output_json_path}'.")
    except Exception as e:
        print(f"Erro ao escrever JSON '{output_json_path}': {e}")
        return video_path_param, None, None, sound_index_content
    
    return video_path_param, output_json_path, None, sound_index_content


# O bloco if __name__ == "__main__": permanece o mesmo para testes