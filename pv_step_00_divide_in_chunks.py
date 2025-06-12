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
    Verifica se os chunks já existem antes de criá-los.
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
    
    base, ext = os.path.splitext(os.path.basename(video_path))
    # Gera a lista de nomes de arquivo que esperamos criar
    expected_chunk_paths = [os.path.join(output_dir, f"{base}_chunk_{i+1:02d}{ext}") for i in range(num_chunks)]

    # === NOVA LÓGICA DE VERIFICAÇÃO ===
    # Verifica se TODOS os chunks esperados já existem
    all_chunks_exist = all(os.path.isfile(p) for p in expected_chunk_paths)
    if all_chunks_exist:
        print(f"  Todos os {num_chunks} chunks esperados já existem. Pulando a etapa de criação.")
        print("--- Etapa 0 Concluída (Arquivos existentes utilizados) ---")
        return expected_chunk_paths
    # ==============================

    print(f"  Vídeo de {original_size_mb:.2f}MB será dividido em {num_chunks} chunks de ~{chunk_duration_s} segundos cada.")
    
    created_chunk_paths = []
    start_time = 0
    
    for i in range(num_chunks):
        if start_time >= duration_s:
            break

        output_path = expected_chunk_paths[i]
        created_chunk_paths.append(output_path)

        # === VERIFICAÇÃO INDIVIDUAL DE CADA CHUNK ===
        if os.path.isfile(output_path):
            print(f"  Chunk {i+1}/{num_chunks}: '{os.path.basename(output_path)}' já existe. Pulando criação.")
            start_time += chunk_duration_s
            continue
        # ============================================
        
        ffmpeg_command = [
            'ffmpeg', '-y',
            '-ss', str(start_time),
            '-i', video_path,
            '-t', str(chunk_duration_s),
            '-c', 'copy',
            output_path
        ]
        
        print(f"  Criando chunk {i+1}/{num_chunks}: {os.path.basename(output_path)}")
        
        try:
            result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                print(f"  !! Erro ao criar chunk {i+1}. Stderr: {result.stderr}")
                return None # Para o processo se um chunk falhar
        except Exception as e:
            print(f"  !! Exceção ao criar chunk {i+1}: {e}")
            return None
            
        start_time += chunk_duration_s

    print(f"--- Etapa 0 Concluída: Criados/Verificados {len(created_chunk_paths)} chunks. ---")
    return created_chunk_paths

# O bloco if __name__ == "__main__" não é estritamente necessário para este módulo,
# pois ele será chamado pelo pv-process.py, mas pode ser útil para testes isolados.