#!/usr/bin/env python3
# pv-process.py

import argparse
import os
import sys
import json
import datetime
import time
import shutil

try:
    import pv_utils
    import pv_step_00_divide_in_chunks as step0
    import pv_step_01_audio_segment as step1
    import pv_step_02_silent_accelerator as step2
    import pv_step_03_segment_join as step3
except ImportError as e:
    print(f"ERRO: Não foi possível importar um dos módulos necessários: {e}")
    print("Certifique-se de que todos os scripts (pv_utils.py, pv_step_00..., etc.) estão no mesmo diretório.")
    sys.exit(1)

def format_time_delta(total_seconds):
    """Formata segundos em HH:MM:SS"""
    if total_seconds is None: total_seconds = 0
    total_seconds = int(round(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def generate_default_output_filename(num_source_files, now_dt):
    timestamp_str = now_dt.strftime("%d.%m.%Y.%H.%M.%S")
    num_files_str = f"{num_source_files:02d}"
    return f"video-join-{num_files_str}-{timestamp_str}.mp4"

def main():
    parser = argparse.ArgumentParser(
        description="Processa vídeos: divide em chunks, segmenta por áudio, acelera silêncios e une.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Argumentos para o processo completo
    parser.add_argument("-d", "--destination", type=str, help="Caminho do arquivo de vídeo final.")
    parser.add_argument("-s", "--source-files", nargs='+', required=True, help="Um ou mais arquivos de vídeo de origem.")
    
    # Argumentos para Etapa 0 (Chunking)
    parser.add_argument("--chunk-size", type=int, default=500, help="Tamanho máx. do chunk em MB para dividir arquivos grandes. Defina como 0 para desativar.")
    
    # Argumentos para Etapa 1 (Segmentação de Áudio)
    parser.add_argument("-m", "--min-silence-len", type=int, default=2000, help="Duração mínima do silêncio em ms (Pydub).")
    parser.add_argument("-t", "--silence-thresh", type=int, default=-35, help="Limiar de silêncio em dBFS (Pydub).")
    parser.add_argument("-p", "--speech-padding", type=int, default=200, help="Padding em ms para o início da fala.")
    parser.add_argument("--fade", action='store_true', help="Aplicar fades de áudio nos segmentos. CUIDADO: Pode causar problemas de áudio em alguns vídeos.")

    # Argumentos para Etapa 2 (Aceleração)
    parser.add_argument("-k", "--min-silent-speedup-duration", type=int, default=1500, help="Duração mínima do silêncio (ms) para acelerar.")
    parser.add_argument("-v", "--speedup-factor", type=int, default=4, help="Fator de aceleração.")

    # Argumentos de controle do processo
    parser.add_argument("-j", "--join-only", action="store_true", help="Modo apenas junção: assume que os arquivos de origem já são os segmentos finais.")
    parser.add_argument("--keep-temp-dirs", action="store_true", help="Não apaga os diretórios temporários após a execução.")
    parser.add_argument("--clean-start", action="store_true", help="Força uma execução limpa, apagando o diretório temporário anterior com o mesmo nome de destino.")

    args = parser.parse_args()
    processing_start_dt = datetime.datetime.now()
    start_time_perf = time.perf_counter()

    if not args.destination:
        args.destination = generate_default_output_filename(len(args.source_files), processing_start_dt)
    args.destination = os.path.abspath(args.destination)
    os.makedirs(os.path.dirname(args.destination), exist_ok=True)
    print(f"Arquivo de destino final: {args.destination}")

    master_log_data = {"parameters_used": vars(args), "processing_start_datetime": processing_start_dt.isoformat(), "source_file_details": []}
    list_of_abs_paths_for_final_join = []
    main_temp_dir = None

    if args.join_only:
        print("INFO: Modo --join-only ativado. Unindo arquivos de origem diretamente...")
        for src_path in args.source_files:
            abs_path = os.path.abspath(src_path)
            if os.path.isfile(abs_path):
                list_of_abs_paths_for_final_join.append(abs_path)
            else:
                print(f"AVISO: Arquivo para junção direta não encontrado: {abs_path}. Pulando.")
    else:
        dest_basename = os.path.splitext(os.path.basename(args.destination))[0]
        main_temp_dir = os.path.join(os.path.dirname(args.destination), f"{dest_basename}_temp_files")

        if args.clean_start and os.path.exists(main_temp_dir):
            print(f"INFO: --clean-start usado. Removendo diretório temporário: {main_temp_dir}")
            try: shutil.rmtree(main_temp_dir)
            except Exception as e: print(f"AVISO: Falha ao remover diretório temporário antigo: {e}")
        
        os.makedirs(main_temp_dir, exist_ok=True)
        print(f"Usando diretório temporário persistente: {main_temp_dir}")
        
        all_chunks_to_process = []
        original_source_map = {}

        # Etapa 0: Dividir arquivos de origem em chunks
        for source_video_path in args.source_files:
            abs_source_path = os.path.abspath(source_video_path)
            source_info = pv_utils.get_extended_video_info(abs_source_path)
            
            source_file_log_entry = next((item for item in master_log_data["source_file_details"] if item["source_filepath"] == abs_source_path), None)
            if not source_file_log_entry:
                source_file_log_entry = {"source_filepath": abs_source_path, "original_video_info": source_info, "chunks_processed": []}
                master_log_data["source_file_details"].append(source_file_log_entry)

            if not source_info.get("exists"):
                print(f"ERRO: Arquivo de origem '{abs_source_path}' não encontrado. Pulando."); continue
            
            if args.chunk_size > 0:
                chunk_output_dir = os.path.join(main_temp_dir, f"chunks_{os.path.splitext(os.path.basename(abs_source_path))[0]}")
                chunk_paths = step0.divide_in_chunks(abs_source_path, chunk_output_dir, args.chunk_size)
            else:
                print("INFO: Divisão em chunks desativada. Processando arquivo de origem inteiro.")
                chunk_paths = [abs_source_path]

            if chunk_paths:
                all_chunks_to_process.extend(chunk_paths)
                for chunk_path in chunk_paths:
                    original_source_map[chunk_path] = abs_source_path
                    if not any(c["chunk_path"] == chunk_path for c in source_file_log_entry["chunks_processed"]):
                         source_file_log_entry["chunks_processed"].append({"chunk_path": chunk_path, "status": "Pendente"})
            else:
                source_file_log_entry["error"] = "Falha na Etapa 0 (divisão em chunks)."
        
        # Etapas 1 e 2: Processamento por Chunk
        for i, video_chunk_path in enumerate(all_chunks_to_process):
            print(f"\n--- Processando Chunk {i+1}/{len(all_chunks_to_process)}: {os.path.basename(video_chunk_path)} ---")
            
            original_source = original_source_map.get(video_chunk_path, video_chunk_path)
            source_log_entry_to_update = next((item for item in master_log_data["source_file_details"] if item["source_filepath"] == original_source), {})
            current_chunk_log = next((c for c in source_log_entry_to_update.get("chunks_processed", []) if c["chunk_path"] == video_chunk_path), {})

            current_chunk_segment_dir = os.path.join(main_temp_dir, f"segments_{os.path.splitext(os.path.basename(video_chunk_path))[0]}")
            
            try:
                processed_video_s1, json_path_s1, kf_info_s1, segments_s1 = step1.segment_video(
                    video_path_param=video_chunk_path, output_dir=current_chunk_segment_dir,
                    json_file_name="sound_index.json", min_silence_len_ms=args.min_silence_len,
                    silence_thresh_dbfs=args.silence_thresh, speech_start_padding_ms=args.speech_padding,
                    apply_fade=args.fade
                )
                if not json_path_s1 or segments_s1 is None: raise Exception("Falha na Etapa 1 (segmentação).")
                current_chunk_log["segmentation_data"] = segments_s1
                
                fps_para_aceleracao = pv_utils.get_extended_video_info(processed_video_s1).get("fps", 60.0)
                accel_summary_s2 = step2.accelerate_silent_segments(
                    segments_dir=current_chunk_segment_dir, index_json_path=json_path_s1,
                    min_original_silent_duration_s=args.min_silent_speedup_duration / 1000.0,
                    speedup_factor=args.speedup_factor, video_fps=fps_para_aceleracao
                )
                current_chunk_log["acceleration_summary"] = accel_summary_s2
                
                for seg_data in segments_s1:
                    original_file = seg_data["file"]
                    file_to_add = original_file
                    if seg_data["result"] == "silent" and accel_summary_s2["created_files_map"].get(original_file):
                        file_to_add = os.path.basename(accel_summary_s2["created_files_map"][original_file])
                    list_of_abs_paths_for_final_join.append(os.path.join(current_chunk_segment_dir, file_to_add))
                
                current_chunk_log["status"] = "Sucesso"
            except Exception as e:
                print(f"ERRO ao processar chunk '{os.path.basename(video_chunk_path)}': {e}")
                current_chunk_log["status"] = "Falha"; current_chunk_log["error"] = str(e)

    # Etapa 3: Junção Final
    if list_of_abs_paths_for_final_join:
        print(f"\n--- Etapa Final: Juntando {len(list_of_abs_paths_for_final_join)} segmentos totais ---")
        join_success = step3.join_segments_from_list(
            list_of_absolute_segment_filepaths=list_of_abs_paths_for_final_join,
            final_output_filepath=args.destination
        )
        master_log_data["final_output_summary"]["status"] = "SUCESSO" if join_success else "FALHA_JUNCAO"
    else:
        print("Nenhum segmento para a junção final."); master_log_data["final_output_summary"]["status"] = "NENHUM_SEGMENTO"

    # Coleta de estatísticas finais e escrita de logs
    end_time_perf = time.perf_counter()
    processing_end_dt = datetime.datetime.now()
    total_elapsed_seconds = end_time_perf - start_time_perf

    master_log_data["processing_end_datetime"] = processing_end_dt.isoformat()
    master_log_data["total_elapsed_seconds"] = round(total_elapsed_seconds, 3)

    total_src_bytes, total_src_duration, total_src_frames = 0, 0.0, 0
    for d in master_log_data["source_file_details"]:
        if not d.get("processing_skipped_join_only") and d.get("original_video_info"):
            total_src_bytes += d["original_video_info"].get("size_bytes", 0)
            total_src_duration += d["original_video_info"].get("duration_s", 0)
            total_src_frames += d["original_video_info"].get("total_frames", 0)
    
    dest_stats = pv_utils.get_extended_video_info(args.destination) if master_log_data["final_output_summary"]["status"] == "SUCESSO" else {}
    total_dest_bytes = dest_stats.get("size_bytes", 0)
    total_dest_duration = dest_stats.get("duration_s", 0)
    total_dest_frames = dest_stats.get("total_frames", 0)
    
    final_summary = master_log_data["final_output_summary"]
    final_summary["destination_filepath"] = args.destination
    final_summary["source_files_processed_count"] = len([d for d in master_log_data["source_file_details"] if not d.get("processing_skipped_join_only") and not d.get("error")])
    final_summary["source_total_size_bytes"], final_summary["source_total_duration_s"], final_summary["source_total_frames"] = total_src_bytes, round(total_src_duration, 3), total_src_frames
    final_summary["destination_size_bytes"], final_summary["destination_duration_s"], final_summary["destination_total_frames"] = total_dest_bytes, round(total_dest_duration, 3), total_dest_frames

    if total_src_bytes > 0 and dest_stats.get("exists"):
        final_summary["size_economy_bytes"] = total_src_bytes - total_dest_bytes
        final_summary["size_economy_percentage"] = round(((total_src_bytes - total_dest_bytes) / total_src_bytes) * 100, 2)
    if total_src_duration > 0 and dest_stats.get("exists"):
        final_summary["time_economy_seconds"] = round(total_src_duration - total_dest_duration, 3)
        final_summary["time_economy_percentage"] = round(((total_src_duration - total_dest_duration) / total_src_duration) * 100, 2)
    if total_src_frames > 0 and dest_stats.get("exists"):
        final_summary["frame_economy_frames"] = total_src_frames - total_dest_frames
        final_summary["frame_economy_percentage"] = round(((total_src_frames - total_dest_frames) / total_src_frames) * 100, 2)
    
    final_summary["list_of_concatenated_segment_paths"] = list_of_abs_paths_for_final_join

    json_log_path = os.path.splitext(args.destination)[0] + "_processing_log.json"
    try:
        with open(json_log_path, 'w', encoding='utf-8') as f_json_log:
            json.dump(master_log_data, f_json_log, indent=2, ensure_ascii=False)
        print(f"Log JSON detalhado salvo em: {json_log_path}")
    except Exception as e: print(f"Erro ao salvar log JSON: {e}")

    txt_summary_path = os.path.splitext(args.destination)[0] + "_summary.txt"
    try:
        with open(txt_summary_path, 'w', encoding='utf-8') as f_txt:
            f_txt.write(f"START   : {processing_start_dt.strftime('%d/%m/%Y %H:%M:%S')}\n")
            f_txt.write(f"END     : {processing_end_dt.strftime('%d/%m/%Y %H:%M:%S')}\n")
            f_txt.write(f"ELAPSED : {format_time_delta(total_elapsed_seconds)} ({total_elapsed_seconds:.0f} segundos)\n")
            f_txt.write(f"STATUS  : {final_summary.get('status', 'DESCONHECIDO')}\n")
            f_txt.write("-" * 20 + " TAMANHO " + "-" * 20 + "\n")
            f_txt.write(f"SIZE START: {total_src_bytes / (1024*1024):.1f}MB ({total_src_bytes} bytes)\n")
            f_txt.write(f"SIZE END  : {total_dest_bytes / (1024*1024):.1f}MB ({total_dest_bytes} bytes)\n")
            if "size_economy_bytes" in final_summary:
                f_txt.write(f"SIZE ECO  : {final_summary['size_economy_bytes'] / (1024*1024):.1f}MB ({final_summary['size_economy_bytes']} bytes, {final_summary.get('size_economy_percentage', 0)}%)\n")
            f_txt.write("-" * 20 + " DURAÇÃO " + "-" * 20 + "\n")
            f_txt.write(f"TIME START: {format_time_delta(total_src_duration)} ({total_src_duration:.0f} segundos)\n")
            f_txt.write(f"TIME END  : {format_time_delta(total_dest_duration)} ({total_dest_duration:.0f} segundos)\n")
            if "time_economy_seconds" in final_summary:
                 f_txt.write(f"TIME ECO  : {format_time_delta(final_summary['time_economy_seconds'])} ({final_summary['time_economy_seconds']:.0f} segundos, {final_summary.get('time_economy_percentage', 0)}%)\n")
            f_txt.write("-" * 20 + " FRAMES " + "-" * 20 + "\n")
            f_txt.write(f"FRAME START: {total_src_frames} frames\n")
            f_txt.write(f"FRAME END  : {total_dest_frames} frames\n")
            if "frame_economy_frames" in final_summary:
                 f_txt.write(f"FRAME ECO : {final_summary['frame_economy_frames']} frames ({final_summary.get('frame_economy_percentage', 0)}%)\n")
            
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
    elif not args.join_only and args.keep_temp_dirs and main_temp_dir:
        print(f"Processamento concluído. Diretório temporário '{main_temp_dir}' foi mantido conforme solicitado.")


if __name__ == "__main__":
    main()