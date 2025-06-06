import os
import json
import sys
import math
import subprocess
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
from pydub.silence import detect_silence

# Parâmetros Configuráveis no Topo da Função Principal ou como Constantes
MIN_SILENCE_LEN_MS = 2000      # Duração mínima para um silêncio ser considerado um "bloco"
SILENCE_THRESH_DBFS = -35      # Limiar de silêncio. Mais negativo = mais sensível à fala.
SPEECH_START_PADDING_MS = 200  # Quanto antes um segmento de FALA deve começar (ms)

def create_segments_final_attempt(video_path, output_dir="audio_segments", json_file_name="sound_index.json"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    full_json_path = os.path.join(output_dir, json_file_name)

    print(f"Segmentos (re-codificados) serão salvos em: '{os.path.abspath(output_dir)}'")
    print(f"Índice JSON será salvo como: '{os.path.abspath(full_json_path)}'")

    try:
        video_clip_obj = VideoFileClip(video_path)
        fps = video_clip_obj.fps
        duration_s = video_clip_obj.duration
        duration_ms = int(duration_s * 1000)
        print(f"Vídeo carregado: {os.path.basename(video_path)}, Duração: {duration_s:.2f}s, FPS: {fps:.2f}")
    except Exception as e:
        print(f"Erro ao carregar o vídeo com MoviePy: {e}"); return

    temp_audio_path_for_pydub = "temp_full_audio_for_pydub.wav"
    try:
        print("Extraindo áudio completo para análise com Pydub...")
        video_clip_obj.audio.write_audiofile(temp_audio_path_for_pydub, codec='pcm_s16le', logger=None)
        full_audio_segment = AudioSegment.from_wav(temp_audio_path_for_pydub)
        print("Áudio completo extraído com sucesso.")
    except Exception as e:
        print(f"Erro ao extrair ou carregar áudio completo para Pydub: {e}")
        if os.path.exists(temp_audio_path_for_pydub): os.remove(temp_audio_path_for_pydub)
        video_clip_obj.close(); return
    finally:
        if os.path.exists(temp_audio_path_for_pydub): os.remove(temp_audio_path_for_pydub)

    print(f"Detectando silêncio (min_len: {MIN_SILENCE_LEN_MS}ms, threshold: {SILENCE_THRESH_DBFS}dBFS)...")
    silent_chunks_ms = detect_silence(
        full_audio_segment,
        min_silence_len=MIN_SILENCE_LEN_MS,
        silence_thresh=SILENCE_THRESH_DBFS,
        seek_step=1 # seek_step padrão
    )
    print(f"Detectados {len(silent_chunks_ms)} trechos de silêncio (análise de áudio).")

    # 1. Gerar lista inicial de segmentos contíguos (sem padding ainda)
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
        if not initial_segments_props and duration_ms > 0:
             initial_segments_props.append({"start_ms": 0, "end_ms": duration_ms, "type": "speech"})
    print(f"Gerados {len(initial_segments_props)} segmentos iniciais baseados em áudio.")

    # 2. Aplicar padding ao início dos segmentos de fala, ajustando o final dos silêncios anteriores
    segments_with_padding = []
    if initial_segments_props:
        # Adiciona o primeiro segmento, aplicando padding se for fala
        first_seg = initial_segments_props[0]
        s_start = first_seg['start_ms']
        s_end = first_seg['end_ms']
        s_type = first_seg['type']
        if s_type == "speech":
            s_start = max(0, s_start - SPEECH_START_PADDING_MS)
        if s_end > s_start:
            segments_with_padding.append({"start_ms": s_start, "end_ms": s_end, "type": s_type})

        # Itera sobre os segmentos restantes para ajustar o início da fala e o fim do silêncio anterior
        for i in range(1, len(initial_segments_props)):
            current_seg_info = initial_segments_props[i]
            s_start = current_seg_info['start_ms']
            s_end = current_seg_info['end_ms']
            s_type = current_seg_info['type']

            prev_processed_seg = segments_with_padding[-1]

            if s_type == "speech":
                adjusted_s_start = max(0, s_start - SPEECH_START_PADDING_MS)
                # Ajusta o fim do segmento anterior (que deve ser silêncio)
                if prev_processed_seg['type'] == 'silent':
                    prev_processed_seg['end_ms'] = max(prev_processed_seg['start_ms'], adjusted_s_start)
                s_start = adjusted_s_start
            else: # current_seg é silêncio
                # O início do silêncio é o fim do segmento de fala anterior (que já foi adicionado)
                s_start = prev_processed_seg['end_ms']
            
            if s_end > s_start: # Adiciona o segmento atual se ainda tiver duração
                segments_with_padding.append({"start_ms": s_start, "end_ms": s_end, "type": s_type})
        
        # Refiltrar para remover segmentos que ficaram com duração zero/negativa e garantir contiguidade
        final_segments_props = []
        last_end_time = 0
        for seg_info in segments_with_padding:
            start_ms = max(last_end_time, seg_info['start_ms']) # Garante contiguidade
            end_ms = seg_info['end_ms']
            
            if end_ms > start_ms: # Apenas se tiver duração positiva
                final_segments_props.append({
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "type": seg_info['type'],
                    "audio_chunk": full_audio_segment[start_ms : end_ms] # Fatia o áudio com os tempos finais
                })
                last_end_time = end_ms
        segments_props = final_segments_props
    else:
        segments_props = []
    print(f"Gerados {len(segments_props)} segmentos com padding aplicado e contiguidade verificada.")

    min_segment_duration_ms_val = (1000 / fps) if fps > 0 else 16 
    final_segments_to_process = []
    if segments_props:
        for s_info in segments_props:
            if (s_info["end_ms"] - s_info["start_ms"]) >= min_segment_duration_ms_val:
                final_segments_to_process.append(s_info)
    segments_props = final_segments_to_process
    print(f"Total de segmentos finais a serem processados com FFmpeg: {len(segments_props)}")

    sound_index_data = []
    actual_segment_index = 0 

    for seg_prop_index, seg_info in enumerate(segments_props):
        start_ms = seg_info["start_ms"]
        end_ms = seg_info["end_ms"]
        segment_type = seg_info["type"]
        pydub_audio_chunk = seg_info["audio_chunk"]

        start_time_s = start_ms / 1000.0
        actual_end_time_s = min(end_ms / 1000.0, duration_s)
        duration_of_segment_s = actual_end_time_s - start_time_s

        if duration_of_segment_s < (min_segment_duration_ms_val / 2000.0) : 
            print(f"  Pulando segmento {seg_prop_index+1}/{len(segments_props)} com duração desprezível para FFmpeg: {duration_of_segment_s:.3f}s.")
            continue
        
        filename = f"{actual_segment_index:06d}_{segment_type}.mp4"
        output_path = os.path.join(output_dir, filename)

        print(f"Processando segmento {seg_prop_index+1}/{len(segments_props)}: {filename} ({duration_of_segment_s:.3f}s)")
        
        ffmpeg_command = [
            'ffmpeg', '-y', 
            '-i', video_path,
            '-ss', str(start_time_s),
            '-t', str(duration_of_segment_s),
            '-map', '0:v:0?', 
            '-map', '0:a:0?', 
            '-c:v', 'libx264',      
            '-preset', 'ultrafast', 
            '-force_key_frames', "expr:eq(n,0)", 
            '-c:a', 'aac',          
            '-b:a', '192k',
            '-ar', '48000',
            '-ac', '2',
            output_path
        ]

        # Adicionar filtro de áudio fade para suavizar transições
        fade_duration_s = 0.12 # 120 milissegundos. Você pode tentar 0.01 (10ms) ou 0.03 (30ms) se necessário.
        if duration_of_segment_s > (2 * fade_duration_s) + 0.001: # Garante espaço para fade in e out
            # Calcula o tempo de início do fade-out para que ele termine exatamente no fim do segmento
            fade_out_start_time = duration_of_segment_s - fade_duration_s
            
            # audio_filter_string = f"afade=type=in:start_time=0:duration={fade_duration_s},afade=type=out:start_time={fade_out_start_time:.3f}:duration={fade_duration_s}"
            # ffmpeg_command.extend(['-af', audio_filter_string])
            print(f"    CANCELADO - Aplicando fade in/out de {fade_duration_s}s.")
        else:
            print(f"    Segmento muito curto ({duration_of_segment_s:.3f}s) para fades completos. Nenhum fade aplicado.")
        
        try:
            result = subprocess.run(ffmpeg_command,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, check=False)

            print(f"--- Iniciando saída FFmpeg para {filename} ---")
            if result.stdout: print("FFmpeg STDOUT:\n" + result.stdout.strip())
            if result.stderr: print("FFmpeg STDERR:\n" + result.stderr.strip()) # FFmpeg usa stderr para logs
            print(f"--- Fim da saída FFmpeg para {filename} (código de retorno: {result.returncode}) ---")

            if result.returncode == 0:
                print(f"  Segmento {filename} parece ter sido criado com sucesso.")
                frame_start = math.floor(start_time_s * fps)
                frame_end = math.floor(actual_end_time_s * fps) -1 
                if frame_end < frame_start:
                    if actual_end_time_s > start_time_s: frame_end = frame_start
                    elif frame_start == 0 and (actual_end_time_s * fps < 1 if fps > 0 else True) : frame_end = 0
                
                db_avg_val = pydub_audio_chunk.dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0
                db_peak_val = pydub_audio_chunk.max_dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0
                
                metadata = {
                    "index": actual_segment_index, "file": filename,
                    "frame_start": frame_start, "frame_end": frame_end,
                    "time_start": round(start_time_s, 3), "time_end": round(actual_end_time_s, 3),
                    "fps": round(float(fps), 2),
                    "db_min": f"{db_avg_val:.1f}", "db_max": f"{db_peak_val:.1f}",
                    "result": segment_type
                }
                sound_index_data.append(metadata)
                actual_segment_index += 1
            else:
                print(f"!! FFmpeg FALHOU para {filename}. O segmento pode não ter sido criado ou está corrompido.")
        except FileNotFoundError:
            print(f"!! ERRO CRÍTICO: 'ffmpeg' não encontrado. Instale-o e adicione ao PATH.")
            video_clip_obj.close(); return 
        except Exception as e:
            print(f"!! Erro de subprocesso com FFmpeg para {filename}: {e}")

    video_clip_obj.close()

    try:
        with open(full_json_path, 'w') as f: json.dump(sound_index_data, f, indent=2)
        print(f"\nSucesso! Processados {len(segments_props)} segmentos propostos, criados {len(sound_index_data)} arquivos em '{os.path.abspath(output_dir)}'.")
        print(f"Índice salvo em '{os.path.abspath(full_json_path)}'.")
    except Exception as e:
        print(f"Erro ao escrever JSON '{full_json_path}': {e}")
    return sound_index_data

def main():
    if len(sys.argv) < 2:
        print("Uso: python nome_do_script.py <caminho_para_o_video>")
        return
    video_file = sys.argv[1]
    if not os.path.isfile(video_file):
        print(f"Erro: Vídeo '{video_file}' não encontrado.")
        return

    output_segment_dir = "audio_segments" 
    json_filename = "sound_index.json" 
    
    if os.path.exists(output_segment_dir) and any(os.scandir(output_segment_dir)):
        while True:
            user_clear = input(f"Diretório de saída '{output_segment_dir}' já existe e contém arquivos. Limpar? (s/n): ").strip().lower()
            if user_clear in ['s', 'n']: break
            print("Opção inválida.")
        if user_clear == 's':
            print(f"Limpando diretório de saída: {output_segment_dir}...")
            for item in os.listdir(output_segment_dir):
                item_path = os.path.join(output_segment_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path): os.unlink(item_path)
                except Exception as e: print(f"  Não foi possível remover {item_path}: {e}")
            print(f"Diretório limpo.")
        else:
            print("Continuando sem limpar o diretório. Arquivos podem ser sobrescritos.")
            
    # Chama a função com os parâmetros configuráveis no topo do script
    create_segments_final_attempt(video_file, output_segment_dir, json_filename)

if __name__ == "__main__":
    main()