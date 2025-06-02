# pv_utils.py
import os
import json
import subprocess
import bisect
from moviepy.editor import VideoFileClip # Para fallback de info, se ffprobe falhar

def get_extended_video_info(video_path):
    """
    Obtém informações estendidas de um arquivo de vídeo usando ffprobe.
    Retorna um dicionário com: filepath, exists, size_bytes, duration_s, 
                               fps, total_frames, video_stream_info, 
                               audio_stream_info, error.
    """
    if not os.path.isfile(video_path):
        return {
            "filepath": video_path, "exists": False, "size_bytes": 0, 
            "duration_s": 0, "fps": 0, "total_frames": 0, 
            "video_stream_info": None, "audio_stream_info": None, "error": "Arquivo não encontrado"
        }

    size_bytes = os.path.getsize(video_path)
    info = {
        "filepath": video_path, "exists": True, "size_bytes": size_bytes, 
        "duration_s": 0.0, "fps": 0.0, "total_frames": 0,
        "video_stream_info": "N/A", "audio_stream_info": "N/A", "error": None
    }

    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_format', '-show_streams', # Pega informações do formato e dos streams
            '-of', 'json', video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(result.stdout)

        if 'format' in data and 'duration' in data['format']:
            try: info["duration_s"] = float(data['format']['duration'])
            except (ValueError, TypeError): info["error"] = (info["error"] or "") + "Duração do formato inválida. "

        video_stream_details = []
        audio_stream_details = []

        if 'streams' in data:
            for stream in data['streams']:
                if stream.get('codec_type') == 'video':
                    vs_info = f"Codec: {stream.get('codec_name', 'N/A')}, {stream.get('width')}x{stream.get('height')}"
                    if 'r_frame_rate' in stream:
                        try:
                            num, den = map(int, stream['r_frame_rate'].split('/'))
                            if den != 0: 
                                current_fps = num / den
                                vs_info += f", FPS: {current_fps:.2f}"
                                if info["fps"] == 0.0: info["fps"] = current_fps # Pega o FPS do primeiro stream de vídeo
                        except (ValueError, ZeroDivisionError): pass # Ignora se r_frame_rate for inválido
                    
                    if 'nb_frames' in stream and stream['nb_frames'] != 'N/A':
                        try: 
                            current_frames = int(stream['nb_frames'])
                            vs_info += f", Frames: {current_frames}"
                            if info["total_frames"] == 0 : info["total_frames"] = current_frames
                        except ValueError: pass
                    video_stream_details.append(vs_info)

                elif stream.get('codec_type') == 'audio':
                    as_info = f"Codec: {stream.get('codec_name', 'N/A')}, Canais: {stream.get('channels', 'N/A')}, Taxa: {stream.get('sample_rate', 'N/A')}Hz"
                    audio_stream_details.append(as_info)
            
            if not video_stream_details: info["error"] = (info["error"] or "") + "Nenhum stream de vídeo encontrado. "
            if not audio_stream_details: info["audio_stream_info"] = "Nenhum stream de áudio encontrado" # Não é um erro fatal
            
            info["video_stream_info"] = "; ".join(video_stream_details) if video_stream_details else "N/A"
            info["audio_stream_info"] = "; ".join(audio_stream_details) if audio_stream_details else "N/A"

            # Estima total_frames se não foi encontrado diretamente mas temos duração e fps
            if info["total_frames"] == 0 and info["fps"] > 0 and info["duration_s"] > 0:
                info["total_frames"] = int(info["duration_s"] * info["fps"])

    except subprocess.CalledProcessError as e:
        info["error"] = f"Falha na execução do ffprobe: {e.stderr.strip()}"
    except FileNotFoundError:
        info["error"] = "'ffprobe' não encontrado. FFmpeg precisa estar instalado e no PATH."
    except json.JSONDecodeError:
        info["error"] = "Falha ao decodificar a saída JSON do ffprobe."
    except Exception as e_gen:
        info["error"] = f"Erro inesperado ao obter informações do vídeo: {str(e_gen)}"
    
    # Fallback para MoviePy se ffprobe falhou em obter dados essenciais
    if info["duration_s"] == 0.0 or info["fps"] == 0.0:
        if info["error"]: print(f"  Aviso (ffprobe): {info['error']}. Tentando MoviePy para duration/fps...")
        try:
            clip = VideoFileClip(video_path)
            info["duration_s"] = clip.duration if clip.duration is not None else 0.0
            info["fps"] = clip.fps if clip.fps is not None else 0.0
            if info["total_frames"] == 0 and info["fps"] > 0 and info["duration_s"] > 0:
                 info["total_frames"] = int(info["duration_s"] * info["fps"])
            clip.close()
            info["error"] = (info["error"] or "") + "[Info de MoviePy usada como fallback]" if info["error"] else "[Info de MoviePy usada]"
        except Exception as e_mp:
            mp_error = f"Falha ao usar MoviePy como fallback: {str(e_mp)}"
            info["error"] = f"{info['error']} {mp_error}" if info["error"] else mp_error

    return info


