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
    print("AVISO: pv_utils.py não encontrado. As informações do vídeo serão obtidas com MoviePy.")
    pv_utils = None

def segment_video(video_path_param, 
                  output_dir, 
                  json_file_name, 
                  min_silence_len_ms, 
                  silence_thresh_dbfs, 
                  speech_start_padding_ms,
                  apply_fade=False,
                  # Parâmetros de KF não são usados ativamente aqui, mas mantidos para compatibilidade
                  prompt_user_for_kf_re_encode=False,
                  force_kf_re_encode=False,
                  keyframe_interval_s_for_re_encode=1.0):
    """
    Segmenta o vídeo baseado em análise de áudio, re-codificando cada segmento.
    Verifica se os segmentos já existem para permitir a retomada do processo.
    """
    
    os.makedirs(output_dir, exist_ok=True) 
    output_json_path = os.path.join(output_dir, json_file_name)
    print(f"--- Iniciando Etapa 1: Segmentação (Modo Re-codificação) para '{os.path.basename(video_path_param)}' ---")

    video_clip_obj = None
    sound_index_content = []
    
    try:
        video_info = pv_utils.get_extended_video_info(video_path_param) if pv_utils else {}
        if not video_info.get("duration_s"): # Fallback para MoviePy se pv_utils falhar ou não existir
            video_clip_obj = VideoFileClip(video_path_param)
            duration_s, fps = video_clip_obj.duration, video_clip_obj.fps
        else:
            duration_s, fps = video_info["duration_s"], video_info["fps"]

        if not fps or fps <= 0: fps = 30.0
        if not duration_s or duration_s <= 0: raise ValueError("Duração do vídeo inválida.")
        duration_ms = int(duration_s * 1000)
        print(f"Processando vídeo: {os.path.basename(video_path_param)}, Duração: {duration_s:.2f}s, FPS: {fps:.2f}")
    except Exception as e:
        if video_clip_obj: video_clip_obj.close()
        print(f"Falha crítica ao carregar info do vídeo: {e}")
        return None, None, None, None

    # Verifica se o JSON já existe e está completo. Se sim, pula tudo.
    if os.path.exists(output_json_path):
        print(f"Arquivo de índice '{output_json_path}' já existe. Verificando se o processo pode ser pulado.")
        try:
            with open(output_json_path, 'r') as f:
                existing_data = json.load(f)
            # Uma heurística para checar se está completo: o tempo final do último segmento é próximo da duração total?
            if existing_data and abs(existing_data[-1]['time_end'] - duration_s) < 0.1:
                print("Parece que a segmentação para este chunk já está completa. Pulando para a próxima etapa.")
                if video_clip_obj: video_clip_obj.close()
                # Retorna os dados existentes para o pv-process.py poder continuar
                return video_path_param, output_json_path, None, existing_data
            else:
                print("O índice JSON parece incompleto. O processo continuará, verificando cada segmento.")
        except Exception as e:
            print(f"Não foi possível ler o índice JSON existente, continuando o processo do zero. Erro: {e}")


    # Extração de Áudio
    if not video_clip_obj: video_clip_obj = VideoFileClip(video_path_param)
    temp_audio_path = os.path.join(output_dir, f"temp_audio_{os.path.splitext(os.path.basename(video_path_param))[0]}.wav")
    try:
        print(f"Extraindo áudio de '{os.path.basename(video_path_param)}' para Pydub...")
        video_clip_obj.audio.write_audiofile(temp_audio_path, codec='pcm_s16le', logger=None)
        full_audio_segment = AudioSegment.from_wav(temp_audio_path)
    except Exception as e:
        print(f"Erro ao extrair áudio: {e}")
        if video_clip_obj: video_clip_obj.close(); 
        return video_path_param, None, None, None
    finally:
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
    
    # Detecção de Silêncio e Geração de Segmentos Iniciais
    print(f"Detectando silêncio (min_len: {min_silence_len_ms}ms, threshold: {silence_thresh_dbfs}dBFS)...")
    silent_chunks_ms = detect_silence(full_audio_segment, min_silence_len_ms, silence_thresh_dbfs, 1)
    
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

    # Aplicação de Padding e Ajuste de Contiguidade
    padded_segments = []
    if initial_segments:
        temp_segments = [s.copy() for s in initial_segments]
        for i in range(len(temp_segments)):
            if temp_segments[i]['type'] == "speech":
                original_start = temp_segments[i]['start_ms']
                padded_start = max(0, original_start - speech_start_padding_ms)
                temp_segments[i]['start_ms'] = padded_start
                if i > 0 and temp_segments[i-1]['type'] == 'silent':
                    temp_segments[i-1]['end_ms'] = max(temp_segments[i-1]['start_ms'], padded_start)
        last_end_time = 0
        for seg in temp_segments:
            start_ms = max(last_end_time, seg['start_ms'])
            if seg['end_ms'] > start_ms:
                seg['start_ms'] = start_ms
                padded_segments.append(seg)
                last_end_time = seg['end_ms']

    print(f"Gerados {len(padded_segments)} segmentos com padding e contiguidade verificada.")

    # Loop de criação de vídeos com FFmpeg
    for seg_prop_index, seg_info in enumerate(padded_segments):
        start_ms, end_ms, segment_type = seg_info["start_ms"], seg_info["end_ms"], seg_info["type"]
        duration_of_segment_s = (end_ms - start_ms) / 1000.0
        if duration_of_segment_s <= 0.001: continue
        
        actual_segment_index = len(sound_index_content)
        filename = f"{actual_segment_index:06d}_{segment_type}.mp4"
        output_path = os.path.join(output_dir, filename)

        # === LÓGICA DE VERIFICAÇÃO INDIVIDUAL DO SEGMENTO ===
        if os.path.isfile(output_path):
            print(f"  Segmento {seg_prop_index+1}/{len(padded_segments)}: '{filename}' já existe. Pulando criação.")
            # Precisamos recriar os metadados para adicionar à lista, mesmo pulando a criação do arquivo
            start_time_s = start_ms / 1000.0
            actual_end_time_s = min(end_ms / 1000.0, duration_s)
            chunk_start = max(0, min(start_ms, duration_ms)); chunk_end = max(0, min(end_ms, duration_ms))
            pydub_audio_chunk = full_audio_segment[chunk_start:chunk_end] if chunk_end > chunk_start else AudioSegment.empty()
            metadata = { "index": actual_segment_index, "file": filename, "frame_start": math.floor(start_time_s * fps), "frame_end": math.floor(actual_end_time_s * fps) -1, "time_start": round(start_time_s, 3), "time_end": round(actual_end_time_s, 3), "fps": round(float(fps), 2), "db_min": f"{pydub_audio_chunk.dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}", "db_max": f"{pydub_audio_chunk.max_dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}", "result": segment_type, "processing_mode": "recode_skipped"}
            sound_index_content.append(metadata)
            continue
        # ======================================================
        
        print(f"  Processando segmento {seg_prop_index+1}/{len(padded_segments)}: {filename} ({duration_of_segment_s:.3f}s)")
        # ... (comando FFmpeg e execução como no script anterior que funcionou bem para você) ...
        # (Vou colar a versão sem fades, pois foi a última estável)
        start_time_s = start_ms / 1000.0
        ffmpeg_command = [
            'ffmpeg', '-y', '-i', video_path_param, '-ss', str(start_time_s), '-t', str(duration_of_segment_s),
            '-map', '0:v:0?', '-map', '0:a:0?', '-c:v', 'libx264', '-preset', 'ultrafast', 
            '-force_key_frames', "expr:eq(n,0)", '-c:a', 'aac', '-b:a', '192k',
            '-ar', '48000', '-ac', '2', output_path
        ]
        # Se quiser tentar os fades novamente, descomente o bloco abaixo
        # if apply_fade:
        #     fade_duration_s = 0.02
        #     if duration_of_segment_s > (2 * fade_duration_s):
        #         fade_out_start = duration_of_segment_s - fade_duration_s
        #         audio_filter = f"afade=t=in:st=0:d={fade_duration_s},afade=t=out:st={fade_out_start:.3f}:d={fade_duration_s}"
        #         ffmpeg_command.insert(-1, '-af')
        #         ffmpeg_command.insert(-1, audio_filter)
        
        try:
            result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                # ... (lógica de metadados como no script anterior) ...
                actual_end_time_s = min(end_ms / 1000.0, duration_s)
                chunk_start = max(0, min(start_ms, duration_ms)); chunk_end = max(0, min(end_ms, duration_ms))
                pydub_audio_chunk = full_audio_segment[chunk_start:chunk_end] if chunk_end > chunk_start else AudioSegment.empty()
                metadata = { "index": actual_segment_index, "file": filename, "frame_start": math.floor(start_time_s * fps), "frame_end": math.floor(actual_end_time_s * fps) -1, "time_start": round(start_time_s, 3), "time_end": round(actual_end_time_s, 3), "fps": round(float(fps), 2), "db_min": f"{pydub_audio_chunk.dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}", "db_max": f"{pydub_audio_chunk.max_dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}", "result": seg_info['type'], "processing_mode": "recode"}
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

