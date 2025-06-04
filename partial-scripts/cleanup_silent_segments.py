import os
import sys

def cleanup_redundant_silent_segments(segments_dir):
    """
    Remove arquivos "_silent.mp4" do diretório de segmentos se uma versão
    "_faster.mp4" correspondente existir.
    """
    if not os.path.isdir(segments_dir):
        print(f"Erro: Diretório de segmentos '{segments_dir}' não encontrado.")
        return

    print(f"Iniciando limpeza de segmentos redundantes em: '{os.path.abspath(segments_dir)}'")

    all_files = os.listdir(segments_dir)
    
    # 1. Encontra todos os arquivos base que têm uma versão "_faster"
    faster_bases = set()
    for filename in all_files:
        if filename.endswith("_faster.mp4"):
            base_name = filename.replace("_faster.mp4", "")
            faster_bases.add(base_name)
            
    if not faster_bases:
        print("Nenhum arquivo '_faster.mp4' encontrado. Nenhuma limpeza necessária com base neles.")
        # Ainda assim, pode haver _silent.mp4 que não deveriam estar se o processo foi interrompido
        # Mas o objetivo é limpar _silent QUANDO _faster existe.
        # Se o objetivo fosse limpar _silent que NÃO foram usados no join, precisaríamos do JSON.
        # O pedido foi: "apaga o correspondente silent... deixando somente o que for parte do video que sera montado"
        # Isso implica que se _faster existe, ele é parte do vídeo, e o _silent original não é.
        # Se um _silent não tem _faster (porque era curto), ele É parte do vídeo.

    # 2. Itera novamente e remove os "_silent.mp4" correspondentes
    deleted_count = 0
    kept_short_silent_count = 0 # Para contar _silent que não tinham _faster

    for filename in all_files:
        if filename.endswith("_silent.mp4"):
            base_name = filename.replace("_silent.mp4", "")
            if base_name in faster_bases: # Se existe um "_faster" para este base_name
                silent_filepath = os.path.join(segments_dir, filename)
                try:
                    os.remove(silent_filepath)
                    print(f"  Removido: '{filename}' (substituído por '{base_name}_faster.mp4')")
                    deleted_count += 1
                except OSError as e:
                    print(f"  Erro ao remover '{filename}': {e}")
            else:
                # Este é um _silent.mp4 que NÃO teve um _faster.mp4 criado (provavelmente era curto)
                # Portanto, ele DEVE ser mantido para a junção.
                kept_short_silent_count +=1

    print(f"\nLimpeza concluída.")
    print(f"  {deleted_count} arquivo(s) '_silent.mp4' redundante(s) foram removidos.")
    if kept_short_silent_count > 0:
        print(f"  {kept_short_silent_count} arquivo(s) '_silent.mp4' (curtos) foram mantidos (não tinham versão '_faster').")
    if not faster_bases and deleted_count == 0:
         print("  Nenhuma ação de limpeza foi realizada (nenhum arquivo '_faster.mp4' encontrado para basear a remoção).")


if __name__ == "__main__":
    default_segments_dir = "audio_segments" # Alinhe com o diretório de saída do seu pv-process.py
    
    segments_dir_to_clean = default_segments_dir
    if len(sys.argv) > 1:
        segments_dir_to_clean = sys.argv[1]
        print(f"Usando diretório especificado para limpeza: '{segments_dir_to_clean}'")
    else:
        print(f"Usando diretório padrão para limpeza: '{default_segments_dir}'")
        print("Você pode especificar um diretório diferente como argumento: python cleanup_processed_segments.py <caminho_do_diretorio>")

    # Confirmação do usuário antes de deletar
    if os.path.isdir(segments_dir_to_clean):
        print(f"\nAVISO: Este script irá apagar arquivos '_silent.mp4' do diretório '{os.path.abspath(segments_dir_to_clean)}'")
        print("se uma versão '_faster.mp4' correspondente existir.")
        
        # Lista os arquivos que seriam apagados (dry run simulado)
        preview_deleted_files = []
        all_files_preview = os.listdir(segments_dir_to_clean)
        faster_bases_preview = set()
        for fname_preview in all_files_preview:
            if fname_preview.endswith("_faster.mp4"):
                faster_bases_preview.add(fname_preview.replace("_faster.mp4", ""))
        
        if faster_bases_preview:
            print("\nArquivos '_silent.mp4' que seriam REMOVIDOS (pois existe um '_faster.mp4'):")
            found_to_delete = False
            for fname_preview in all_files_preview:
                if fname_preview.endswith("_silent.mp4"):
                    base_preview = fname_preview.replace("_silent.mp4", "")
                    if base_preview in faster_bases_preview:
                        print(f"  - {fname_preview}")
                        found_to_delete = True
            if not found_to_delete:
                print("  (Nenhum arquivo '_silent.mp4' seria removido com base nos '_faster.mp4' existentes)")
        else:
            print("\nNenhum arquivo '_faster.mp4' encontrado, então nenhum '_silent.mp4' seria removido por esta lógica.")


        while True:
            confirm = input("\nDeseja continuar com a limpeza? (s/n): ").strip().lower()
            if confirm in ['s', 'n']:
                break
            print("Opção inválida.")
        
        if confirm == 's':
            cleanup_redundant_silent_segments(segments_dir_to_clean)
        else:
            print("Limpeza cancelada pelo usuário.")
    else:
        print(f"Erro: Diretório '{segments_dir_to_clean}' não encontrado para limpeza.")