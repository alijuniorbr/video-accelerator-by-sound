# pv_gui.py
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import subprocess
import threading
import queue
import os
import sys

# --- CONFIGURAÇÃO ---
# Verifique se este caminho está correto ou se o pv-process.py está no mesmo diretório
# Se os scripts estiverem na mesma pasta, apenas o nome do arquivo é suficiente.
# Para mais robustez, pode-se usar o caminho absoluto.
PV_PROCESS_SCRIPT_PATH = "pv-process.py" 
# --------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Processador de Vídeo (PV)")
        self.geometry("800x750")

        self.source_files = []

        # --- Variáveis de controle para os widgets ---
        self.destination_file_var = tk.StringVar()
        self.min_silence_len_var = tk.StringVar(value="2000")
        self.silence_thresh_var = tk.StringVar(value="-35")
        self.speech_padding_var = tk.StringVar(value="200")
        self.min_silent_speedup_duration_var = tk.StringVar(value="1500")
        self.speedup_factor_var = tk.StringVar(value="4")
        self.chunk_size_var = tk.StringVar(value="500")
        self.join_only_var = tk.BooleanVar(value=False)

        # Fila para comunicação entre a thread de processamento e a GUI
        self.log_queue = queue.Queue()

        # Cria a estrutura principal da janela com frames
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Cria as seções da GUI
        self.create_file_selection_widgets(main_frame)
        self.create_parameters_widgets(main_frame)
        self.create_log_widgets(main_frame)
        self.create_action_buttons(main_frame)

        # Inicia o loop para verificar a fila de logs
        self.after(100, self.process_log_queue)

    def create_file_selection_widgets(self, parent):
        frame = ttk.LabelFrame(parent, text="Seleção de Arquivos", padding="10")
        frame.pack(fill=tk.X, expand=True, pady=5)

        # --- Arquivos de Origem ---
        ttk.Label(frame, text="Arquivos de Origem:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        
        self.source_listbox = tk.Listbox(frame, height=5, selectmode=tk.EXTENDED)
        self.source_listbox.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)

        source_buttons_frame = ttk.Frame(frame)
        source_buttons_frame.grid(row=1, column=2, sticky="ns", padx=5)
        
        ttk.Button(source_buttons_frame, text="Adicionar Arquivos...", command=self.select_source_files).pack(fill=tk.X, pady=2)
        ttk.Button(source_buttons_frame, text="Remover Selecionado", command=self.remove_selected_source_files).pack(fill=tk.X, pady=2)
        ttk.Button(source_buttons_frame, text="Limpar Lista", command=self.clear_source_files).pack(fill=tk.X, pady=2)

        # --- Arquivo de Destino ---
        ttk.Label(frame, text="Arquivo de Destino:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        
        dest_entry = ttk.Entry(frame, textvariable=self.destination_file_var)
        dest_entry.grid(row=3, column=0, columnspan=2, sticky="ew", padx=5)
        
        ttk.Button(frame, text="Salvar Como...", command=self.select_destination_file).grid(row=3, column=2, padx=5)
        
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def create_parameters_widgets(self, parent):
        frame = ttk.LabelFrame(parent, text="Parâmetros de Processamento", padding="10")
        frame.pack(fill=tk.X, expand=True, pady=5)
        
        # Cria campos para cada parâmetro
        params = [
            ("Duração Mín. Silêncio (ms) [-m]:", self.min_silence_len_var),
            ("Limiar de Silêncio (dBFS) [-t]:", self.silence_thresh_var),
            ("Padding da Fala (ms) [-p]:", self.speech_padding_var),
            ("Duração Mín. p/ Acelerar (ms) [-k]:", self.min_silent_speedup_duration_var),
            ("Fator de Aceleração [-v]:", self.speedup_factor_var),
            ("Tamanho do Chunk (MB) [0=desativado]:", self.chunk_size_var),
        ]
        
        for i, (label_text, var) in enumerate(params):
            ttk.Label(frame, text=label_text).grid(row=i, column=0, sticky="w", padx=5, pady=2)
            ttk.Entry(frame, textvariable=var, width=10).grid(row=i, column=1, sticky="w", padx=5, pady=2)

        # Checkbox para o modo "Apenas Juntar"
        self.join_only_checkbox = ttk.Checkbutton(frame, text="Apenas Juntar arquivos de origem (ignora outras etapas)", variable=self.join_only_var)
        self.join_only_checkbox.grid(row=len(params), column=0, columnspan=2, sticky="w", padx=5, pady=5)
    
    def create_log_widgets(self, parent):
        frame = ttk.LabelFrame(parent, text="Log de Processamento", padding="10")
        frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state='disabled')

    def create_action_buttons(self, parent):
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.X)
        
        self.start_button = ttk.Button(frame, text="Iniciar Processamento", command=self.start_processing)
        self.start_button.pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(frame, text="Sair", command=self.quit).pack(side=tk.LEFT, padx=5)

    def select_source_files(self):
        files = filedialog.askopenfilenames(
            title="Selecione os arquivos de vídeo de origem",
            filetypes=[("Arquivos de Vídeo", "*.mp4 *.mov *.mkv *.avi"), ("Todos os arquivos", "*.*")]
        )
        for f in files:
            if f not in self.source_files:
                self.source_files.append(f)
                self.source_listbox.insert(tk.END, os.path.basename(f))
    
    def remove_selected_source_files(self):
        selected_indices = self.source_listbox.curselection()
        # Itera de trás para frente para não bagunçar os índices ao remover
        for i in reversed(selected_indices):
            self.source_listbox.delete(i)
            del self.source_files[i]

    def clear_source_files(self):
        self.source_listbox.delete(0, tk.END)
        self.source_files.clear()

    def select_destination_file(self):
        file = filedialog.asksaveasfilename(
            title="Definir arquivo de destino",
            defaultextension=".mp4",
            filetypes=[("Vídeo MP4", "*.mp4")]
        )
        if file:
            self.destination_file_var.set(file)

    def start_processing(self):
        if not self.source_files:
            self.log_message("ERRO: Por favor, adicione pelo menos um arquivo de origem.")
            return

        self.start_button.config(state="disabled")
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        # Executa o script em uma thread separada para não travar a GUI
        processing_thread = threading.Thread(target=self.run_script_worker, daemon=True)
        processing_thread.start()

    def run_script_worker(self):
        try:
            python_executable = sys.executable # Usa o python do VENV
            command = [
                python_executable,
                PV_PROCESS_SCRIPT_PATH,
                "-s", *self.source_files,
                "-m", self.min_silence_len_var.get(),
                "-t", self.silence_thresh_var.get(),
                "-p", self.speech_padding_var.get(),
                "-k", self.min_silent_speedup_duration_var.get(),
                "-v", self.speedup_factor_var.get(),
                "--chunk-size", self.chunk_size_var.get()
            ]

            if self.destination_file_var.get():
                command.extend(["-d", self.destination_file_var.get()])
            
            if self.join_only_var.get():
                command.append("-j")
            
            self.log_message("--- Iniciando Processamento ---\n")
            self.log_message(f"Comando: {' '.join(command)}\n\n")

            # Inicia o subprocesso
            process = subprocess.Popen(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, # Redireciona stderr para stdout
                text=True, 
                encoding='utf-8', 
                errors='replace',
                # A flag abaixo ajuda a não criar uma janela de console extra no Windows
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Lê a saída do processo em tempo real e a coloca na fila
            for line in iter(process.stdout.readline, ''):
                self.log_queue.put(line)
            
            process.stdout.close()
            return_code = process.wait()
            
            if return_code == 0:
                self.log_queue.put("\n--- Processamento Concluído com Sucesso! ---")
            else:
                self.log_queue.put(f"\n--- ERRO: Processo finalizado com código {return_code} ---")

        except Exception as e:
            self.log_queue.put(f"\n--- ERRO CRÍTICO AO INICIAR O SCRIPT: {e} ---")
        finally:
            # Sinaliza para reativar o botão na thread principal
            self.log_queue.put("##PROCESS_FINISHED##")

    def process_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line == "##PROCESS_FINISHED##":
                    self.start_button.config(state="normal")
                else:
                    self.log_message(line)
        except queue.Empty:
            pass # Fila está vazia, continua esperando
        
        # Agenda a próxima verificação da fila
        self.after(100, self.process_log_queue)

    def log_message(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END) # Auto-scroll para o final
        self.log_text.config(state='disabled')

if __name__ == "__main__":
    app = App()
    app.mainloop()