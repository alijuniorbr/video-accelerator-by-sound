# pv_step_01_audio_segment.py
import os
import json
import sys
import math
import subprocess
import bisect
from pydub import AudioSegment
from pydub.silence import detect_silence

# Importa as funções auxiliares
try:
    import pv_utils
except ImportError:
    print("ERRO: pv_utils.py não encontrado.")
    sys.exit(1)

def extract_audio_direct_ffmpeg(video_path, temp_audio_path):
    """Usa uma chamada FFmpeg direta para extrair áudio, pode ser mais eficiente."""
    print(f"Extraindo áudio para '{os.path.basename(temp_audio_path)}' com FFmpeg direto...")
    command = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vn', # Sem vídeo
        '-acodec', 'pcm_s16le', # Formato WAV não comprimido
        '-ar', '48000', # Taxa de amostragem
        '-ac', '2',     # Canais (estéreo)
        temp_audio_path
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return AudioSegment.from_wav(temp_audio_path)
    except subprocess.CalledProcessError as e:
        print(f"Erro FFmpeg ao extrair áudio: {e.stderr}")
        raise
    except Exception as e:
        print(f"Erro ao carregar áudio WAV com Pydub: {e}")
        raise

def segment_video(video_path_param, 
                  output_dir, 
                  json_file_name_in_output_dir, 
                  min_silence_len_ms, 
                  silence_thresh_dbfs, 
                  speech_start_padding_ms,
                  # Novos parâmetros para controle
                  processing_mode='recode', # 'recode' ou 'fast'
                  apply_fade=False,
                  prompt_user_for_kf_re_encode=True):
    """
    Função principal para segmentar um vídeo com modo selecionável.
    - mode='recode': Re-codifica cada segmento, permite filtros (fades). Mais lento, mais compatível.
    - mode='fast': Tenta cortar sem re-codificação (-codec copy), baseado em keyframes. Rápido, mas depende de keyframes no vídeo fonte.
    """
    
    os.makedirs(output_dir, exist_ok=True) 
    output_json_path = os.path.join(output_dir, json_file_name_in_output_dir)
    print(f"--- Iniciando Etapa 1: Segmentação para '{os.path.basename(video_path_param)}' ---")
    print(f"   Modo de Processamento: '{processing_mode.upper()}'" + (" com Fades de Áudio" if apply_fade and processing_mode == 'recode' else ""))
    print(f"   Segmentos e índice serão salvos em: '{os.path.abspath(output_dir)}'")

    current_video_to_process = video_path_param
    kf_re_encode_details = None

    try:
        video_info = pv_utils.get_extended_video_info(current_video_to_process)
        if video_info.get("error"): raise ValueError(f"Falha ao obter info: {video_info['error']}")
        duration_s, fps = video_info["duration_s"], video_info["fps"]
        if not all([duration_s, fps]): raise ValueError("Duração ou FPS inválidos.")
    except Exception as e:
        print(f"Falha crítica ao obter informações: {e}"); return None, None, None, None

    # Lógica de Keyframe (relevante para o modo 'fast' ou se o usuário for questionado)
    keyframes_s = []
    if processing_mode == 'fast':
        try:
            keyframes_s = pv_utils.get_video_keyframes(current_video_to_process)
            num_kfs = len(keyframes_s) if keyframes_s else 0
            avg_interval = duration_s / num_kfs if num_kfs > 0 else float('inf')
            is_sparse_kf = (avg_interval > 3.0) or (num_kfs <= 5 and duration_s > 10.0)

            if is_sparse_kf and prompt_user_for_kf_re_encode:
                print("-" * 50)
                print(f"ATENÇÃO: Modo 'fast' (-c copy) selecionado, mas o vídeo tem poucos keyframes (1 a cada {avg_interval:.1f}s).")
                print("Para o modo 'fast' funcionar bem, keyframes frequentes são necessários.")
                print("Recomenda-se (r)ecodificar o vídeo inteiro primeiro ou usar o modo de processamento 'recode'.")
                print("-" * 50)
                # (Lógica do prompt para re-codificar aqui, como na versão anterior, se desejado)
                # ...
                # Se recodificar, atualiza current_video_to_process, duration_s, fps, e re-mapeia keyframes_s
                # Para simplificar, vamos apenas avisar. A re-codificação interativa fica no pv-process.py
        except Exception as e:
            print(f"Aviso: Falha ao analisar keyframes para o modo 'fast': {e}. O resultado pode ser inesperado.")
    
    # Extração de Áudio e Análise Pydub
    temp_audio_path = os.path.join(output_dir, f"temp_audio_{os.path.splitext(os.path.basename(current_video_to_process))[0]}.wav")
    try:
        full_audio_segment = extract_audio_direct_ffmpeg(current_video_to_process, temp_audio_path)
    except Exception as e:
        print(f"Erro ao extrair áudio: {e}"); return None, None, None, None
    finally:
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)

    # ... (Lógica para gerar, preencher e ajustar `segments_props` como antes) ...
    # (Vou colar a lógica de padding que já funcionou para você)
    silent_chunks_ms = detect_silence(full_audio_segment, min_silence_len_ms, silence_thresh_dbfs, 1)
    print(f"Detectados {len(silent_chunks_ms)} trechos de silêncio (análise de áudio).")
    initial_audio_segments = []
    current_time_ms = 0
    duration_ms = int(duration_s * 1000)
    if duration_ms > 0:
        if not silent_chunks_ms: initial_audio_segments.append({"start_ms": 0, "end_ms": duration_ms, "type": "speech"})
        else:
            for silent_start, silent_end in silent_chunks_ms:
                if silent_start > current_time_ms: initial_audio_segments.append({"start_ms": current_time_ms, "end_ms": silent_start, "type": "speech"})
                if silent_end > silent_start: initial_audio_segments.append({"start_ms": silent_start, "end_ms": silent_end, "type": "silent"})
                current_time_ms = silent_end
            if current_time_ms < duration_ms: initial_audio_segments.append({"start_ms": current_time_ms, "end_ms": duration_ms, "type": "speech"})
        initial_audio_segments = [s for s in initial_audio_segments if s["end_ms"] > s["start_ms"]]
        if not initial_audio_segments : initial_audio_segments.append({"start_ms": 0, "end_ms": duration_ms, "type": "speech"})
    
    # Aplicar padding
    padded_segments = []
    if initial_audio_segments:
        # Primeiro segmento
        first_seg = initial_audio_segments[0].copy(); s_start, s_end, s_type = first_seg['start_ms'], first_seg['end_ms'], first_seg['type']
        if s_type == "speech": s_start = max(0, s_start - speech_start_padding_ms)
        if s_end > s_start: padded_segments.append({"start_ms": s_start, "end_ms": s_end, "type": s_type})
        # Segmentos restantes
        for i in range(1, len(initial_audio_segments)):
            current_s_info = initial_audio_segments[i].copy(); s_start_orig, s_end_curr, s_type_curr = current_s_info['start_ms'], current_s_info['end_ms'], current_s_info['type']
            prev_padded_seg = padded_segments[-1] if padded_segments else None
            current_s_start_final = s_start_orig
            if s_type_curr == "speech":
                current_s_start_final = max(0, s_start_orig - speech_start_padding_ms)
                if prev_padded_seg and prev_padded_seg['type'] == 'silent': prev_padded_seg['end_ms'] = max(prev_padded_seg['start_ms'], current_s_start_final)
            elif prev_padded_seg: current_s_start_final = prev_padded_seg['end_ms']
            if s_end_curr > current_s_start_final:
                if prev_padded_seg and prev_padded_seg['end_ms'] <= prev_padded_seg['start_ms']:
                    if padded_segments and segments_with_padding[-1] is prev_padded_seg: padded_segments.pop()
                padded_segments.append({"start_ms": current_s_start_final, "end_ms": s_end_curr, "type": s_type_curr})
        # Atribui audio_chunk e filtra novamente
        audio_based_segments_props_final = []
        last_segment_end_ms = 0
        for seg in padded_segments:
            start_ms = max(last_segment_end_ms, seg['start_ms'])
            end_ms = seg['end_ms']
            if end_ms > start_ms:
                audio_chunk = full_audio_segment[max(0, min(start_ms, duration_ms)):max(0, min(end_ms, duration_ms))]
                audio_based_segments_props_final.append({"start_ms": start_ms, "end_ms": end_ms, "type": seg['type'], "audio_chunk": audio_chunk})
                last_segment_end_ms = end_ms
        segments_props = audio_based_segments_props_final
    else: segments_props = []
    print(f"Gerados {len(segments_props)} segmentos de áudio com padding.")
    # Fim da lógica de preparação de segmentos

    # -----------------------------------------------------------------------------------
    # Loop de criação de vídeos
    sound_index_data_content = []
    actual_segment_index = 0
    final_segments_to_process = segments_props # Renomeado para clareza

    for seg_prop_index, seg_info in enumerate(final_segments_to_process):
        start_ms, end_ms, segment_type = seg_info["start_ms"], seg_info["end_ms"], seg_info["type"]
        pydub_audio_chunk = seg_info["audio_chunk"]

        # Se modo for 'fast', ajusta para keyframes
        if processing_mode == 'fast':
            start_time_s = pv_utils.find_kf_before_or_at(start_ms / 1000.0, keyframes_s)
            end_time_s = pv_utils.find_kf_after_or_at(end_ms / 1000.0, keyframes_s, duration_s)
        else: # modo 'recode'
            start_time_s = start_ms / 1000.0
            end_time_s = min(end_ms / 1000.0, duration_s)

        duration_of_segment_s = end_time_s - start_time_s
        if duration_of_segment_s <= 0.001: continue
        
        filename = f"{actual_segment_index:06d}_{segment_type}.mp4"
        output_path = os.path.join(output_dir, filename)
        print(f"  Processando seg {seg_prop_index+1}/{len(final_segments_to_process)}: {filename} ({duration_of_segment_s:.3f}s)")
        
        # Monta o comando FFmpeg com base no modo escolhido
        ffmpeg_command = ['ffmpeg', '-y']
        if processing_mode == 'fast':
            ffmpeg_command.extend(['-ss', str(start_time_s), '-i', current_video_to_process,
                                   '-t', str(duration_of_segment_s), '-codec', 'copy', 
                                   '-avoid_negative_ts', 'make_zero'])
        else: # 'recode'
            ffmpeg_command.extend(['-i', current_video_to_process, '-ss', str(start_time_s),
                                   '-t', str(duration_of_segment_s),
                                   '-map', '0:v:0?', '-map', '0:a:0?', 
                                   '-c:v', 'libx264', '-preset', 'ultrafast',
                                   '-force_key_frames', "expr:eq(n,0)", 
                                   '-c:a', 'aac', '-b:a', '192k',
                                   '-ar', '48000', '-ac', '2'])
            if apply_fade:
                fade_duration_s = 0.02
                if duration_of_segment_s > (2 * fade_duration_s) + 0.001:
                    fade_out_start = duration_of_segment_s - fade_duration_s
                    audio_filter = f"afade=t=in:st=0:d={fade_duration_s},afade=t=out:st={fade_out_start:.3f}:d={fade_duration_s}"
                    ffmpeg_command.extend(['-af', audio_filter])

        ffmpeg_command.append(output_path)
        
        # Execução e tratamento de erro (como antes)
        try:
            result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if result.returncode == 0:
                # ... (cálculo de metadata e append em sound_index_data_content)
                metadata = {
                    "index": actual_segment_index, "file": filename,
                    "frame_start": math.floor(start_time_s * fps), "frame_end": math.floor(end_time_s * fps) -1,
                    "time_start": round(start_time_s, 3), "time_end": round(end_time_s, 3),
                    "fps": round(float(fps), 2),
                    "db_min": f"{pydub_audio_chunk.dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}", 
                    "db_max": f"{pydub_audio_chunk.max_dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}",
                    "result": segment_type,
                    "processing_mode": processing_mode
                }
                sound_index_data_content.append(metadata)
                actual_segment_index += 1
            else:
                print(f"  !! Erro FFmpeg para {filename}: {result.stderr[:500]}...")
        except Exception as e:
            print(f"  !! Erro subprocesso com FFmpeg para {filename}: {e}")

    # ... (Fecha video_clip_obj_final, escreve JSON e retorna)
    video_clip_obj_final.close()
    try:
        with open(output_json_path, 'w') as f: json.dump(sound_index_data_content, f, indent=2)
        print(f"Etapa 1 concluída. Índice salvo em '{output_json_path}'.")
    except Exception as e:
        print(f"Erro ao escrever JSON '{output_json_path}': {e}")
        return current_video_to_process, None, None, None

    return current_video_to_process, output_json_path, None, sound_index_data_content


