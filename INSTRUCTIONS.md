# Parâmetros de Linha de Comando para `pv-process.py`

Este documento detalha todos os parâmetros de linha de comando disponíveis para o script `pv-process.py`, suas funções e valores padrão.

## Sintaxe Geral

```bash
pv [OPÇÕES] -s <arquivo_fonte1.mp4> [arquivo_fonte2.mov ...]
```

ou

```bash
python3 /caminho/completo/para/seu/pv-process.py [OPÇÕES] -s <arquivo_fonte1.mp4> [arquivo_fonte2.mov ...]
```

---

## Opções / Parâmetros

- **`-d ARQUIVO`, `--destination ARQUIVO`**

  - **Descrição:** Especifica o caminho completo e o nome do arquivo para o vídeo final que será gerado após a junção de todos os segmentos processados.
  - **Tipo:** String (caminho do arquivo)
  - **Obrigatório:** Não
  - **Valor Padrão:** Se não fornecido, um nome de arquivo é gerado automaticamente no diretório onde o comando é executado. O formato do nome padrão é `video-join-NUM_ARQUIVOS-DD.MM.YYYY.HH.MM.SS.mp4` (ex: `video-join-02-02.06.2025.15.30.00.mp4` para 2 arquivos de origem processados em 2 de Junho de 2025 às 15:30:00).

- **`-m MS`, `--min-silence-len MS`**

  - **Descrição:** (Etapa 1: Segmentação de Áudio) Define a duração mínima de um silêncio, em milissegundos (MS), para que a biblioteca Pydub o considere um bloco de silêncio distinto. Valores menores detectam pausas mais curtas como silêncio.
  - **Tipo:** Inteiro
  - **Valor Padrão:** `400` (milissegundos)

- **`-t DBFS`, `--silence-thresh DBFS`**

  - **Descrição:** (Etapa 1: Segmentação de Áudio) Define o limiar de silêncio em dBFS (decibéis relativos à escala cheia) para o Pydub. Áudio abaixo deste nível é considerado silêncio. Valores mais negativos (ex: -50) são mais "sensíveis" e tendem a classificar mais partes como fala (ou seja, o silêncio precisa ser mais "silencioso"). Valores menos negativos (ex: -30) são menos sensíveis (o silêncio pode ser um pouco mais "ruidoso").
  - **Tipo:** Inteiro
  - **Valor Padrão:** `-42` (dBFS)

- **`-p MS`, `--speech-padding MS`**

  - **Descrição:** (Etapa 1: Segmentação de Áudio) Define a quantidade de preenchimento (ou "folga"), em milissegundos (MS), a ser adicionada _antes_ do início detectado de um segmento de fala. Isso ajuda a garantir que o comecinho da voz não seja cortado. O segmento de silêncio anterior será correspondentemente encurtado.
  - **Tipo:** Inteiro
  - **Valor Padrão:** `200` (milissegundos)

- **`-k MS`, `--min-silent-speedup-duration MS`**

  - **Descrição:** (Etapa 2: Aceleração de Silêncios) Define a duração mínima original (em milissegundos) que um segmento de silêncio (identificado na Etapa 1) precisa ter para que a Etapa 2 tente acelerá-lo. Segmentos de silêncio mais curtos que este valor não serão acelerados e serão usados na junção com sua duração e velocidade originais.
  - **Tipo:** Inteiro
  - **Valor Padrão:** `1500` (milissegundos, ou seja, 1.5 segundos)

- **`-v N`, `--speedup-factor N`**

  - **Descrição:** (Etapa 2: Aceleração de Silêncios) Define o fator de aceleração para os segmentos de silêncio que atendem ao critério de duração mínima (parâmetro `-k`). Por exemplo, um valor `4` significa que o trecho de silêncio será 4x mais rápido.
  - **Tipo:** Inteiro
  - **Valor Padrão:** `4`

- **`-j`, `--join-only`**

  - **Descrição:** Ativa o modo "apenas junção". Quando esta flag está presente, o script assume que os arquivos fornecidos através da opção `-s` já são os segmentos finais e prontos para serem concatenados. As etapas de segmentação por áudio (Etapa 1) e aceleração de silêncios (Etapa 2) são completamente puladas. Útil se você já processou os segmentos e quer apenas juntá-los ou rejuntá-los.
  - **Tipo:** Flag (não recebe valor; sua presença ativa o modo)

- **`-s ARQUIVO [ARQUIVO ...]`, `--source-files ARQUIVO [ARQUIVO ...]`**

  - **Descrição:** Especifica um ou mais caminhos para os arquivos de vídeo de origem que serão processados. Se a flag `-j` (join-only) estiver ativa, estes são os arquivos de segmento que serão diretamente concatenados na ordem fornecida.
  - **Tipo:** Lista de Strings (caminhos de arquivo)
  - **Obrigatório:** Sim

- **`--keep-temp-dirs`**

  - **Descrição:** Se esta flag for fornecida, os diretórios temporários criados durante o processamento (que contêm os segmentos individuais de cada arquivo de origem, vídeos recodificados para keyframes, etc.) não serão apagados automaticamente no final da execução. Isso pode ser útil para depuração ou para inspecionar os arquivos intermediários.
  - **Tipo:** Flag

- **`--no-kf-re-encode-prompt`**
  - **Descrição:** Desativa o prompt interativo na Etapa 1 (segmentação de áudio) que pergunta ao usuário se deseja re-codificar um vídeo de origem caso ele seja detectado como tendo poucos keyframes. Se esta flag for usada e um vídeo tiver poucos keyframes, o script continuará o processamento usando os keyframes existentes (o que pode não ser ideal para a estratégia de corte sem re-codificação dos segmentos, resultando em poucos ou apenas um segmento para aquele vídeo).
  - **Tipo:** Flag

---

Passos manuais para executar os tres passos do projeto:

Segmentar videos de acord com o audio

```

python3 ./partial-scripts/segment_video_by_audio.py video-teste.mov

```

Acelerar as partes em silencio

```

python3 ./partial-scripts/accelerate_silent_segments.py

```

Unir os segmentos em um unico video

```

python3 ./partial-scripts/join_segments.py

```
