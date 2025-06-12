# pv_step_02_silent_accelerator.py
import os
import json
import subprocess
import sys

# Este script agora não precisa de pv_utils.py, pois as informações necessárias (duração, fps)
# vêm do JSON gerado pela Etapa 1 ou são passadas como parâmetros.

def accelerate_silent_segments(segments_dir, index_json_path, 
                               min_original_silent_duration_s, 
                               speedup_factor,
                               video_fps):
    """
    Processa os segmentos de vídeo marcados como "silent" no arquivo JSON:
    - Verifica se a versão acelerada já existe antes de criar.
    - Acelera o vídeo pelo speedup_factor.
    - Adiciona uma trilha de áudio silenciosa.
    - Salva como "_faster.mp4".
    Retorna um dicionário com contagens e um mapa dos arquivos criados.
    """
    
    # Inicializa o dicionário de resumo com o novo contador
    result_summary = {"processed_count": 0, "skipped_count": 0, "already_exists_count": 0, "created_files_map": {}}

    if not os.path.isdir(segments_dir):
        print(f"  ETAPA 2 ERRO: Diretório de segmentos '{segments_dir}' não encontrado.")
        return result_summary
    if not os.path.isfile(index_json_path):
        print(f"  ETAPA 2 ERRO: Arquivo de índice '{index_json_path}' não encontrado.")
        return result_summary

    try:
        with open(index_json_path, 'r') as f:
            segment_data_list = json.load(f)
    except Exception as e:
        print(f"  ETAPA 2 ERRO: Falha ao ler ou parsear '{index_json_path}': {e}")
        return result_summary

    if not segment_data_list:
        print("  ETAPA 2: Nenhum segmento no índice para processar.")
        return result_summary

    print(f"--- Iniciando Etapa 2: Aceleração de Segmentos Silenciosos ---")
    print(f"  Verificando {len(segment_data_list)} segmentos do índice: {os.path.basename(index_json_path)}")
    print(f"  Acelerando por {speedup_factor}x os segmentos 'silent' com duração >= {min_original_silent_duration_s:.2f}s.")
    
    for segment_info in segment_data_list:
        if segment_info.get("result") == "silent":
            original_filename = segment_info.get("file")
            if not original_filename:
                print(f"  Aviso Etapa 2: Segmento com índice {segment_info.get('index')} sem nome de arquivo. Pulando.")
                continue

            input_filepath = os.path.join(segments_dir, original_filename)
            if not os.path.isfile(input_filepath):
                print(f"  Aviso Etapa 2: Arquivo '{input_filepath}' não encontrado. Pulando.")
                continue

            # Calcula a duração do segmento silencioso original a partir do JSON
            time_start = segment_info.get("time_start", 0.0)
            time_end = segment_info.get("time_end", 0.0)
            original_duration_s = time_end - time_start

            # Pula se for muito curto para acelerar
            if original_duration_s < min_original_silent_duration_s:
                # print(f"  Segmento silencioso '{original_filename}' (duração: {original_duration_s:.3f}s) muito curto. Não será acelerado.")
                result_summary["skipped_count"] += 1
                continue
            
            # Constrói o nome do arquivo de saída e verifica se ele já existe
            base_name_part = original_filename.split('_')[0]
            output_filename = f"{base_name_part}_faster.mp4"
            output_filepath = os.path.join(segments_dir, output_filename)

            # === LÓGICA DE VERIFICAÇÃO PARA RETOMADA DO PROCESSO ===
            if os.path.isfile(output_filepath):
                print(f"  Segmento acelerado '{output_filename}' já existe. Pulando criação.")
                result_summary["already_exists_count"] += 1
                # Adiciona ao mapa mesmo assim, para que o processo principal saiba que ele existe
                result_summary["created_files_map"][original_filename] = output_filepath
                continue
            # ========================================================
            
            print(f"  Processando '{original_filename}' -> '{output_filename}'")

            pts_factor = 1.0 / speedup_factor
            ffmpeg_command = [
                'ffmpeg', '-y',
                '-i', input_filepath,
                '-f', 'lavfi',
                '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
                '-vf', f'setpts={pts_factor:.3f}*PTS', 
                '-map', '0:v:0', 
                '-map', '1:a:0',
                '-r', str(video_fps), # Força o FPS de saída para consistência
                '-c:v', 'libx264', 
                '-preset', 'ultrafast',
                '-c:a', 'aac', 
                '-b:a', '16k',      # Bitrate baixo para áudio silencioso
                '-shortest',        # Termina com o stream mais curto (o vídeo)
                output_filepath
            ]
            
            try:
                ff_result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
                
                if ff_result.returncode == 0:
                    result_summary["created_files_map"][original_filename] = output_filepath
                    result_summary["processed_count"] += 1
                else:
                    print(f"  !! Erro Etapa 2 ao processar '{original_filename}' com FFmpeg (código: {ff_result.returncode}).")
                    if ff_result.stderr: print(f"     Stderr: {ff_result.stderr[:400]}...") # Mostra parte do erro
            
            except FileNotFoundError:
                print("!! ERRO CRÍTICO Etapa 2: 'ffmpeg' não encontrado."); return result_summary
            except Exception as e:
                print(f"!! Erro Etapa 2 inesperado ao processar '{original_filename}': {e}")
        
    print(f"--- Etapa 2 Concluída ---")
    print(f"  {result_summary['processed_count']} segmentos silenciosos foram criados/acelerados.")
    print(f"  {result_summary['already_exists_count']} segmentos acelerados já existiam e foram pulados.")
    print(f"  {result_summary['skipped_count']} segmentos silenciosos eram curtos demais e foram ignorados.")
    return result_summary


if __name__ == "__main__":
    print("--- Testando pv_step_02_silent_accelerator.py diretamente ---")
    if len(sys.argv) < 2:
        print("Uso para teste: python pv_step_02_silent_accelerator.py <diretorio_dos_segmentos>")
        print("  O diretório deve conter um 'sound_index.json' da Etapa 1.")
        sys.exit(1)
    
    test_segments_dir = sys.argv[1]
    test_json_path = os.path.join(test_segments_dir, "sound_index.json") 

    MIN_DURATION_S_TEST = 1.5 
    SPEEDUP_FACTOR_TEST = 4
    # Para teste, precisamos do FPS. Vamos tentar pegar do primeiro segmento no JSON.
    FPS_TEST = 60.0 # Default de segurança
    try:
        with open(test_json_path, 'r') as f_test:
            test_data = json.load(f_test)
            if test_data and 'fps' in test_data[0]:
                FPS_TEST = test_data[0]['fps']
    except Exception as e:
        print(f"Aviso: Não foi possível ler o FPS do JSON de teste, usando {FPS_TEST} como padrão. Erro: {e}")

    if not os.path.isdir(test_segments_dir) or not os.path.isfile(test_json_path):
        print(f"Erro: Diretório '{test_segments_dir}' ou arquivo '{test_json_path}' não encontrado.")
        sys.exit(1)

    print(f"Diretório de Teste: {test_segments_dir}, Índice: {test_json_path}")
    summary = accelerate_silent_segments(
        segments_dir=test_segments_dir,
        index_json_path=test_json_path,
        min_original_silent_duration_s=MIN_DURATION_S_TEST,
        speedup_factor=SPEEDUP_FACTOR_TEST,
        video_fps=FPS_TEST
    )
    print(f"Resumo do teste: {summary}")
    print("--- Teste de pv_step_02_silent_accelerator.py Concluído ---")