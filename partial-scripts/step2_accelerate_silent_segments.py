import os
import json
import subprocess
import sys

# NOVO: Limite mínimo de duração para que um segmento silencioso seja acelerado
MIN_ORIGINAL_SILENT_DURATION_FOR_SPEEDUP_S = 1.5  # Em segundos (ex: 1.5s). Ajuste conforme necessário.

def accelerate_silent_clips(segments_dir="audio_segments", index_file_name="sound_index.json", video_fps=60):
    full_index_path = os.path.join(segments_dir, index_file_name)
    
    if not os.path.isdir(segments_dir):
        print(f"Erro: Diretório de segmentos '{segments_dir}' não encontrado.")
        return

    if not os.path.isfile(full_index_path):
        print(f"Erro: Arquivo de índice '{full_index_path}' não encontrado.")
        return

    try:
        with open(full_index_path, 'r') as f:
            segment_data_list = json.load(f)
    except Exception as e:
        print(f"Erro ao ler ou parsear o arquivo JSON '{full_index_path}': {e}")
        return

    if not segment_data_list:
        print("Nenhum segmento encontrado no arquivo de índice.")
        return

    print(f"Encontrados {len(segment_data_list)} segmentos no índice. Procurando por segmentos silenciosos para acelerar...")
    
    processed_count = 0
    skipped_due_to_duration_count = 0

    for segment_info in segment_data_list:
        if segment_info.get("result") == "silent":
            original_filename = segment_info.get("file")
            if not original_filename:
                print(f"  Aviso: Segmento com índice {segment_info.get('index')} não tem nome de arquivo. Pulando.")
                continue

            input_filepath = os.path.join(segments_dir, original_filename)
            if not os.path.isfile(input_filepath):
                print(f"  Aviso: Arquivo de segmento original '{input_filepath}' não encontrado. Pulando.")
                continue

            # Calcula a duração do segmento silencioso original
            time_start = segment_info.get("time_start", 0.0)
            time_end = segment_info.get("time_end", 0.0)
            original_duration_s = time_end - time_start

            # === NOVA VERIFICAÇÃO DE DURAÇÃO ===
            if original_duration_s < MIN_ORIGINAL_SILENT_DURATION_FOR_SPEEDUP_S:
                print(f"  Segmento silencioso '{original_filename}' (duração: {original_duration_s:.3f}s) é muito curto. Não será acelerado.")
                skipped_due_to_duration_count += 1
                continue # Pula para o próximo segmento
            # ====================================

            base_name_part = original_filename.split('_')[0]
            output_filename = f"{base_name_part}_faster.mp4"
            output_filepath = os.path.join(segments_dir, output_filename)

            print(f"\nProcessando segmento silencioso: '{original_filename}' (duração: {original_duration_s:.3f}s) -> '{output_filename}'")

            ffmpeg_command = [
                'ffmpeg', '-y',
                '-i', input_filepath,
                '-f', 'lavfi',
                '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
                '-vf', 'setpts=0.25*PTS', 
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-r', str(video_fps), 
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-c:a', 'aac',
                '-b:a', '16k',
                '-shortest',
                output_filepath
            ]
            
            print(f"  Comando FFmpeg: {' '.join(ffmpeg_command)}")
            try:
                result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
                # (Impressão de logs do FFmpeg como antes)
                print(f"  --- Iniciando saída FFmpeg para {output_filename} ---")
                if result.stdout: print("  FFmpeg STDOUT:\n" + result.stdout.strip())
                if result.stderr: print("  FFmpeg STDERR:\n" + result.stderr.strip())
                print(f"  --- Fim da saída FFmpeg para {output_filename} (código de retorno: {result.returncode}) ---")

                if result.returncode == 0:
                    print(f"  Segmento '{output_filename}' criado e acelerado com sucesso.")
                    processed_count += 1
                else:
                    print(f"  !! Erro ao processar '{original_filename}' com FFmpeg.")
            except FileNotFoundError:
                print("!! ERRO CRÍTICO: 'ffmpeg' não encontrado."); return
            except Exception as e:
                print(f"!! Erro inesperado ao processar '{original_filename}': {e}")
        
    print(f"\nProcessamento concluído. {processed_count} segmentos silenciosos foram acelerados.")
    if skipped_due_to_duration_count > 0:
        print(f"{skipped_due_to_duration_count} segmentos silenciosos foram mantidos com velocidade original por serem muito curtos (menor que {MIN_ORIGINAL_SILENT_DURATION_FOR_SPEEDUP_S}s).")

# O if __name__ == "__main__": e a função main permanecem os mesmos
if __name__ == "__main__":
    default_segments_dir = "audio_segments" 
    segments_dir_to_use = sys.argv[1] if len(sys.argv) > 1 else default_segments_dir
    if not os.path.isdir(segments_dir_to_use):
        if segments_dir_to_use == default_segments_dir:
            print(f"Erro: Diretório padrão de segmentos '{default_segments_dir}' não encontrado.")
        else:
            print(f"Erro: Diretório de segmentos especificado '{segments_dir_to_use}' não encontrado.")
        sys.exit(1)
    accelerate_silent_clips(segments_dir=segments_dir_to_use)