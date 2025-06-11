# pv_step_03_segment_join.py
import os
import subprocess
import sys
import tempfile

def join_segments_from_list(list_of_absolute_segment_filepaths, final_output_filepath):
    """
    Junta uma lista de arquivos de segmento (caminhos absolutos) em um único 
    arquivo de saída usando FFmpeg concat demuxer.
    Retorna True se bem-sucedido, False caso contrário.
    """
    if not list_of_absolute_segment_filepaths:
        print("  ETAPA 3 ERRO: Nenhuma lista de arquivos de segmento fornecida para junção.")
        return False

    temp_file_descriptor, temp_file_list_path = tempfile.mkstemp(text=True, suffix='.txt', prefix='ffmpeg_concat_list_')
    print(f"--- Iniciando Etapa 3: Junção de {len(list_of_absolute_segment_filepaths)} Segmentos ---")
    print(f"  Usando arquivo de lista temporário: {temp_file_list_path}")
    print(f"  Arquivo de saída final: {final_output_filepath}")
    
    try:
        with os.fdopen(temp_file_descriptor, 'w', encoding='utf-8') as fl:
            for seg_path in list_of_absolute_segment_filepaths:
                clean_path = seg_path.replace("\\", "/").replace("'", "'\\''")
                fl.write(f"file '{clean_path}'\n") 
        
        ffmpeg_command = [
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0',            
            '-i', temp_file_list_path,
            '-c:v', 'copy',         # Copia o stream de vídeo
            '-c:a', 'aac',          # Re-codifica o stream de áudio
            '-b:a', '192k',         # Bitrate do áudio
            final_output_filepath
        ]
        
        print(f"  Executando FFmpeg para junção...")
        result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

        if result.returncode == 0:
            print(f"  Junção concluída com sucesso: '{final_output_filepath}'")
            return True
        else:
            print(f"  !! Erro Etapa 3 ao juntar segmentos com FFmpeg.")
            print(f"     STDERR: {result.stderr.strip()}")
            return False

    except Exception as e:
        print(f"!! Erro Etapa 3 inesperado durante a junção: {e}"); return False
    finally:
        if os.path.exists(temp_file_list_path):
            os.remove(temp_file_list_path)

# Bloco para testar este script individualmente
if __name__ == "__main__":
    print("--- Testando pv_step_03_segment_join.py diretamente ---")
    if len(sys.argv) < 3:
        print("Uso para teste: python pv_step_03_segment_join.py <arquivo_de_saida.mp4> <segmento1.mp4> [segmento2.mp4 ...]")
        print("  Os caminhos para os segmentos devem ser válidos.")
        sys.exit(1)

    output_file_test = os.path.abspath(sys.argv[1])
    list_of_segments_test = [os.path.abspath(p) for p in sys.argv[2:]]
    
    # O diretório para o filelist.txt temporário pode ser o diretório do arquivo de saída.
    temp_dir_for_list_test = os.path.dirname(output_file_test) # Ou use tempfile.gettempdir()
    os.makedirs(temp_dir_for_list_test, exist_ok=True)

    print(f"Arquivo de Saída para Teste: {output_file_test}")
    print(f"Segmentos para Teste: {list_of_segments_test}")
    print(f"Diretório para filelist.txt (no teste): {temp_dir_for_list_test}")

    success = join_segments_from_list(list_of_segments_test, output_file_test, temp_dir_for_list_test)

    if success:
        print("\nTeste de junção pv_step_03_segment_join.py CONCLUÍDO COM SUCESSO.")
    else:
        print("\nTeste de junção pv_step_03_segment_join.py FALHOU.")
    print("--- Teste de pv_step_03_segment_join.py Finalizado ---")