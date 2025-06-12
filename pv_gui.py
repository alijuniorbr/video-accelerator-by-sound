# pv_gui.py
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import subprocess
import threading
import queue
import os
import sys
import shlex
import json

# --- CONFIGURAÇÃO ---
PV_PROCESS_SCRIPT_PATH = "pv-process.py" 
CONFIG_FILE_NAME = "pv_gui_config.json"
# --------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Processador de Vídeo (PV-Process)")
        self.geometry("800x800")

        self.source_files = [] # Esta lista agora será salva e carregada
        self.processing_process = None
        self.processing_thread = None

        # --- Variáveis de controle para os widgets ---
        self.destination_file_var = tk.StringVar()
        self.min_silence_len_var = tk.StringVar()
        self.silence_thresh_var = tk.StringVar()
        self.speech_padding_start_var = tk.StringVar()
        self.speech_padding_end_var = tk.StringVar()
        self.fade_duration_var = tk.StringVar()
        self.min_silent_speedup_duration_var = tk.StringVar()
        self.speedup_factor_var = tk.StringVar()
        self.chunk_size_var = tk.StringVar()
        self.join_only_var = tk.BooleanVar()
        self.apply_fade_var = tk.BooleanVar()
        self.keep_temp_dirs_var = tk.BooleanVar()
        self.clean_start_var = tk.BooleanVar()
        
        self.config_vars = {
            "destination_file": self.destination_file_var,
            "min_silence_len": self.min_silence_len_var,
            "silence_thresh": self.silence_thresh_var,
            "speech_padding_start": self.speech_padding_start_var,
            "speech_padding_end": self.speech_padding_end_var,
            "fade_duration": self.fade_duration_var,
            "min_silent_speedup_duration": self.min_silent_speedup_duration_var,
            "speedup_factor": self.speedup_factor_var,
            "chunk_size": self.chunk_size_var,
            "join_only": self.join_only_var,
            "apply_fade": self.apply_fade_var,
            "keep_temp_dirs": self.keep_temp_dirs_var,
            "clean_start": self.clean_start_var
            # A lista de arquivos de origem será tratada separadamente
        }

        self.log_queue = queue.Queue()
        self.after(100, self.process_log_queue)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Criação da Interface ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.create_file_selection_widgets(main_frame)
        self.create_parameters_widgets(main_frame)
        self.create_log_widgets(main_frame)
        self.create_action_buttons(main_frame)
        
        self.load_settings() # Carrega as últimas configurações salvas

    def get_default_settings(self):
        """Retorna um dicionário com todos os valores padrão."""
        return {
            "source_files": [], # Adicionado para a lógica de resetar
            "destination_file": "", "min_silence_len": "2000", "silence_thresh": "-35",
            "speech_padding_start": "500", "speech_padding_end": "500", "fade_duration": "20",
            "min_silent_speedup_duration": "1500", "speedup_factor": "4", "chunk_size": "500",
            "join_only": False, "apply_fade": False, "keep_temp_dirs": False, "clean_start": False
        }
    
    def on_closing(self):
        """Salva as configurações ao fechar a janela."""
        self.save_settings()
        self.destroy()

    def save_settings(self):
        """Salva os valores atuais dos widgets em um arquivo JSON."""
        settings_to_save = {key: var.get() for key, var in self.config_vars.items()}
        # === ADICIONADO: Salva a lista de arquivos de origem ===
        settings_to_save["source_files"] = self.source_files
        # ====================================================
        try:
            with open(CONFIG_FILE_NAME, 'w') as f:
                json.dump(settings_to_save, f, indent=2)
            print("Configurações salvas.")
        except Exception as e:
            print(f"Não foi possível salvar as configurações: {e}")

    def load_settings(self):
        """Carrega as configurações de um arquivo JSON se ele existir, senão usa os padrões."""
        if os.path.exists(CONFIG_FILE_NAME):
            print("Carregando configurações salvas.")
            try:
                with open(CONFIG_FILE_NAME, 'r') as f:
                    settings = json.load(f)
                
                # Carrega os parâmetros normais
                for key, var in self.config_vars.items():
                    if key in settings:
                        var.set(settings[key])
                
                # === ADICIONADO: Carrega e exibe a lista de arquivos de origem ===
                self.clear_source_files() # Limpa a lista atual antes de carregar
                loaded_files = settings.get("source_files", [])
                for f_path in loaded_files:
                    if os.path.exists(f_path): # Apenas adiciona se o arquivo ainda existir
                        self.source_files.append(f_path)
                        self.source_listbox.insert(tk.END, os.path.basename(f_path))
                    else:
                        print(f"Aviso: arquivo de origem salvo '{f_path}' não encontrado. Ignorando.")
                # =============================================================

            except Exception as e:
                print(f"Não foi possível carregar as configurações, usando padrões. Erro: {e}")
                self.reset_to_defaults()
        else:
            print("Nenhum arquivo de configuração encontrado, usando padrões.")
            self.reset_to_defaults()

    def reset_to_defaults(self):
        """Reseta todos os campos para os valores padrão."""
        defaults = self.get_default_settings()
        for key, var in self.config_vars.items():
            if key in defaults:
                var.set(defaults[key])
        # Reseta também a lista de arquivos
        self.clear_source_files()
        self.log_message("Parâmetros resetados para os valores padrão.\n")

    def create_file_selection_widgets(self, parent):
        frame = ttk.LabelFrame(parent, text="Seleção de Arquivos", padding="10")
        frame.pack(fill=tk.X, pady=5)
        ttk.Label(frame, text="Arquivos de Origem:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.source_listbox = tk.Listbox(frame, height=5, selectmode=tk.EXTENDED)
        self.source_listbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)
        source_buttons_frame = ttk.Frame(frame)
        source_buttons_frame.grid(row=1, column=2, sticky="ns", padx=5)
        ttk.Button(source_buttons_frame, text="Adicionar...", command=self.select_source_files).pack(fill=tk.X, pady=2)
        ttk.Button(source_buttons_frame, text="Remover", command=self.remove_selected_source_files).pack(fill=tk.X, pady=2)
        ttk.Button(source_buttons_frame, text="Limpar", command=self.clear_source_files).pack(fill=tk.X, pady=2)
        ttk.Label(frame, text="Arquivo de Destino:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        dest_entry = ttk.Entry(frame, textvariable=self.destination_file_var)
        dest_entry.grid(row=3, column=0, columnspan=2, sticky="ew", padx=5)
        ttk.Button(frame, text="Salvar Como...", command=self.select_destination_file).grid(row=3, column=2, padx=5)
        frame.columnconfigure(0, weight=1)

    def create_parameters_widgets(self, parent):
        frame = ttk.LabelFrame(parent, text="Parâmetros de Processamento", padding="10")
        frame.pack(fill=tk.X, pady=5)
        
        params_frame = ttk.Frame(frame)
        params_frame.grid(row=0, column=0, sticky="nw")
        
        params = [
            ("Duração Mín. Silêncio (ms):", self.min_silence_len_var),
            ("Limiar de Silêncio (dBFS):", self.silence_thresh_var),
            ("Padding Início Fala (ms):", self.speech_padding_start_var),
            ("Padding Fim Fala (ms):", self.speech_padding_end_var),
            ("Duração Fade (ms):", self.fade_duration_var),
            ("Duração Mín. p/ Acelerar (ms):", self.min_silent_speedup_duration_var),
            ("Fator de Aceleração:", self.speedup_factor_var),
            ("Tamanho do Chunk (MB) [0=desativado]:", self.chunk_size_var),
        ]
        
        for i, (label_text, var) in enumerate(params):
            ttk.Label(params_frame, text=label_text).grid(row=i, column=0, sticky="w", padx=5, pady=2)
            ttk.Entry(params_frame, textvariable=var, width=10).grid(row=i, column=1, sticky="w", padx=5, pady=2)

        options_frame = ttk.Frame(frame)
        options_frame.grid(row=0, column=1, sticky="nw", padx=(20, 5))
        ttk.Label(options_frame, text="Opções Booleanas:").pack(anchor="w")
        
        ttk.Checkbutton(options_frame, text="Apenas Juntar (--join-only)", variable=self.join_only_var).pack(anchor="w")
        ttk.Checkbutton(options_frame, text="Aplicar Fades de Áudio (--fade)", variable=self.apply_fade_var).pack(anchor="w")
        ttk.Checkbutton(options_frame, text="Manter Dirs Temporários (--keep-temp-dirs)", variable=self.keep_temp_dirs_var).pack(anchor="w")
        ttk.Checkbutton(options_frame, text="Forçar Execução Limpa (--clean-start)", variable=self.clean_start_var).pack(anchor="w")

        reset_button = ttk.Button(options_frame, text="Resetar Parâmetros", command=self.reset_to_defaults)
        reset_button.pack(anchor="w", pady=(10,0))
        
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
    
    def create_log_widgets(self, parent):
        # ... (como antes)
        frame = ttk.LabelFrame(parent, text="Log de Processamento", padding="10")
        frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, height=15, bg="black", fg="limegreen", font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state='disabled')

    def create_action_buttons(self, parent):
        # ... (como antes)
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.X)
        self.start_button = ttk.Button(frame, text="Iniciar Processamento", command=self.start_processing, style="Accent.TButton")
        self.start_button.pack(side=tk.RIGHT, padx=5)
        self.copy_button = ttk.Button(frame, text="Gerar e Copiar Comando", command=self.generate_and_copy_command)
        self.copy_button.pack(side=tk.RIGHT, padx=5)
        self.cancel_button = ttk.Button(frame, text="Cancelar Processo", command=self.cancel_processing)
        ttk.Button(frame, text="Sair", command=self.on_closing).pack(side=tk.LEFT, padx=5)
        style = ttk.Style(self)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    def _build_command(self):
        # ... (como antes)
        if not self.source_files:
            self.log_message("ERRO: Adicione pelo menos um arquivo de origem.\n"); return None

        python_executable = sys.executable
        command = [
            python_executable, "-u", PV_PROCESS_SCRIPT_PATH,
            "-s", *self.source_files,
            "-m", self.min_silence_len_var.get(),
            "-t", self.silence_thresh_var.get(),
            "-p", self.speech_padding_start_var.get(),
            "--speech-padding-end", self.speech_padding_end_var.get(),
            "-k", self.min_silent_speedup_duration_var.get(),
            "-v", self.speedup_factor_var.get(),
            "--chunk-size", self.chunk_size_var.get(),
            "--fade-duration", self.fade_duration_var.get()
        ]

        if self.destination_file_var.get(): command.extend(["-d", self.destination_file_var.get()])
        if self.join_only_var.get(): command.append("--join-only")
        if self.apply_fade_var.get(): command.append("--fade")
        if self.keep_temp_dirs_var.get(): command.append("--keep-temp-dirs")
        if self.clean_start_var.get(): command.append("--clean-start")
        return command

    def generate_and_copy_command(self):
        # ... (como antes)
        command_list = self._build_command()
        if not command_list: return
        command_string = shlex.join(command_list)
        self.clipboard_clear(); self.clipboard_append(command_string)
        self.log_message("--- Comando copiado ---\n" + command_string + "\n\n")

    def start_processing(self):
        # ... (como antes)
        command = self._build_command()
        if not command: return
        self.start_button.pack_forget(); self.copy_button.pack_forget()
        self.cancel_button.pack(side=tk.RIGHT, padx=5)
        self.log_text.config(state='normal'); self.log_text.delete(1.0, tk.END); self.log_text.config(state='disabled')
        self.processing_thread = threading.Thread(target=self.run_script_worker, args=(command,), daemon=True)
        self.processing_thread.start()

    def cancel_processing(self):
        # ... (como antes)
        if self.processing_process and self.processing_process.poll() is None:
            self.log_message("\n--- TENTANDO CANCELAR O PROCESSO... ---\n")
            self.processing_process.terminate()

    def run_script_worker(self, command):
        # ... (como antes)
        try:
            self.log_message("--- Iniciando Processamento ---\n")
            startup_info = None
            if sys.platform == "win32":
                startup_info = subprocess.STARTUPINFO()
                startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.processing_process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                startupinfo=startup_info, bufsize=1
            )
            for line in iter(self.processing_process.stdout.readline, ''): self.log_queue.put(line)
            self.processing_process.stdout.close()
            return_code = self.processing_process.wait()
            if return_code == 0: self.log_queue.put("\n--- Processamento Concluído com Sucesso! ---")
            elif return_code in [-9, -15, 1]: self.log_queue.put("\n--- Processo Cancelado/Interrompido ---")
            else: self.log_queue.put(f"\n--- ERRO: Processo finalizado com código {return_code} ---")
        except Exception as e: self.log_queue.put(f"\n--- ERRO CRÍTICO AO INICIAR O SCRIPT: {e} ---")
        finally:
            self.processing_process = None
            self.log_queue.put("##PROCESS_FINISHED##")

    def process_log_queue(self):
        # ... (como antes)
        try:
            while not self.log_queue.empty():
                line = self.log_queue.get_nowait()
                if line == "##PROCESS_FINISHED##":
                    self.cancel_button.pack_forget()
                    self.start_button.pack(side=tk.RIGHT, padx=5); self.copy_button.pack(side=tk.RIGHT, padx=5)
                else: self.log_message(line)
        except queue.Empty: pass 
        self.after(100, self.process_log_queue)

    def log_message(self, message):
        # ... (como antes)
        self.log_text.config(state='normal'); self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END); self.log_text.config(state='disabled')
    
    def select_source_files(self):
        # ... (como antes)
        files = filedialog.askopenfilenames(title="Selecione os arquivos de vídeo de origem", filetypes=[("Vídeos", "*.mp4 *.mov *.mkv *.avi"), ("Todos", "*.*")])
        for f in files:
            if f not in self.source_files: self.source_files.append(f); self.source_listbox.insert(tk.END, os.path.basename(f))
    
    def remove_selected_source_files(self):
        # ... (como antes)
        selected_indices = self.source_listbox.curselection()
        for i in reversed(selected_indices): self.source_listbox.delete(i); del self.source_files[i]
    
    def clear_source_files(self):
        # ... (como antes)
        self.source_listbox.delete(0, tk.END); self.source_files.clear()
    
    def select_destination_file(self):
        # ... (como antes)
        file = filedialog.asksaveasfilename(title="Definir arquivo de destino", defaultextension=".mp4", filetypes=[("Vídeo MP4", "*.mp4")])
        if file: self.destination_file_var.set(file)

if __name__ == "__main__":
    app = App()
    app.mainloop()