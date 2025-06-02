# pv_step_01_audio_segment.py
import os
import json
import sys
import math
import subprocess
import shutil # Para limpar diretório de teste no __main__
from moviepy.editor import VideoFileClip # Para extração de áudio e info se ffprobe falhar
from pydub import AudioSegment
from pydub.silence import detect_silence

try:
    import pv_utils 
except ImportError:
    print("AVISO: pv_utils.py não encontrado. Informações de vídeo podem ser limitadas.")
    pv_utils = None

def segment_video(video_path_param, 
                  output_dir, 
                  json_file_name_in_output_dir, 
                  min_silence_len_ms, 
                  silence_thresh_dbfs, 
                  speech_start_padding_ms,
                  # Parâmetros de KF abaixo não são usados ativamente nesta versão, mas mantidos para assinatura
                  prompt_user_for_kf_re_encode=False, 
                  force_kf_re_encode=False,
                  keyframe_interval_s_for_re_encode=1.0):
    """
    Segmenta o vídeo baseado em análise de áudio, re-codificando cada segmento.
    NÃO realiza mais a verificação/re-codificação de keyframes do vídeo de origem.
    Retorna: (caminho_video_usado, caminho_json_indice, None, lista_segmentos_do_json)
    """
    
    output_json_path = os.path.join(output_dir, json_file_name_in_output_dir)
    os.makedirs(output_dir, exist_ok=True) 

    print(f"--- Iniciando Etapa 1: Segmentação (Re-codificando Segmentos) para '{os.path.basename(video_path_param)}' ---")
    print(f"   Segmentos e índice serão salvos em: '{os.path.abspath(output_dir)}'")

    # Nesta versão, o vídeo processado é sempre o vídeo de entrada original.
    current_video_to_process = video_path_param 
    kf_re_encode_details = None # Não fazemos re-encode de KF do vídeo de origem aqui
    sound_index_content = [] # Lista para os metadados dos segmentos

    try:
        # Obter informações do vídeo (duração, fps)
        if pv_utils:
            video_info = pv_utils.get_extended_video_info(current_video_to_process)
            if video_info.get("error") and not (video_info.get("duration_s") and video_info.get("fps")):
                 raise ValueError(f"Falha ao obter informações do vídeo via pv_utils: {video_info.get('error')}")
            duration_s = video_info["duration_s"]
            fps = video_info["fps"]
        else: # Fallback para MoviePy se pv_utils não estiver disponível
            clip_temp = VideoFileClip(current_video_to_process)
            duration_s = clip_temp.duration
            fps = clip_temp.fps
            clip_temp.close()

        if not fps or fps <= 0: fps = 30.0 # Fallback robusto para FPS
        if not duration_s or duration_s <=0:
            print(f"Erro: Vídeo '{current_video_to_process}' parece ter duração zero ou inválida. Abortando etapa.")
            return current_video_to_process, None, kf_re_encode_details, None

        duration_ms = int(duration_s * 1000)
        print(f"Processando vídeo: {os.path.basename(current_video_to_process)}, Duração: {duration_s:.2f}s, FPS: {fps:.2f}")
    except Exception as e:
        print(f"Falha crítica ao obter informações de '{os.path.basename(current_video_to_process)}': {e}")
        return current_video_to_process, None, kf_re_encode_details, None


    # Extração de Áudio para Pydub
    video_clip_for_audio = VideoFileClip(current_video_to_process)
    temp_audio_path = os.path.join(output_dir, f"temp_audio_{os.path.splitext(os.path.basename(current_video_to_process))[0]}.wav")
    try:
        print(f"Extraindo áudio de '{os.path.basename(current_video_to_process)}' para Pydub...")
        video_clip_for_audio.audio.write_audiofile(temp_audio_path, codec='pcm_s16le', logger=None)
        full_audio_segment = AudioSegment.from_wav(temp_audio_path)
    except Exception as e:
        print(f"Erro ao extrair áudio: {e}")
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
        video_clip_for_audio.close()
        return current_video_to_process, None, kf_re_encode_details, None
    finally:
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
    
    # Detecção de Silêncio
    print(f"Detectando silêncio (min_len: {min_silence_len_ms}ms, threshold: {silence_thresh_dbfs}dBFS)...")
    silent_chunks_ms = detect_silence(full_audio_segment, min_silence_len_ms, silence_thresh_dbfs, 1)
    print(f"Detectados {len(silent_chunks_ms)} trechos de silêncio (análise de áudio).")

    # 1. Gerar lista inicial de segmentos contíguos
    initial_segments_props = []
    current_time_ms = 0
    if duration_ms > 0:
        if not silent_chunks_ms:
            initial_segments_props.append({"start_ms": 0, "end_ms": duration_ms, "type": "speech"})
        else:
            for silent_start, silent_end in silent_chunks_ms:
                if silent_start > current_time_ms:
                    initial_segments_props.append({"start_ms": current_time_ms, "end_ms": silent_start, "type": "speech"})
                if silent_end > silent_start:
                    initial_segments_props.append({"start_ms": silent_start, "end_ms": silent_end, "type": "silent"})
                current_time_ms = silent_end
            if current_time_ms < duration_ms:
                initial_segments_props.append({"start_ms": current_time_ms, "end_ms": duration_ms, "type": "speech"})
        initial_segments_props = [s for s in initial_segments_props if s["end_ms"] > s["start_ms"]]
        if not initial_segments_props : initial_segments_props.append({"start_ms": 0, "end_ms": duration_ms, "type": "speech"})
    
    # 2. Aplicar padding e ajustar contiguidade
    segments_with_padding = []
    if initial_segments_props:
        # Adiciona o primeiro segmento, aplicando padding se for fala
        first_seg = initial_segments_props[0].copy()
        s_start, s_end, s_type = first_seg['start_ms'], first_seg['end_ms'], first_seg['type']
        if s_type == "speech": s_start = max(0, s_start - speech_start_padding_ms)
        if s_end > s_start: segments_with_padding.append({"start_ms": s_start, "end_ms": s_end, "type": s_type})

        # Segmentos restantes
        for i in range(1, len(initial_segments_props)):
            current_s_info = initial_segments_props[i].copy()
            s_start_orig, s_end_curr, s_type_curr = current_s_info['start_ms'], current_s_info['end_ms'], current_s_info['type']
            
            prev_padded_seg = segments_with_padding[-1] if segments_with_padding else None # Pega o último adicionado à lista processada

            current_s_start_final = s_start_orig # Início padrão do segmento atual

            if s_type_curr == "speech":
                current_s_start_final = max(0, s_start_orig - speech_start_padding_ms)
                if prev_padded_seg and prev_padded_seg['type'] == 'silent':
                    # Ajusta o fim do silêncio anterior para encontrar o novo início da fala
                    prev_padded_seg['end_ms'] = max(prev_padded_seg['start_ms'], current_s_start_final)
            elif prev_padded_seg: # Se o atual é silêncio, ele deve começar onde o anterior (fala ou silêncio) terminou
                current_s_start_final = prev_padded_seg['end_ms']
            
            # Adiciona o segmento atual se ele ainda tiver uma duração válida
            if s_end_curr > current_s_start_final:
                # Remove o segmento anterior da lista processada se ele ficou com duração zero ou negativa
                if prev_padded_seg and prev_padded_seg['end_ms'] <= prev_padded_seg['start_ms']:
                    if segments_with_padding and segments_with_padding[-1] is prev_padded_seg:
                        segments_with_padding.pop()
                
                segments_with_padding.append({
                    "start_ms": current_s_start_final, 
                    "end_ms": s_end_curr, 
                    "type": s_type_curr
                })
        
        # Atribui audio_chunk e filtra novamente para garantir não sobreposição e positividade
        audio_based_segments_props_final = []
        last_segment_end_ms = 0
        for seg_idx, seg in enumerate(segments_with_padding):
            # Força o início do segmento atual a ser o fim do anterior, para garantir contiguidade
            # Exceto para o primeiro segmento, que começa em seu 'start_ms' calculado (que pode ser 0 ou >0 devido a padding)
            effective_start_ms = max(last_segment_end_ms, seg['start_ms']) if seg_idx > 0 else seg['start_ms']
            effective_end_ms = seg['end_ms']

            if effective_end_ms > effective_start_ms:
                 # Garante que os chunks de áudio não saiam dos limites do áudio original
                 chunk_start = max(0, min(effective_start_ms, duration_ms))
                 chunk_end = max(0, min(effective_end_ms, duration_ms))
                 audio_chunk = full_audio_segment[chunk_start:chunk_end] if chunk_end > chunk_start else AudioSegment.empty()
                 
                 audio_based_segments_props_final.append({
                     "start_ms": effective_start_ms,
                     "end_ms": effective_end_ms,
                     "type": seg['type'],
                     "audio_chunk": audio_chunk
                 })
                 last_segment_end_ms = effective_end_ms
        segments_props = audio_based_segments_props_final
    else:
        segments_props = []
    print(f"Gerados {len(segments_props)} segmentos de áudio com padding e contiguidade verificada.")

    # Filtrar segmentos muito curtos (menos de meio frame, por segurança)
    min_ffmpeg_duration_ms = (1000 / fps) / 2 if fps > 0 else 8 
    final_segments_to_process = [
        s for s in segments_props if (s["end_ms"] - s["start_ms"]) >= min_ffmpeg_duration_ms
    ]
    print(f"Total de segmentos (após filtro de duração mínima) a serem processados com FFmpeg: {len(final_segments_to_process)}")

    # 3. Cortar com FFmpeg (RE-CODIFICANDO) e gerar JSON
    sound_index_data_content = []
    actual_segment_index = 0 
    for seg_prop_index, seg_info in enumerate(final_segments_to_process):
        start_ms = seg_info["start_ms"]
        end_ms = seg_info["end_ms"]
        segment_type = seg_info["type"]
        pydub_audio_chunk_for_db = seg_info["audio_chunk"]

        start_time_s = start_ms / 1000.0
        actual_end_time_s = min(end_ms / 1000.0, duration_s) # Garante que não exceda
        duration_of_segment_s = actual_end_time_s - start_time_s

        if duration_of_segment_s <= 0.001: continue # Segurança final
        
        filename = f"{actual_segment_index:06d}_{segment_type}.mp4"
        output_path = os.path.join(output_dir, filename)
        print(f"  Processando segmento {seg_prop_index+1}/{len(final_segments_to_process)}: {filename} (Duração: {duration_of_segment_s:.3f}s)")
        
        ffmpeg_command = [
            'ffmpeg', '-y', 
            '-i', current_video_to_process, 
            '-ss', str(start_time_s),
            '-t', str(duration_of_segment_s),
            '-map', '0:v:0?', '-map', '0:a:0?', 
            '-c:v', 'libx264', '-preset', 'ultrafast', 
            '-force_key_frames', "expr:eq(n,0)", 
            '-c:a', 'aac', '-b:a', '192k',
            '-ar', '48000', '-ac', '2',
            output_path
        ]
        # SEM FADES DE ÁUDIO
        
        try:
            result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            # Descomente para logs FFmpeg completos
            # print(f"    --- Iniciando saída FFmpeg para {filename} ---")
            # if result.stdout: print("    FFmpeg STDOUT:\n" + result.stdout.strip())
            # if result.stderr: print("    FFmpeg STDERR:\n" + result.stderr.strip())
            # print(f"    --- Fim da saída FFmpeg (código de retorno: {result.returncode}) ---")

            if result.returncode == 0:
                frame_start = math.floor(start_time_s * fps)
                frame_end = math.floor(actual_end_time_s * fps) -1 
                if frame_end < frame_start:
                    if actual_end_time_s > start_time_s: frame_end = frame_start
                    elif frame_start == 0 and (actual_end_time_s * fps < 1 if fps > 0 else True) : frame_end = 0
                
                db_avg_val = pydub_audio_chunk_for_db.dBFS if pydub_audio_chunk_for_db.duration_seconds > 0.001 else -999.0
                db_peak_val = pydub_audio_chunk_for_db.max_dBFS if pydub_audio_chunk_for_db.duration_seconds > 0.001 else -999.0
                
                metadata = {
                    "index": actual_segment_index, "file": filename,
                    "frame_start": frame_start, "frame_end": frame_end,
                    "time_start": round(start_time_s, 3), "time_end": round(actual_end_time_s, 3),
                    "fps": round(float(fps), 2),
                    "db_min": f"{db_avg_val:.1f}", "db_max": f"{db_peak_val:.1f}",
                    "result": segment_type,
                    "source_video_processed": os.path.basename(current_video_to_process) # Mantém o nome do vídeo que foi de fato segmentado
                }
                sound_index_content.append(metadata)
                actual_segment_index += 1
            else:
                print(f"  !! Erro FFmpeg para {filename} (cód: {result.returncode}): {result.stderr[:500]}...")
        except FileNotFoundError:
            print(f"!! ERRO CRÍTICO: 'ffmpeg' não encontrado."); video_clip_for_audio.close(); return None, None, None, None
        except Exception as e:
            print(f"  !! Erro subprocesso com FFmpeg para {filename}: {e}")

    video_clip_for_audio.close() # Fecha o objeto MoviePy usado para extração de áudio

    try:
        with open(output_json_path, 'w') as f: json.dump(sound_index_content, f, indent=2)
        print(f"Etapa 1 concluída para '{os.path.basename(video_path_param)}'. Índice salvo em '{output_json_path}'.")
    except Exception as e:
        print(f"Erro ao escrever JSON '{output_json_path}': {e}")
        return current_video_to_process, None, None, sound_index_content

    return current_video_to_process, output_json_path, None, sound_index_content