def get_video_keyframes(video_path_kf):
    """Usa ffprobe para obter uma lista de timestamps (em segundos) de todos os keyframes."""
    print(f"Mapeando keyframes do vídeo: {os.path.basename(video_path_kf)}...")
    command = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0', '-show_entries', 'frame=key_frame,pkt_pts_time',
        '-of', 'json', video_path_kf
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(result.stdout)
        keyframes = []
        if 'frames' in data:
            for frame_info in data['frames']:
                if int(frame_info.get('key_frame', 0)) == 1 and 'pkt_pts_time' in frame_info:
                    try: keyframes.append(float(frame_info['pkt_pts_time']))
                    except (ValueError, TypeError): pass # Ignora timestamps inválidos
        
        keyframes = sorted(list(set(kf for kf in keyframes if kf >= 0)))
        if not keyframes or (keyframes and keyframes[0] > 0.01 and 0.0 not in keyframes):
            bisect.insort(keyframes, 0.0) # Adiciona 0.0 se não estiver presente e for relevante
        if not keyframes: keyframes = [0.0] # Garante que não está vazia

        print(f"Encontrados {len(keyframes)} keyframes. Primeiro: {keyframes[0]:.3f}s, Último: {keyframes[-1]:.3f}s" if keyframes else "Nenhum keyframe.")
        return keyframes
    except FileNotFoundError:
        print("!! ERRO CRÍTICO: 'ffprobe' não encontrado."); raise
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar ffprobe (JSON) para {os.path.basename(video_path_kf)}: {e.stderr}"); raise
    except json.JSONDecodeError:
        output_stdout = result.stdout if 'result' in locals() and hasattr(result, 'stdout') else 'N/A (sem output capturado)'
        print(f"Erro ao decodificar JSON do ffprobe. Saída: {output_stdout}"); raise
    except Exception as e:
        print(f"Erro inesperado ao obter keyframes (JSON) para {os.path.basename(video_path_kf)}: {e}"); raise

def find_kf_before_or_at(target_time, kf_list_sorted):
    """Encontra o maior keyframe <= target_time."""
    if not kf_list_sorted: return max(0.0, target_time)
    idx = bisect.bisect_right(kf_list_sorted, target_time)
    if idx == 0: return 0.0 
    return kf_list_sorted[idx - 1]

def find_kf_after_or_at(target_time, kf_list_sorted, video_duration_s_ref):
    """Encontra o menor keyframe >= target_time, não excedendo video_duration_s_ref."""
    if not kf_list_sorted: return min(video_duration_s_ref, target_time)
    idx = bisect.bisect_left(kf_list_sorted, target_time)
    if idx == len(kf_list_sorted): return min(kf_list_sorted[-1], video_duration_s_ref)
    return min(kf_list_sorted[idx], video_duration_s_ref)


def re_encode_video_for_keyframes(input_video_path, output_video_path, keyframe_interval_s=1.0):
    """Recodifica o vídeo para forçar keyframes mais frequentes.
    Retorna (True, re_encode_details_dict) em sucesso, ou (False, re_encode_details_dict) em falha.
    """
    print("-" * 50)
    print(f"Iniciando re-codificação de '{os.path.basename(input_video_path)}' para adicionar keyframes...")
    print(f"Novo arquivo será salvo como: '{os.path.basename(output_video_path)}'")
    print("Este processo pode demorar bastante. Por favor, aguarde.")
    print("-" * 50)
    
    re_encode_details = {
        "re_encoded_path": output_video_path, 
        "original_path": input_video_path, 
        "status": "Falhou",
        "new_duration_s": 0, "new_fps": 0, "new_size_bytes": 0
    }
    
    gop_size_str = ""
    try:
        _ , fps_for_gop = get_video_info_ffprobe(input_video_path) # Usa a função unificada
        if fps_for_gop and fps_for_gop > 0:
            gop_size = max(1, int(round(fps_for_gop * keyframe_interval_s)))
            gop_size_str = str(gop_size)
            print(f"  Usando FPS: {fps_for_gop:.2f}, Intervalo KF: {keyframe_interval_s}s => GOP size (parâmetro -g): {gop_size}")
    except Exception as e:
        print(f"  Aviso: Não foi possível obter FPS para calcular GOP size ótimo: {e}")
        print(f"  Usando -force_key_frames a cada {keyframe_interval_s}s como alternativa.")

    # Garante que o diretório de saída para o vídeo recodificado exista
    os.makedirs(os.path.dirname(output_video_path), exist_ok=True)

    re_encode_command = [
        'ffmpeg', '-y', '-i', input_video_path,
        '-c:v', 'libx264', '-preset', 'medium', # 'medium' é um bom equilíbrio
        '-c:a', 'aac', '-b:a', '192k',
    ]
    if gop_size_str:
        re_encode_command.extend(['-g', gop_size_str])
    else: # Fallback
        re_encode_command.extend(['-force_key_frames', f"expr:gte(t,n_forced*{keyframe_interval_s})"])
    re_encode_command.append(output_video_path)
    
    try:
        print(f"Executando FFmpeg para re-codificação: {' '.join(re_encode_command)}")
        result = subprocess.run(re_encode_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if result.returncode == 0:
            print("Re-codificação concluída com sucesso!")
            re_encode_details["status"] = "Sucesso"
            try: # Obter stats do novo arquivo
                new_info = get_extended_video_info(output_video_path)
                re_encode_details["new_duration_s"] = new_info["duration_s"]
                re_encode_details["new_fps"] = new_info["fps"]
                re_encode_details["new_size_bytes"] = new_info["size_bytes"]
            except Exception as e_stat:
                print(f"Aviso: não foi possível obter stats do vídeo recodificado: {e_stat}")
            return True, re_encode_details
        else:
            print("!! Erro durante a re-codificação do vídeo:")
            if result.stderr: print(f"   Stderr: {result.stderr.strip()}")
            return False, re_encode_details
    except FileNotFoundError:
        print("!! ERRO CRÍTICO: 'ffmpeg' não encontrado para re-codificação."); return False, re_encode_details
    except Exception as e:
        print(f"!! Erro inesperado durante a re-codificação: {e}"); return False, re_encode_details