if __name__ == "__main__":
    # Bloco de teste direto
    # Exemplo: python pv_step_01_audio_segment.py recode video.mov --fade
    parser = argparse.ArgumentParser(description="Teste direto do script de segmentação.")
    parser.add_argument("mode", choices=['recode', 'fast'], help="Modo de processamento: 'recode' ou 'fast' (baseado em keyframes).")
    parser.add_argument("video_path", help="Caminho para o vídeo de teste.")
    parser.add_argument("--fade", action='store_true', help="Aplicar fades de áudio (apenas no modo 'recode').")
    args_test = parser.parse_args()

    test_output_dir = os.path.splitext(os.path.basename(args_test.video_path))[0] + f"_s1_test_{args_test.mode}"
    if os.path.exists(test_output_dir):
        print(f"Limpando dir de teste: {test_output_dir}...")
        shutil.rmtree(test_output_dir)
    os.makedirs(test_output_dir)

    segment_video(
        video_path_param=args_test.video_path,
        output_dir=test_output_dir,
        json_file_name_in_output_dir="sound_index_test.json",
        min_silence_len_ms=2000,
        silence_thresh_dbfs=-35,
        speech_start_padding_ms=200,
        processing_mode=args_test.mode,
        apply_fade=args_test.fade,
        prompt_user_for_kf_re_encode=True
    )