if __name__ == "__main__":
    # Bloco de teste direto (como no exemplo anterior)
    if len(sys.argv) < 2:
        print("Uso para teste: python pv_step_01_audio_segment.py <video_path> [output_dir] [min_silence_len_ms] [silence_thresh_dbfs] [speech_padding_ms]")
        sys.exit(1)
    
    test_video_path = sys.argv[1]
    test_output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(test_video_path))[0] + "_s1_test_re_encode"
    
    # Usa os defaults definidos no topo do script para os parâmetros de Pydub e padding se não fornecidos
    # (o argparse no pv-process.py fará isso de forma mais elegante)
    test_params = {
        "min_silence_len_ms": int(sys.argv[3]) if len(sys.argv) > 3 else 400, # Usa o default do script
        "silence_thresh_dbfs": int(sys.argv[4]) if len(sys.argv) > 4 else -42, # Usa o default do script
        "speech_start_padding_ms": int(sys.argv[5]) if len(sys.argv) > 5 else 200 # Usa o default do script
    }

    print(f"--- Teste Direto: pv_step_01_audio_segment.py (Modo Re-codificação por Segmento) ---")
    print(f"Vídeo: {test_video_path}, Output: {test_output_dir}")
    print(f"Params: min_silence={test_params['min_silence_len_ms']}, thresh={test_params['silence_thresh_dbfs']}, padding={test_params['speech_start_padding_ms']}")

    if os.path.exists(test_output_dir):
        print(f"Limpando dir de teste: {test_output_dir}...")
        try:
            shutil.rmtree(test_output_dir) # Remove a pasta inteira e recria
        except Exception as e: print(f"Erro ao limpar dir: {e}")
    os.makedirs(test_output_dir, exist_ok=True)

    processed_video, json_path, kf_info, segments_list = segment_video(
        video_path_param=test_video_path,
        output_dir=test_output_dir,
        json_file_name_in_output_dir="sound_index_s1_test.json",
        min_silence_len_ms=test_params['min_silence_len_ms'],
        silence_thresh_dbfs=test_params['silence_thresh_dbfs'],
        speech_start_padding_ms=test_params['speech_start_padding_ms'],
        prompt_user_for_kf_re_encode=False, # Desativa o prompt para este modo de teste
        force_kf_re_encode=False           # Não força re-encode KF do vídeo fonte
    )

    if json_path and segments_list is not None:
        print(f"\n--- Teste Concluído ---")
        print(f"Vídeo Processado (usado para segmentação): {processed_video}")
        print(f"JSON Salvo: {json_path} ({len(segments_list)} segmentos)")
        # kf_info será None nesta versão
        if kf_info: print(f"Info Re-encode KF: {kf_info}") 
    else:
        print("\n--- Teste Falhou ---")