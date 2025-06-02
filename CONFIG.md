# Instruções de Uso - Processador de Vídeo (pv-process)

Este conjunto de scripts automatiza a segmentação de vídeos com base em análise de áudio (detectando fala e silêncio), acelera os trechos de silêncio e une todos os segmentos resultantes de um ou mais vídeos de origem em um único arquivo final.

## Pré-requisitos

1.  **Python 3:** Idealmente Python 3.9 ou superior.
2.  **FFmpeg e ffprobe:** Devem estar instalados e acessíveis no PATH do seu sistema. São essenciais para manipulação de vídeo e áudio.
    - No macOS, a forma mais fácil de instalar/gerenciar é via Homebrew: `brew install ffmpeg`
3.  **Bibliotecas Python:** `moviepy` e `pydub`. Estas devem ser instaladas em um ambiente virtual.

## Configuração Inicial

Siga estes passos uma vez para preparar seu ambiente:

**1. Crie um Ambiente Virtual (venv):**
É altamente recomendável usar um ambiente virtual para isolar as dependências deste projeto.

- Navegue no terminal até a pasta onde você salvou os scripts Python (ex: `~/scripts/pv_ferramenta`).
- Crie o ambiente virtual (vamos chamá-lo de `pv_env` aqui, mas pode ser qualquer nome como `venv`):
  ```bash
  python3 -m venv pv_env
  ```

**2. Ative o Ambiente Virtual:**

- Para ativar (no mesmo terminal ou em um novo, na pasta do projeto):
  ```bash
  source pv_env/bin/activate
  ```
- Seu prompt do terminal deve mudar, mostrando algo como `(pv_env)` no início, indicando que o ambiente virtual está ativo.

**3. Instale as Dependências Python:**

- Com o ambiente virtual ativo, instale as bibliotecas necessárias:
  ```bash
  pip install moviepy pydub
  ```

**4. Salve os Scripts:**
Certifique-se de que os seguintes arquivos Python estejam todos no mesmo diretório (ex: `~/scripts/pv_ferramenta/`):

- `pv-process.py` (o script mestre)
- `pv_utils.py`
- `pv_step_01_audio_segment.py`
- `pv_step_02_silent_accelerator.py`
- `pv_step_03_segment_join.py`

**5. Configure um Alias (Opcional, mas Recomendado):**
Para facilitar a chamada do script mestre, você pode criar um alias. Adicione a seguinte linha ao seu arquivo de configuração do shell (ex: `~/.zshrc` para Zsh, ou `~/.bash_profile` ou `~/.bashrc` para Bash):

```bash
alias pv='python3 /caminho/completo/para/seu/pv-process.py'
```

**6. Gerenciamento do Ambiente Virtual do Python (venv):**

Como mencionei, vou listar os comandos para você incluir na seção de "Configuração Inicial" do `instructions.md`. Um script separado para isso não é tão prático quanto fornecer os comandos diretamente, pois a ativação (`source`) é um comando do próprio shell.

**No `instructions.md`, na seção "Configuração Inicial", você já tem os passos. Eles são:**

1.  **Navegue até a pasta do projeto:**

    ```bash
    cd /caminho/para/sua/pasta_do_projeto
    ```

2.  **Crie o ambiente virtual (ex: `pv_env`):**

    ```bash
    python3 -m venv pv_env
    ```

3.  **Ative o ambiente virtual:**

    - Para macOS/Linux (Zsh, Bash):
      ```bash
      source pv_env/bin/activate
      ```
    - Para Windows (Command Prompt):
      ```cmd
      pv_env\Scripts\activate.bat
      ```
    - Para Windows (PowerShell):
      `powershell
.\pv_env\Scripts\Activate.ps1
`
      (Seu prompt do terminal mudará para indicar que o venv está ativo, ex: `(pv_env) ...$`)

4.  **Instale as dependências (com o venv ativo):**

    ```bash
    pip install moviepy pydub
    ```

5.  **Para desativar o ambiente virtual (quando terminar de usar):**
    Simplesmente digite no terminal:
    ```bash
    deactivate
    ```

Estes são os comandos essenciais para o ambiente virtual. O `instructions.md` acima já os cobre na seção de configuração.

Espero que este arquivo de instruções seja claro e útil!
