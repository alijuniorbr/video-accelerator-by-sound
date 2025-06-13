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

def extract_audio_direct_ffmpeg(video_path, temp_audio_path):
    """Usa uma chamada FFmpeg direta para extrair áudio, mostrando o progresso."""
    print(f"  Extraindo áudio para '{os.path.basename(temp_audio_path)}' com FFmpeg direto...")
    # command = [
    #     'ffmpeg', '-y', # Sobrescreve o arquivo temporário se ele existir
    #     '-i', video_path,
    #     '-vn', # Ignora o vídeo
    #     '-acodec', 'pcm_s16le', # Formato WAV padrão (não comprimido)
    #     '-ar', '48000',        # Taxa de amostragem padrão
    #     '-ac', '2',            # Canais padrão (estéreo)
    #     temp_audio_path
    # ]

    # Este comando agora não apenas extrai, mas também re-codifica o áudio,
    # o que pode corrigir erros no stream de áudio de origem.
    command = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vn',                   # Sem vídeo
        '-acodec', 'pcm_s16le',  # Formato de saída (WAV não comprimido)
        '-ar', '48000',          # Taxa de amostragem
        '-ac', '2',              # Canais de áudio (estéreo)
        '-b:a', '1536k',         # Bitrate explícito para WAV estéreo de 16bit/48kHz
        '-af', 'aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo', # Força o formato do filtro de áudio
        temp_audio_path
    ]

    try:
        # Executa o comando e deixa o FFmpeg imprimir seu progresso/erros no terminal
        # A saída de erro do FFmpeg (stderr) contém os logs de progresso.
        # Ao não capturar stdout/stderr, eles são passados para o console.
        subprocess.run(command, check=True, capture_output=False) # check=True lançará erro se FFmpeg falhar
        
        # Carrega o arquivo WAV criado com o Pydub
        audio_segment = AudioSegment.from_wav(temp_audio_path)
        print("  Áudio extraído e carregado com sucesso.")
        return audio_segment
    except subprocess.CalledProcessError as e:
        print(f"  !! Erro FFmpeg ao extrair áudio. O processo pode ter sido interrompido ou o arquivo é inválido.")
        # O stderr do FFmpeg já terá sido impresso no console.
        raise # Levanta a exceção para que a função principal saiba que falhou
    except FileNotFoundError:
        print("!! ERRO CRÍTICO: 'ffmpeg' não encontrado."); raise
    except Exception as e:
        print(f"  !! Erro ao carregar o arquivo WAV com Pydub: {e}"); raise


