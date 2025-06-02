# pv_step_03_segment_join.py
import os
import subprocess
import sys
import tempfile # Para criar o filelist.txt em um local temporário seguro

def join_segments_from_list(list_of_absolute_segment_filepaths, 
                            final_output_filepath, 
                            segments_dir_for_filelist="."): # <--- VERIFIQUE ESTE TERCEIRO PARÂMETRO
    """
    Junta uma lista de arquivos de segmento (caminhos absolutos) em um único 
    arquivo de saída usando FFmpeg concat demuxer.
    O filelist.txt é criado no segments_dir_for_filelist.
    Retorna True se bem-sucedido, False caso contrário.
    """
    if not list_of_absolute_segment_filepaths:
        print("  ETAPA 3 ERRO: Nenhuma lista de arquivos de segmento fornecida para junção.")
        return False

    # Usa um arquivo temporário nomeado para a lista de arquivos do FFmpeg
    temp_file_list_descriptor, temp_file_list_path = tempfile.mkstemp(text=True, suffix='.txt', prefix='ffmpeg_concat_list_')
    
    # Usa o diretório do arquivo de saída para o arquivo de lista temporário se segments_dir_for_filelist for "."
    # Isso é mais para o caso de teste direto. No pv-process.py, passamos um diretório específico.
    effective_file_list_dir = segments_dir_for_filelist
    if segments_dir_for_filelist == ".":
        effective_file_list_dir = os.path.dirname(final_output_filepath) # Coloca perto do output
        os.makedirs(effective_file_list_dir, exist_ok=True)

    # Recria o temp_file_list_path no diretório efetivo, se necessário
    # A maneira como tempfile.mkstemp funciona já cria o arquivo. Vamos usá-lo como está.
    # Se você quiser controlar o diretório do tempfile.mkstemp:
    # temp_file_list_descriptor, temp_file_list_path = tempfile.mkstemp(dir=effective_file_list_dir, text=True, suffix='.txt', prefix='ffmpeg_concat_list_')


    print(f"--- Iniciando Etapa 3: Junção de {len(list_of_absolute_segment_filepaths)} Segmentos ---")
    print(f"  Usando arquivo de lista temporário: {temp_file_list_path}")
    print(f"  Arquivo de saída final: {final_output_filepath}")
    
    try:
        with os.fdopen(temp_file_list_descriptor, 'w') as fl: # Abre o descritor de arquivo como um objeto de arquivo
            for seg_path in list_of_absolute_segment_filepaths:
                # Escreve caminhos absolutos no filelist, o que é mais seguro.
                # Aspas simples são boas se os caminhos puderem ter espaços.
                fl.write(f"file '{seg_path.replace(os.sep, '/')}'\n") # Garante barras / para FFmpeg
        
        ffmpeg_command = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',            
            '-i', temp_file_list_path, # Usa o arquivo de lista temporário
            '-c:v', 'copy',          
            '-c:a', 'aac',           
            '-b:a', '192k',          
            final_output_filepath
        ]
        
        print(f"  Executando FFmpeg para junção: {' '.join(ffmpeg_command)}")
        # Não precisa de cwd aqui, pois filelist.txt agora usa caminhos absolutos ou caminhos que o FFmpeg entenda
        result = subprocess.run(ffmpeg_command,
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE,
                                text=True, check=False)

        print(f"  --- Iniciando saída FFmpeg para junção ({os.path.basename(final_output_filepath)}) ---")
        if result.stdout: print("  FFmpeg STDOUT:\n" + result.stdout.strip())
        if result.stderr: print("  FFmpeg STDERR:\n" + result.stderr.strip())
        print(f"  --- Fim da saída FFmpeg (código de retorno: {result.returncode}) ---")

        if result.returncode == 0:
            print(f"  Junção concluída com sucesso: '{final_output_filepath}'")
            return True
        else:
            print(f"  !! Erro Etapa 3 ao juntar segmentos com FFmpeg (código: {result.returncode}).")
            return False

    except FileNotFoundError:
        print("!! ERRO CRÍTICO Etapa 3: 'ffmpeg' não encontrado."); return False
    except Exception as e:
        print(f"!! Erro Etapa 3 inesperado durante a junção: {e}"); return False
    finally:
        if os.path.exists(temp_file_list_path):
            try:
                os.remove(temp_file_list_path)
                # print(f"  Arquivo de lista temporário '{temp_file_list_path}' removido.")
            except Exception as e_rem:
                print(f"  Aviso: não foi possível remover o arquivo de lista temporário '{temp_file_list_path}': {e_rem}")


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