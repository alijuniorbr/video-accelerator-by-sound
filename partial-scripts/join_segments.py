import os
import json
import subprocess
import sys

def join_video_segments(segments_dir="audio_segments", 
                        index_file_name="sound_index.json", 
                        output_file_name_base="teste-join"):
    """
    Junta os segmentos de vídeo listados em um arquivo de índice JSON.
    Prioriza o uso de versões "_faster.mp4" para segmentos silenciosos, se existirem.
    """
    full_index_path = os.path.join(segments_dir, index_file_name)
    file_list_path = os.path.join(segments_dir, "filelist_for_concat.txt") # Arquivo temporário

    if not os.path.isdir(segments_dir):
        print(f"Erro: Diretório de segmentos '{segments_dir}' não encontrado.")
        return

    if not os.path.isfile(full_index_path):
        print(f"Erro: Arquivo de índice '{full_index_path}' não encontrado.")
        print(f"Certifique-se de que o script de segmentação foi executado e o JSON está em '{segments_dir}'.")
        return

    try:
        with open(full_index_path, 'r') as f:
            segment_data_list = json.load(f) # Renomeado para clareza
    except Exception as e:
        print(f"Erro ao ler ou parsear o arquivo JSON '{full_index_path}': {e}")
        return

    if not segment_data_list:
        print("Nenhum segmento encontrado no arquivo de índice.")
        return

    segment_data_list.sort(key=lambda x: x.get("index", 0))
    print(f"Preparando para juntar {len(segment_data_list)} segmentos (ou suas versões aceleradas)...")

    files_for_concat_list = []
    used_faster_version = False # Flag para nomear o arquivo final

    for segment_info in segment_data_list:
        original_filename = segment_info.get("file")
        segment_type = segment_info.get("result")

        if not original_filename:
            print(f"  Aviso: Segmento com índice {segment_info.get('index')} não tem nome de arquivo. Pulando.")
            continue

        file_to_include_in_list = original_filename # Default

        if segment_type == "silent":
            # Tenta encontrar a versão "_faster.mp4"
            # Ex: "000000_silent.mp4" -> "000000_faster.mp4"
            base_name_part = original_filename.split('_')[0]
            faster_filename_candidate = f"{base_name_part}_faster.mp4"
            path_to_faster_file = os.path.join(segments_dir, faster_filename_candidate)

            if os.path.isfile(path_to_faster_file):
                print(f"  Segmento '{original_filename}': Usando versão acelerada '{faster_filename_candidate}'.")
                file_to_include_in_list = faster_filename_candidate
                used_faster_version = True
            else:
                print(f"  Segmento '{original_filename}': Versão acelerada não encontrada, usando original.")
        
        files_for_concat_list.append(file_to_include_in_list)

    if not files_for_concat_list:
        print("Nenhum arquivo válido para concatenar após as verificações.")
        return

    # Define o nome do arquivo de saída
    if used_faster_version:
        final_output_filename = f"{output_file_name_base}_com_fast.mp4"
    else:
        final_output_filename = f"{output_file_name_base}_original.mp4"
    final_output_path = os.path.join(segments_dir, final_output_filename)

    try:
        with open(file_list_path, 'w') as fl:
            for filename_in_list in files_for_concat_list:
                # O demuxer concat do FFmpeg espera os caminhos literais dos arquivos.
                # Aspas simples são importantes se os nomes tiverem espaços (não é o caso aqui, mas boa prática).
                fl.write(f"file '{filename_in_list}'\n") 
        
        print(f"Arquivo de lista '{file_list_path}' criado com {len(files_for_concat_list)} arquivos.")

        ffmpeg_command = [
            'ffmpeg',
            '-y',                   
            '-f', 'concat',         
            '-safe', '0',           
            '-i', file_list_path,   
            # '-c', 'copy',           # Copia os streams (sem re-codificar)
            '-c:v', 'copy',         # Copia o stream de vídeo
            '-c:a', 'aac',          # Re-codifica o stream de áudio para AAC
            '-b:a', '192k',         # Define o bitrate do áudio (ex: 192kbps, ajuste se necessário)
            # '-ar', '48000',       # Opcional: Forçar taxa de amostragem se FFmpeg escolher errado
            # '-ac', '2',           # Opcional: Forçar canais de áudio (estéreo) se FFmpeg escolher errado
            final_output_path
        ]

        print(f"Executando FFmpeg para juntar os segmentos em '{final_output_filename}'...")
        print(f"Comando: {' '.join(ffmpeg_command)}")

        result = subprocess.run(ffmpeg_command,
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE,
                                text=True, check=False)

        print(f"--- Iniciando saída FFmpeg para junção ---")
        if result.stdout: print("FFmpeg STDOUT:\n" + result.stdout.strip())
        if result.stderr: print("FFmpeg STDERR:\n" + result.stderr.strip())
        print(f"--- Fim da saída FFmpeg para junção (código de retorno: {result.returncode}) ---")

        if result.returncode == 0:
            print(f"\nSucesso! Segmentos juntados em '{final_output_path}'.")
        else:
            print(f"\n!! Erro ao juntar os segmentos com FFmpeg.")

    except FileNotFoundError:
        print("!! ERRO CRÍTICO: 'ffmpeg' não encontrado. Instale-o e adicione ao PATH.")
    except Exception as e:
        print(f"Ocorreu um erro durante o processo de junção: {e}")
    finally:
        if os.path.exists(file_list_path):
            os.remove(file_list_path)
            print(f"Arquivo de lista temporário '{file_list_path}' removido.")

if __name__ == "__main__":
    default_segments_dir = "audio_segments" 
    
    # Permite passar o diretório dos segmentos como argumento, se necessário
    segments_dir_to_use = sys.argv[1] if len(sys.argv) > 1 else default_segments_dir
    
    if not os.path.isdir(segments_dir_to_use):
        if segments_dir_to_use == default_segments_dir:
            print(f"Erro: Diretório padrão de segmentos '{default_segments_dir}' não encontrado.")
            print("Execute o script de segmentação primeiro ou especifique o diretório correto como argumento.")
        else:
            print(f"Erro: Diretório de segmentos especificado '{segments_dir_to_use}' não encontrado.")
        sys.exit(1)
        
    join_video_segments(segments_dir=segments_dir_to_use)