def segment_video(video_path_param, 
                  output_dir, 
                  json_file_name, 
                  min_silence_len_ms, 
                  silence_thresh_dbfs, 
                  speech_start_padding_ms,
                  speech_end_padding_ms,
                  apply_fade=False,
                  fade_duration_ms=20):
    
    os.makedirs(output_dir, exist_ok=True) 
    output_json_path = os.path.join(output_dir, json_file_name)
    print(f"--- Iniciando Etapa 1: Segmentação para '{os.path.basename(video_path_param)}' ---")

    # Inicialização de variáveis
    duration_s, fps = 0.0, 30.0
    sound_index_content = []

    try:
        if pv_utils:
            video_info = pv_utils.get_extended_video_info(video_path_param)
            if video_info.get("error"): raise ValueError(f"Falha via pv_utils: {video_info.get('error')}")
            duration_s, fps = video_info["duration_s"], video_info["fps"]
        else: # Fallback
            with VideoFileClip(video_path_param) as clip:
                duration_s, fps = clip.duration, clip.fps

        if not fps or fps <= 0: fps = 30.0
        if not duration_s or duration_s <= 0: raise ValueError("Duração inválida.")
        duration_ms = int(duration_s * 1000)
        print(f"Processando vídeo: {os.path.basename(video_path_param)}, Duração: {duration_s:.2f}s, FPS: {fps:.2f}")
    except Exception as e:
        print(f"Falha crítica ao carregar info do vídeo: {e}")
        return None, None, None, None

    # Extração de Áudio usando a nova função robusta
    temp_audio_path = os.path.join(output_dir, f"temp_audio_{os.path.splitext(os.path.basename(video_path_param))[0]}.wav")
    try:
        full_audio_segment = extract_audio_direct_ffmpeg(video_path_param, temp_audio_path)
    except Exception as e:
        print(f"Não foi possível extrair o áudio do vídeo. Abortando esta etapa. Erro: {e}")
        return video_path_param, None, None, None
    finally:
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
    
    print(f"Detectando silêncio (min_len: {min_silence_len_ms}ms, threshold: {silence_thresh_dbfs}dBFS)...")
    silent_chunks_ms = detect_silence(full_audio_segment, min_silence_len_ms, silence_thresh_dbfs, 1)
    
    # ... (O restante da lógica para gerar segmentos com padding, cortar com FFmpeg,
    #      e criar o JSON permanece o mesmo da versão anterior que você me passou,
    #      pois essa parte estava funcionando bem.)
    # (Vou colar o resto para garantir que o arquivo esteja completo)
    
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
        expanded_speech = []
        for seg in initial_segments:
            if seg['type'] == "speech":
                expanded_start = max(0, seg['start_ms'] - speech_start_padding_ms)
                expanded_end = min(duration_ms, seg['end_ms'] + speech_end_padding_ms)
                expanded_speech.append({"start_ms": expanded_start, "end_ms": expanded_end, "type": "speech"})
        
        if expanded_speech:
            merged_speech = [expanded_speech[0].copy()]
            for i in range(1, len(expanded_speech)):
                if expanded_speech[i]['start_ms'] < merged_speech[-1]['end_ms']:
                    merged_speech[-1]['end_ms'] = max(merged_speech[-1]['end_ms'], expanded_speech[i]['end_ms'])
                else:
                    merged_speech.append(expanded_speech[i].copy())
        else: merged_speech = []

        last_end_time_ms = 0
        for speech_seg in merged_speech:
            if speech_seg['start_ms'] > last_end_time_ms:
                final_segments_props.append({"start_ms": last_end_time_ms, "end_ms": speech_seg['start_ms'], "type": "silent"})
            final_segments_props.append(speech_seg)
            last_end_time_ms = speech_seg['end_ms']
        if last_end_time_ms < duration_ms:
            final_segments_props.append({"start_ms": last_end_time_ms, "end_ms": duration_ms, "type": "silent"})
        if not final_segments_props and duration_ms > 0:
            final_segments_props.append({"start_ms": 0, "end_ms": duration_ms, "type": "silent" if not speech_segments else "speech"})
    
    print(f"Gerados {len(final_segments_props)} segmentos finais com padding.")
    
    for seg in final_segments_props:
        start_ms, end_ms = seg['start_ms'], seg['end_ms']
        chunk_start, chunk_end = max(0, min(start_ms, duration_ms)), max(0, min(end_ms, duration_ms))
        seg['audio_chunk'] = full_audio_segment[chunk_start:chunk_end] if chunk_end > chunk_start else AudioSegment.empty()

    # 3. Loop de criação de vídeos com FFmpeg
    sound_index_content = []
    for seg_prop_index, seg_info in enumerate(final_segments_props):
        start_ms, end_ms, segment_type, pydub_audio_chunk = seg_info.values()
        start_time_s = start_ms / 1000.0; actual_end_time_s = min(end_ms / 1000.0, duration_s)
        duration_of_segment_s = actual_end_time_s - start_time_s
        if duration_of_segment_s <= 0.001: continue
        
        actual_segment_index = len(sound_index_content)
        filename = f"{actual_segment_index:06d}_{segment_type}.mp4"
        output_path = os.path.join(output_dir, filename)
        print(f"  Processando segmento {seg_prop_index+1}/{len(final_segments_props)}: {filename} ({duration_of_segment_s:.3f}s)")
        
        ffmpeg_command = [
            'ffmpeg', '-y', '-i', video_path_param, '-ss', str(start_time_s),
            '-t', str(duration_of_segment_s), '-map', '0:v:0?', '-map', '0:a:0?', 
            '-c:v', 'libx264', '-preset', 'ultrafast', '-force_key_frames', "expr:eq(n,0)", 
            '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
        ]
        if apply_fade and seg_info['type'] == 'speech':
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
                    "index": actual_segment_index, "file": filename, "frame_start": math.floor(start_time_s * fps), 
                    "frame_end": math.floor(actual_end_time_s * fps) -1, "time_start": round(start_time_s, 3), 
                    "time_end": round(actual_end_time_s, 3), "fps": round(float(fps), 2),
                    "db_min": f"{pydub_audio_chunk.dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}", 
                    "db_max": f"{pydub_audio_chunk.max_dBFS if pydub_audio_chunk.duration_seconds > 0.001 else -999.0:.1f}",
                    "result": seg_info['type']}
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

# if __name__ == "__main__": (bloco de teste)