if __name__ == "__main__":
    # Bloco de teste direto
    parser = argparse.ArgumentParser(description="Teste direto do script de segmentação (modo re-codificação).")
    parser.add_argument("video_path", help="Caminho para o vídeo de teste.")
    parser.add_argument("--fade", action='store_true', help="Aplicar fades de áudio.")
    # Adicionar outros argumentos para teste
    parser.add_argument("-m", "--min_silence_len_ms", type=int, default=3000)
    parser.add_argument("-t", "--silence_thresh_dbfs", type=int, default=-42)
    parser.add_argument("-p", "--speech_start_padding_ms", type=int, default=200)
    
    args_test = parser.parse_args()

    test_output_dir = os.path.splitext(os.path.basename(args_test.video_path))[0] + "_s1_recode_test"
    if os.path.exists(test_output_dir):
        print(f"Limpando dir de teste: {test_output_dir}..."); shutil.rmtree(test_output_dir)
    os.makedirs(test_output_dir)

    segment_video(
        video_path_param=args_test.video_path, output_dir=test_output_dir,
        json_file_name_in_output_dir="sound_index_test.json", min_silence_len_ms=args_test.min_silence_len_ms,
        silence_thresh_dbfs=args_test.silence_thresh_dbfs, speech_start_padding_ms=args_test.speech_start_padding_ms,
        apply_fade=args_test.fade
    )