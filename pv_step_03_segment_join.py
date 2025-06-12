# pv_step_03_segment_join.py
import os
import subprocess
import sys
import tempfile # Para criar o filelist.txt de forma segura e limpa

def join_segments_from_list(list_of_segment_filepaths, final_output_filepath):
    """
    Junta uma lista de arquivos de segmento em um único arquivo de saída.
    Usa o demuxer concat do FFmpeg.
    Espera uma lista de caminhos de arquivo (idealmente absolutos).
    Retorna True se bem-sucedido, False caso contrário.
    """
    if not list_of_segment_filepaths:
        print("  ETAPA 3 ERRO: Nenhuma lista de arquivos de segmento fornecida para junção.")
        return False

    # Cria um arquivo de texto temporário seguro para a lista do FFmpeg
    temp_file_descriptor, temp_file_list_path = tempfile.mkstemp(text=True, suffix='.txt', prefix='ffmpeg_join_list_')
    
    print(f"--- Iniciando Etapa 3: Junção de {len(list_of_segment_filepaths)} Segmentos ---")
    print(f"  Usando arquivo de lista temporário: {temp_file_list_path}")
    print(f"  Arquivo de saída final: {final_output_filepath}")
    
    try:
        # Escreve os caminhos dos arquivos no arquivo de lista temporário
        with os.fdopen(temp_file_descriptor, 'w', encoding='utf-8') as fl:
            for seg_path in list_of_segment_filepaths:
                # Normaliza o caminho e o coloca entre aspas simples para o FFmpeg
                # Isso ajuda a lidar com espaços ou caracteres especiais nos nomes dos arquivos/pastas
                clean_path = seg_path.replace("\\", "/").replace("'", "'\\''")
                fl.write(f"file '{clean_path}'\n")
        
        # Comando FFmpeg para concatenar os segmentos
        # -c:v copy copia o vídeo sem re-codificar (rápido, sem perda de qualidade)
        # -c:a aac re-codifica o áudio, o que é necessário para juntar segmentos
        # que têm áudio (os de fala) com os que não têm (os _faster com áudio silencioso gerado)
        ffmpeg_command = [
            'ffmpeg', '-y',                   # Sobrescrever arquivo de saída
            '-f', 'concat',           # Usar o demuxer concat
            '-safe', '0',             # Necessário para usar caminhos absolutos ou complexos no filelist
            '-i', temp_file_list_path,  # O arquivo de entrada é a lista que criamos
            '-c:v', 'copy',           # Copia o stream de vídeo
            '-c:a', 'aac',            # Re-codifica o stream de áudio para AAC
            '-b:a', '192k',           # Define o bitrate do áudio (ajuste se necessário)
            final_output_filepath
        ]
        
        print(f"  Executando FFmpeg para junção...")
        # A execução não precisa de um diretório de trabalho (cwd) específico
        # pois usamos caminhos absolutos (garantido pelo pv-process.py) ou
        # caminhos que são resolvidos corretamente pelo sistema.
        result = subprocess.run(ffmpeg_command, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE,
                                text=True, check=False)

        # Imprime a saída do FFmpeg para diagnóstico
        print(f"  --- Saída FFmpeg para junção ({os.path.basename(final_output_filepath)}) ---")
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
        # Limpa o arquivo de lista temporário em qualquer caso
        if os.path.exists(temp_file_list_path):
            os.remove(temp_file_list_path)
            # print(f"  Arquivo de lista temporário '{temp_file_list_path}' removido.")


if __name__ == "__main__":
    print("--- Testando pv_step_03_segment_join.py diretamente ---")
    if len(sys.argv) < 3:
        print("Uso para teste: python pv_step_03_segment_join.py <arquivo_de_saida.mp4> <segmento1.mp4> [segmento2.mp4 ...]")
        sys.exit(1)

    # Converte todos os caminhos para absolutos para o teste
    output_file_test = os.path.abspath(sys.argv[1])
    list_of_segments_test = [os.path.abspath(p) for p in sys.argv[2:]]
    
    # Cria o diretório de saída se ele não existir
    os.makedirs(os.path.dirname(output_file_test), exist_ok=True)

    print(f"Arquivo de Saída para Teste: {output_file_test}")
    print(f"Segmentos para Teste: {list_of_segments_test}")

    # Chama a função principal com os caminhos absolutos
    success = join_segments_from_list(list_of_segments_test, output_file_test)

    if success:
        print("\nTeste de junção pv_step_03_segment_join.py CONCLUÍDO COM SUCESSO.")
    else:
        print("\nTeste de junção pv_step_03_segment_join.py FALHOU.")
    print("--- Teste de pv_step_03_segment_join.py Finalizado ---")