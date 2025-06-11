# pv_step_00_divide_in_chunks.py
import os
import math
import subprocess
import sys

try:
    import pv_utils
except ImportError:
    print("ERRO: O arquivo pv_utils.py não foi encontrado.")
    sys.exit(1)

def divide_in_chunks(video_path, output_dir, chunk_size_mb=500):
    """
    Divide um vídeo em chunks de aproximadamente chunk_size_mb.
    Usa -c copy para ser rápido e sem perdas.
    Retorna a lista de caminhos dos chunks criados.
    """
    print(f"--- Iniciando Etapa 0: Divisão em Chunks para '{os.path.basename(video_path)}' ---")
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        video_info = pv_utils.get_extended_video_info(video_path)
        if video_info.get("error"):
            raise ValueError(f"Não foi possível obter informações do vídeo: {video_info['error']}")
    except Exception as e:
        print(f"  Erro: {e}. Não é possível dividir o vídeo.")
        return None

    original_size_mb = video_info.get("size_bytes", 0) / (1024 * 1024)
    duration_s = video_info.get("duration_s", 0)
    
    # Se o vídeo já for menor que o tamanho alvo + uma margem de 10%, não divide.
    if original_size_mb <= (chunk_size_mb * 1.1):
        print(f"  Vídeo de {original_size_mb:.1f}MB já está dentro do limite de tamanho ({chunk_size_mb}MB). Divisão não necessária.")
        return [video_path] # Retorna o caminho original em uma lista

    if duration_s <= 0:
        print("  Erro: Duração do vídeo é zero. Não é possível dividir.")
        return None

    num_chunks = math.ceil(original_size_mb / chunk_size_mb)
    chunk_duration_s = math.ceil(duration_s / num_chunks)
    
    print(f"  Vídeo de {original_size_mb:.2f}MB será dividido em {num_chunks} chunks de ~{chunk_duration_s} segundos cada.")
    
    chunk_paths = []
    start_time = 0
    base, ext = os.path.splitext(os.path.basename(video_path))
    
    for i in range(num_chunks):
        if start_time >= duration_s:
            break # Evita criar chunks vazios se os cálculos arredondarem para cima

        chunk_filename = f"{base}_chunk_{i+1:02d}{ext}"
        output_path = os.path.join(output_dir, chunk_filename)
        chunk_paths.append(output_path)
        
        ffmpeg_command = [
            'ffmpeg', '-y',
            '-ss', str(start_time),  # Definir start time ANTES de -i para usar "input seeking", que é muito rápido
            '-i', video_path,
            '-t', str(chunk_duration_s),
            '-c', 'copy', # Importante: Copia os streams sem re-codificar
            output_path
        ]
        
        print(f"  Criando chunk {i+1}/{num_chunks}: {chunk_filename}")
        
        try:
            result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                print(f"  !! Erro ao criar chunk {i+1}: {result.stderr}")
                return None # Para o processo se um chunk falhar
        except Exception as e:
            print(f"  !! Exceção ao criar chunk {i+1}: {e}")
            return None
            
        start_time += chunk_duration_s

    print(f"--- Etapa 0 Concluída: Criados {len(chunk_paths)} chunks. ---")
    return chunk_paths