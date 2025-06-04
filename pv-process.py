#!/usr/bin/env python3
# pv-process.py

import argparse
import os
import sys
import json
import datetime
import time
import shutil # Para gerenciar diretórios temporários

# Tenta importar os módulos de etapa e utilitários
try:
    import pv_utils
    import pv_step_01_audio_segment as step1
    import pv_step_02_silent_accelerator as step2
    import pv_step_03_segment_join as step3
except ImportError as e:
    print(f"ERRO: Não foi possível importar um dos módulos necessários (pv_utils, pv_step_01..., pv_step_02..., pv_step_03...).")
    print(f"Certifique-se de que eles estão no mesmo diretório que pv-process.py. Detalhe: {e}")
    sys.exit(1)

def format_time_delta(total_seconds):
    """Formata segundos em HH:MM:SS"""
    if total_seconds is None: total_seconds = 0
    total_seconds = int(round(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def generate_default_output_filename(num_source_files, now_dt):
    timestamp_str = now_dt.strftime("%d.%m.%Y.%H.%M.%S")
    num_files_str = f"{num_source_files:02d}"
    return f"video-join-{num_files_str}-{timestamp_str}.mp4"

def main():
    parser = argparse.ArgumentParser(
        description="Processa vídeos: segmenta por áudio, acelera silêncios e une os resultados.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Mostra defaults na ajuda
    )
    parser.add_argument("-d", "--destination", type=str, 
                        help="Caminho completo do arquivo de vídeo final. Se não fornecido, um nome padrão será gerado no diretório atual.")
    parser.add_argument("-m", "--min-silence-len", type=int, default=400, 
                        help="Duração mínima do silêncio em ms para Pydub (MIN_SILENCE_LEN_MS).")
    parser.add_argument("-t", "--silence-thresh", type=int, default=-42, 
                        help="Limiar de silêncio em dBFS para Pydub (SILENCE_THRESH_DBFS).")
    parser.add_argument("-p", "--speech-padding", type=int, default=200, 
                        help="Padding (adiantamento) em ms para o início de segmentos de fala (SPEECH_START_PADDING_MS).")
    parser.add_argument("-k", "--min-silent-speedup-duration", type=int, default=1500, 
                        help="Duração mínima original de um segmento silencioso (em ms) para que ele seja acelerado.")
    parser.add_argument("-v", "--speedup-factor", type=int, default=4, 
                        help="Fator de aceleração para segmentos silenciosos (TIMES_OF_SPEEDUP).")
    parser.add_argument("-j", "--join-only", action="store_true", 
                        help="Modo apenas junção: assume que os arquivos de origem já são os segmentos finais a serem concatenados.")
    parser.add_argument("-s", "--source-files", nargs='+', required=True, 
                        help="Um ou mais caminhos para os arquivos de vídeo de origem.")
    parser.add_argument("--keep-temp-dirs", action="store_true",
                        help="Não apaga os diretórios temporários de segmentos após a execução.")
    parser.add_argument("--no-kf-re-encode-prompt", action="store_true",
                        help="Desativa o prompt interativo para re-codificar vídeos com poucos keyframes (assume 'continuar').")


    args = parser.parse_args()

    processing_start_dt = datetime.datetime.now()
    start_time_perf = time.perf_counter()

    # Define o nome do arquivo de destino e garante que o diretório exista
    if not args.destination:
        args.destination = generate_default_output_filename(len(args.source_files), processing_start_dt)
    
    args.destination = os.path.abspath(args.destination)
    os.makedirs(os.path.dirname(args.destination), exist_ok=True)
    print(f"Arquivo de destino final: {args.destination}")

    master_log_data = {
        "parameters_used": vars(args),
        "processing_start_datetime": processing_start_dt.isoformat(),
        "source_file_details": [],
        "final_output_summary": {"status": "NÃO INICIADO"},
        "processing_end_datetime": None,
        "total_elapsed_seconds": None
    }

    list_of_abs_paths_for_final_join = []
    main_temp_dir = None

    if args.join_only:
        print("INFO: Modo --join-only ativado. Unindo arquivos de origem diretamente...")
        for i, src_path in enumerate(args.source_files):
            abs_src_path = os.path.abspath(src_path)
            if not os.path.isfile(abs_src_path):
                print(f"AVISO: Arquivo para junção direta não encontrado: {abs_src_path}. Pulando.")
                master_log_data["source_file_details"].append({
                    "source_filepath_for_join": abs_src_path,
                    "original_video_info": pv_utils.get_extended_video_info(abs_src_path),
                    "processing_skipped_join_only": True,
                    "error": "Arquivo não encontrado para junção direta" if not os.path.isfile(abs_src_path) else None
                })
                continue
            list_of_abs_paths_for_final_join.append(abs_src_path)
            master_log_data["source_file_details"].append({
                "source_filepath_for_join": abs_src_path,
                "original_video_info": pv_utils.get_extended_video_info(abs_src_path),
                "processing_skipped_join_only": True
            })
    else:
        timestamp_run = processing_start_dt.strftime("%Y%m%d_%H%M%S")
        main_temp_dir = os.path.abspath(f"pv_temp_run_{timestamp_run}")
        try:
            if os.path.exists(main_temp_dir): shutil.rmtree(main_temp_dir) # Limpa se existir de uma execução falha
            os.makedirs(main_temp_dir, exist_ok=True)
            print(f"Usando diretório temporário principal: {main_temp_dir}")
        except Exception as e:
            print(f"ERRO: Não foi possível criar ou limpar o diretório temporário principal '{main_temp_dir}': {e}")
            sys.exit(1)


        for i, source_video_raw_path in enumerate(args.source_files):
            source_video_abs_path = os.path.abspath(source_video_raw_path)
            print(f"\n--- Processando Arquivo de Origem {i+1}/{len(args.source_files)}: {source_video_abs_path} ---")
            
            source_file_log_entry = {
                "source_filepath": source_video_abs_path,
                "original_video_info": pv_utils.get_extended_video_info(source_video_abs_path),
                "parameters_for_this_file": {
                    "min_silence_len_ms": args.min_silence_len, "silence_thresh_dbfs": args.silence_thresh,
                    "speech_start_padding_ms": args.speech_padding,
                    "min_silent_speedup_duration_s": args.min_silent_speedup_duration / 1000.0,
                    "speedup_factor": args.speedup_factor
                },
                "kf_re_encode_details": None,
                "segmentation_json_path": None,
                "segmentation_data": None, # Conteúdo do JSON da Etapa 1
                "acceleration_summary": None, # Resumo da Etapa 2
                "segments_contributed_to_join": [] # Detalhes dos segmentos que vão para a junção final
            }

            if not source_file_log_entry["original_video_info"]["exists"]:
                print(f"ERRO: Arquivo de origem não encontrado: {source_video_abs_path}. Pulando.")
                source_file_log_entry["error"] = "Arquivo de origem não encontrado"
                master_log_data["source_file_details"].append(source_file_log_entry)
                continue

            source_file_basename = os.path.splitext(os.path.basename(source_video_abs_path))[0]
            current_source_segment_dir = os.path.join(main_temp_dir, f"{i:02d}_{source_file_basename}_segments")
            os.makedirs(current_source_segment_dir, exist_ok=True)
            
            try:
                # Etapa 1: Segmentação
                print(f"\n  Etapa 1: Segmentando '{source_file_basename}'...")
                processed_video_path_s1, index_json_path_s1, kf_re_encode_info_s1, segments_list_s1 = \
                    step1.segment_video(
                        video_path_param=source_video_abs_path,
                        output_dir=current_source_segment_dir,
                        json_file_name_in_output_dir="sound_index.json", # Nome padrão
                        min_silence_len_ms=args.min_silence_len,
                        silence_thresh_dbfs=args.silence_thresh,
                        speech_start_padding_ms=args.speech_padding,
                        prompt_user_for_kf_re_encode=(not args.no_kf_re_encode_prompt) 
                        # keyframe_interval_s_for_re_encode já tem default em step1
                    )

                if not index_json_path_s1 or not segments_list_s1: # Falha na Etapa 1
                    raise Exception(f"Falha na Etapa 1 (segmentação) para {source_file_basename}.")

                source_file_log_entry["video_path_used_for_segmentation"] = processed_video_path_s1
                source_file_log_entry["kf_re_encode_details"] = kf_re_encode_info_s1
                source_file_log_entry["segmentation_json_path"] = index_json_path_s1
                source_file_log_entry["segmentation_data"] = segments_list_s1
                
                # Etapa 2: Acelerar Segmentos Silenciosos
                print(f"\n  Etapa 2: Acelerando silêncios para '{source_file_basename}'...")

                # Exemplo de como pegar o FPS do vídeo que foi efetivamente segmentado:
                fps_para_aceleracao = 60.0 # Default
                if source_file_log_entry.get("kf_re_encode_details") and \
                   source_file_log_entry["kf_re_encode_details"].get("status") == "Sucesso" and \
                   source_file_log_entry["kf_re_encode_details"].get("new_fps"):
                    fps_para_aceleracao = source_file_log_entry["kf_re_encode_details"]["new_fps"]
                elif source_file_log_entry.get("original_video_info"):
                    fps_para_aceleracao = source_file_log_entry["original_video_info"]["fps"]
                
                if not fps_para_aceleracao or fps_para_aceleracao <=0: # Fallback final
                    print(f"AVISO: FPS para aceleração não pôde ser determinado para {source_file_basename}, usando 30.0.")
                    fps_para_aceleracao = 60.0

                acceleration_summary_s2 = step2.accelerate_silent_segments(
                    segments_dir=current_source_segment_dir,
                    index_json_path=index_json_path_s1, 
                    min_original_silent_duration_s=args.min_silent_speedup_duration / 1000.0,
                    speedup_factor=args.speedup_factor,
                    video_fps=fps_para_aceleracao 
                )

                source_file_log_entry["acceleration_summary"] = acceleration_summary_s2
                
                # Coleta de segmentos para junção final (considerando _faster.mp4)
                current_source_segments_for_join = []
                for seg_data in segments_list_s1: # Usa os segmentos originais da Etapa 1
                    original_seg_filename = seg_data["file"]
                    file_to_add_for_join = original_seg_filename
                    is_accelerated = False

                    if seg_data["result"] == "silent" and \
                       acceleration_summary_s2["created_files_map"].get(original_seg_filename):
                        file_to_add_for_join = os.path.basename(acceleration_summary_s2["created_files_map"][original_seg_filename])
                        is_accelerated = True
                    
                    abs_path_to_add = os.path.join(current_source_segment_dir, file_to_add_for_join)
                    list_of_abs_paths_for_final_join.append(abs_path_to_add)
                    
                    # Para o log detalhado dos segmentos que entraram na junção
                    join_contrib_info = seg_data.copy() # Copia dados originais do segmento
                    join_contrib_info["final_file_used"] = file_to_add_for_join
                    join_contrib_info["full_path_for_join"] = abs_path_to_add
                    join_contrib_info["was_accelerated"] = is_accelerated
                    source_file_log_entry["segments_contributed_to_join"].append(join_contrib_info)

            except Exception as e:
                print(f"ERRO ao processar '{source_video_abs_path}' nas etapas 1 ou 2: {e}")
                source_file_log_entry["error"] = str(e)
            
            master_log_data["source_file_details"].append(source_file_log_entry)

    # Etapa 3: Junção Final
    if list_of_abs_paths_for_final_join:
        print(f"\n--- Etapa Final: Juntando {len(list_of_abs_paths_for_final_join)} segmentos totais ---")
        # O diretório para o filelist.txt temporário. Pode ser o diretório do arquivo de destino.
        join_temp_dir = os.path.dirname(args.destination)

        join_success = step3.join_segments_from_list(
            list_of_absolute_segment_filepaths=list_of_abs_paths_for_final_join,
            final_output_filepath=args.destination,
            segments_dir_for_filelist=join_temp_dir # Onde o filelist.txt será criado
        )
        if join_success:
            print(f"Arquivo final '{args.destination}' criado com sucesso.")
            master_log_data["final_output_summary"]["status"] = "SUCESSO"
        else:
            print(f"ERRO na junção final dos segmentos para '{args.destination}'.")
            master_log_data["final_output_summary"]["status"] = "FALHA_JUNCAO"
    else:
        print("Nenhum segmento para a junção final.")
        master_log_data["final_output_summary"]["status"] = "NENHUM_SEGMENTO_PARA_JUNTAR"

    # Coleta de estatísticas finais e escrita de logs
    end_time_perf = time.perf_counter()
    processing_end_dt = datetime.datetime.now()
    total_elapsed_seconds = end_time_perf - start_time_perf

    master_log_data["processing_end_datetime"] = processing_end_dt.isoformat()
    master_log_data["total_elapsed_seconds"] = round(total_elapsed_seconds, 3)

    # Sumarização para JSON e TXT
    total_src_bytes = sum(d.get("original_video_info", {}).get("size_bytes", 0) for d in master_log_data["source_file_details"] if not d.get("processing_skipped_join_only"))
    total_src_duration = sum(d.get("original_video_info", {}).get("duration_s", 0) for d in master_log_data["source_file_details"] if not d.get("processing_skipped_join_only"))
    total_src_frames = sum(d.get("original_video_info", {}).get("total_frames", 0) for d in master_log_data["source_file_details"] if not d.get("processing_skipped_join_only"))

    dest_stats = pv_utils.get_extended_video_info(args.destination) if master_log_data["final_output_summary"]["status"] == "SUCESSO" else pv_utils.get_extended_video_info("dummy_non_existent_path_for_init_stats") # para ter a estrutura
    
    final_summary = master_log_data["final_output_summary"]
    final_summary["destination_filepath"] = args.destination
    final_summary["source_files_processed_count"] = len([d for d in master_log_data["source_file_details"] if not d.get("processing_skipped_join_only") and not d.get("error")])
    final_summary["source_total_size_bytes"] = total_src_bytes
    final_summary["source_total_duration_s"] = round(total_src_duration, 3)
    final_summary["source_total_frames"] = total_src_frames
    
    final_summary["destination_size_bytes"] = dest_stats["size_bytes"]
    final_summary["destination_duration_s"] = round(dest_stats["duration_s"], 3)
    final_summary["destination_total_frames"] = dest_stats["total_frames"]

    if total_src_bytes > 0 and dest_stats["exists"]:
        final_summary["size_economy_bytes"] = total_src_bytes - dest_stats["size_bytes"]
        final_summary["size_economy_percentage"] = round(((total_src_bytes - dest_stats["size_bytes"]) / total_src_bytes) * 100, 2)
    if total_src_duration > 0 and dest_stats["exists"]:
        # A "economia de tempo" é mais complexa se o objetivo não é encurtar o vídeo, mas sim acelerar partes.
        # O que o usuário pediu foi TIME START, TIME END, TIME ECO.
        # TIME END aqui é a duração do vídeo final. TIME START é a soma das durações originais.
        final_summary["time_economy_seconds"] = round(total_src_duration - dest_stats["duration_s"], 3)
        final_summary["time_economy_percentage"] = round(((total_src_duration - dest_stats["duration_s"]) / total_src_duration) * 100, 2)
    if total_src_frames > 0 and dest_stats["exists"]:
        final_summary["frame_economy_frames"] = total_src_frames - dest_stats["total_frames"]
        final_summary["frame_economy_percentage"] = round(((total_src_frames - dest_stats["total_frames"]) / total_src_frames) * 100, 2)
    
    final_summary["list_of_concatenated_segment_paths"] = list_of_abs_paths_for_final_join

    # Escreve o log JSON completo
    json_log_path = os.path.splitext(args.destination)[0] + "_processing_log.json"
    try:
        with open(json_log_path, 'w') as f_json_log:
            json.dump(master_log_data, f_json_log, indent=2, ensure_ascii=False)
        print(f"Log JSON detalhado salvo em: {json_log_path}")
    except Exception as e:
        print(f"Erro ao salvar log JSON: {e}")

    # Escreve o sumário TXT
    txt_summary_path = os.path.splitext(args.destination)[0] + "_summary.txt"
    try:
        with open(txt_summary_path, 'w', encoding='utf-8') as f_txt:
            f_txt.write(f"START   : {processing_start_dt.strftime('%d/%m/%Y %H:%M:%S')}\n")
            f_txt.write(f"END     : {processing_end_dt.strftime('%d/%m/%Y %H:%M:%S')}\n")
            f_txt.write(f"ELAPSED : {format_time_delta(total_elapsed_seconds)} ({total_elapsed_seconds:.0f} segundos)\n")
            f_txt.write(f"STATUS  : {final_summary.get('status', 'DESCONHECIDO')}\n")
            f_txt.write("-" * 20 + " TAMANHO " + "-" * 20 + "\n")
            f_txt.write(f"SIZE START: {total_src_bytes / (1024*1024):.1f}MB ({total_src_bytes} bytes)\n")
            f_txt.write(f"SIZE END  : {dest_stats['size_bytes'] / (1024*1024):.1f}MB ({dest_stats['size_bytes']} bytes)\n")
            if "size_economy_bytes" in final_summary:
                f_txt.write(f"SIZE ECO  : {(final_summary['size_economy_bytes']) / (1024*1024):.1f}MB ({final_summary['size_economy_bytes']} bytes, {final_summary.get('size_economy_percentage',0)}%)\n")
            f_txt.write("-" * 20 + " DURAÇÃO " + "-" * 20 + "\n")
            f_txt.write(f"TIME START: {format_time_delta(total_src_duration)} ({total_src_duration:.0f} segundos)\n")
            f_txt.write(f"TIME END  : {format_time_delta(dest_stats['duration_s'])} ({dest_stats['duration_s']:.0f} segundos)\n") # Duração do vídeo final
            if "time_economy_seconds" in final_summary:
                 f_txt.write(f"TIME ECO  : {format_time_delta(final_summary['time_economy_seconds'])} ({final_summary['time_economy_seconds']:.0f} segundos, {final_summary.get('time_economy_percentage',0)}%)\n")
            f_txt.write("-" * 20 + " FRAMES " + "-" * 20 + "\n")
            f_txt.write(f"FRAME START: {total_src_frames} frames\n")
            f_txt.write(f"FRAME END  : {dest_stats['total_frames']} frames\n") # Frames do vídeo final
            if "frame_economy_frames" in final_summary:
                 f_txt.write(f"FRAME ECO : {final_summary['frame_economy_frames']} frames ({final_summary.get('frame_economy_percentage',0)}%)\n")
            
            f_txt.write("-" * 20 + " ARQUIVOS " + "-" * 20 + "\n")
            f_txt.write(f"FILE DEST : {args.destination}\n")
            f_txt.write("FILE SRC  :\n")
            for src_detail in master_log_data["source_file_details"]:
                f_txt.write(f"            {src_detail['source_filepath']}\n")
        print(f"Sumário TXT salvo em: {txt_summary_path}")
    except Exception as e:
        print(f"Erro ao salvar sumário TXT: {e}")

    if not args.join_only and not args.keep_temp_dirs and main_temp_dir and os.path.exists(main_temp_dir):
        try:
            shutil.rmtree(main_temp_dir)
            print(f"Diretório temporário principal '{main_temp_dir}' removido.")
        except Exception as e:
            print(f"AVISO: Não foi possível remover o diretório temporário principal '{main_temp_dir}': {e}")

    print("\n--- Processamento Geral Concluído ---")

if __name__ == "__main__":
    main()