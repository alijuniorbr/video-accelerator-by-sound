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
    sys.exit(1)

def format_time_delta(total_seconds):
    if total_seconds is None: total_seconds = 0
    total_seconds = int(round(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def main():
    parser = argparse.ArgumentParser(
        description="Processa vídeos: divide em chunks, segmenta por áudio, acelera silêncios e une.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Adicionando parâmetros para a nova Etapa 0
    parser.add_argument("--chunk-size", type=int, default=500, 
                        help="Tamanho do chunk em MB para dividir arquivos grandes. Defina como 0 para desativar o chunking.")
    # Parâmetros existentes
    parser.add_argument("-d", "--destination", type=str, help="Caminho do arquivo final.")
    parser.add_argument("-m", "--min-silence-len", type=int, default=2000, help="Duração mínima do silêncio em ms.")
    parser.add_argument("-t", "--silence-thresh", type=int, default=-35, help="Limiar de silêncio em dBFS.")
    parser.add_argument("-p", "--speech-padding", type=int, default=200, help="Padding em ms para o início da fala.")
    parser.add_argument("-k", "--min-silent-speedup-duration", type=int, default=1500, help="Duração mínima do silêncio (ms) para acelerar.")
    parser.add_argument("-v", "--speedup-factor", type=int, default=4, help="Fator de aceleração.")
    parser.add_argument("--fade", action='store_true', help="Aplicar fades de áudio nos segmentos (apenas no modo 'recode').")
    # parser.add_argument("--mode", choices=['recode', 'fast'], default='recode', help="Modo de processamento para a Etapa 1: 'recode' (lento, permite fades) ou 'fast' (rápido, baseado em keyframes).")
    parser.add_argument("-j", "--join-only", action="store_true", help="Modo apenas junção.")
    parser.add_argument("-s", "--source-files", nargs='+', required=True, help="Um ou mais arquivos de origem.")
    parser.add_argument("--keep-temp-dirs", action="store_true", help="Não apaga diretórios temporários.")
    
    args = parser.parse_args()
    processing_start_dt = datetime.datetime.now()
    start_time_perf = time.perf_counter()

    if not args.destination:
        timestamp_str = processing_start_dt.strftime("%d.%m.%Y.%H.%M.%S")
        args.destination = f"video-join-{len(args.source_files):02d}-{timestamp_str}.mp4"
    args.destination = os.path.abspath(args.destination)
    os.makedirs(os.path.dirname(args.destination), exist_ok=True)
    print(f"Arquivo de destino final: {args.destination}")

    master_log_data = {"parameters_used": vars(args), "processing_start_datetime": processing_start_dt.isoformat(), "source_file_details": []}
    list_of_abs_paths_for_final_join = []
    main_temp_dir = None

    if args.join_only:
        # Lógica de join-only (inalterada)
        print("INFO: Modo --join-only ativado. Unindo arquivos de origem diretamente...")
        for src_path in args.source_files:
            abs_path = os.path.abspath(src_path)
            if os.path.isfile(abs_path):
                list_of_abs_paths_for_final_join.append(abs_path)
            else:
                print(f"AVISO: Arquivo para junção direta não encontrado: {abs_path}. Pulando.")
    else:
        # Lógica principal de processamento
        timestamp_run = processing_start_dt.strftime("%Y%m%d_%H%M%S")
        main_temp_dir = os.path.abspath(f"pv_temp_run_{timestamp_run}")
        os.makedirs(main_temp_dir, exist_ok=True)
        print(f"Usando diretório temporário principal: {main_temp_dir}")
        
        all_chunks_to_process = []
        original_source_map = {} # Mapeia chunk para seu arquivo de origem original

        # Etapa 0: Dividir arquivos de origem em chunks, se necessário
        if args.chunk_size > 0:
            for source_video_path in args.source_files:
                abs_source_path = os.path.abspath(source_video_path)
                source_info = pv_utils.get_extended_video_info(abs_source_path)
                if not source_info.get("exists"):
                    print(f"ERRO: Arquivo de origem '{abs_source_path}' não encontrado. Pulando.")
                    continue
                
                source_file_log_entry = {"source_filepath": abs_source_path, "original_video_info": source_info, "chunks_processed": []}
                
                chunk_output_dir = os.path.join(main_temp_dir, f"chunks_{os.path.splitext(os.path.basename(abs_source_path))[0]}")
                
                chunk_paths = step0.divide_in_chunks(abs_source_path, chunk_output_dir, args.chunk_size)
                
                if chunk_paths:
                    all_chunks_to_process.extend(chunk_paths)
                    for chunk_path in chunk_paths:
                        original_source_map[chunk_path] = abs_source_path
                        source_file_log_entry["chunks_processed"].append({"chunk_path": chunk_path, "status": "Pendente"})
                else:
                     source_file_log_entry["error"] = "Falha na Etapa 0 (divisão em chunks)."
                
                master_log_data["source_file_details"].append(source_file_log_entry)
        else:
            print("INFO: Divisão em chunks desativada (--chunk-size 0). Processando arquivos de origem inteiros.")
            all_chunks_to_process = [os.path.abspath(p) for p in args.source_files]
            for source_path in all_chunks_to_process:
                original_source_map[source_path] = source_path
                master_log_data["source_file_details"].append({"source_filepath": source_path, "original_video_info": pv_utils.get_extended_video_info(source_path), "chunks_processed": []})

        # Agora, processa cada chunk (ou arquivo original)
        for i, video_chunk_path in enumerate(all_chunks_to_process):
            print(f"\n--- Processando Chunk {i+1}/{len(all_chunks_to_process)}: {os.path.basename(video_chunk_path)} ---")
            
            # Encontra o log do arquivo de origem correspondente para atualizar
            original_source = original_source_map[video_chunk_path]
            source_log_entry_to_update = next((item for item in master_log_data["source_file_details"] if item["source_filepath"] == original_source), None)

            current_chunk_segment_dir = os.path.join(main_temp_dir, f"segments_{os.path.splitext(os.path.basename(video_chunk_path))[0]}")
            
            try:
                # Etapa 1: Segmentação
                processed_video_s1, json_path_s1, kf_info_s1, segments_s1 = step1.segment_video(
                    video_path_param=video_chunk_path, output_dir=current_chunk_segment_dir,
                    json_file_name_in_output_dir="sound_index.json", min_silence_len_ms=args.min_silence_len,
                    silence_thresh_dbfs=args.silence_thresh, speech_start_padding_ms=args.speech_padding,
                    # processing_mode=args.mode, 
                    apply_fade=args.fade
                )
                if not json_path_s1: raise Exception("Falha na Etapa 1 (segmentação).")

                # Etapa 2: Acelerar Silêncios
                fps_para_aceleracao = pv_utils.get_extended_video_info(processed_video_s1).get("fps", 60.0)
                accel_summary_s2 = step2.accelerate_silent_segments(
                    segments_dir=current_chunk_segment_dir, index_json_path=json_path_s1,
                    min_original_silent_duration_s=args.min_silent_speedup_duration / 1000.0,
                    speedup_factor=args.speedup_factor, video_fps=fps_para_aceleracao
                )
                
                # Coletar segmentos para a junção final
                for seg_data in segments_s1:
                    original_file = seg_data["file"]
                    file_to_add = original_file
                    if seg_data["result"] == "silent" and accel_summary_s2["created_files_map"].get(original_file):
                        file_to_add = os.path.basename(accel_summary_s2["created_files_map"][original_file])
                    list_of_abs_paths_for_final_join.append(os.path.join(current_chunk_segment_dir, file_to_add))
                
                # Atualizar log do chunk
                if source_log_entry_to_update:
                    chunk_log = next((c for c in source_log_entry_to_update["chunks_processed"] if c["chunk_path"] == video_chunk_path), None)
                    if chunk_log:
                        chunk_log["status"] = "Sucesso"
                        chunk_log["segmentation_data"] = segments_s1
                        chunk_log["acceleration_summary"] = accel_summary_s2
            except Exception as e:
                print(f"ERRO ao processar chunk '{os.path.basename(video_chunk_path)}': {e}")
                if source_log_entry_to_update:
                    chunk_log = next((c for c in source_log_entry_to_update["chunks_processed"] if c["chunk_path"] == video_chunk_path), None)
                    if chunk_log: chunk_log["status"] = "Falha"; chunk_log["error"] = str(e)

    # Etapa 3: Junção Final
    if list_of_abs_paths_for_final_join:
        print(f"\n--- Etapa Final: Juntando {len(list_of_abs_paths_for_final_join)} segmentos totais ---")
        join_success = step3.join_segments_from_list(list_of_abs_paths_for_final_join, args.destination)
        master_log_data["final_output_summary"]["status"] = "SUCESSO" if join_success else "FALHA_JUNCAO"
    else:
        print("Nenhum segmento para a junção final."); master_log_data["final_output_summary"]["status"] = "NENHUM_SEGMENTO"

    # Coleta de estatísticas finais e escrita de logs
    end_time_perf = time.perf_counter()
    # (Lógica de logging e resumo como no script pv-process.py anterior, sem alterações)
    # ... (copie e cole a seção de logging e resumo daqui)
    # ...
    # Exemplo simplificado para manter a resposta concisa:
    print(f"\nProcessamento concluído em {end_time_perf - start_time_perf:.2f} segundos.")

    if not args.join_only and not args.keep_temp_dirs and main_temp_dir and os.path.exists(main_temp_dir):
        try:
            shutil.rmtree(main_temp_dir)
            print(f"Diretório temporário principal '{main_temp_dir}' removido.")
        except Exception as e:
            print(f"AVISO: Não foi possível remover o diretório temporário principal '{main_temp_dir}': {e}")

    print("\n--- Processamento Geral Concluído ---")

if __name__ == "__main__":
    main()