preciso de um script que receba como parametros:

-d ./ready/speedup-video.mp4 # nome do arquivo de resultado

-m 400 # MIN_SILENCE_LEN_MS = 400
-t -42 # SILENCE_THRESH_DBFS = -42
-p 200 # SPEECH_START_PADDING_MS = 200

-k 1500 # MIN_ORIGINAL_SILENT_DURATION_FOR_SPEEDUP_S = 1.5
-v 4 # criar a TIMES_OF_SPEEDUP (taxa de vezes que acelera o video)

-j # NAO faz nenhum processamento para segmentacao e aceleracao, apenas une os arquivos de origem

-s ./file-01.mp4 ./dir1/file2.mp4 ./ file-03.mov # um ou mais arquivos de origem

entao ele deve executar as acoes para cada um dos arquivos:

dividir em segmentos de acordo com silencio/fala (segment_video_by_audio.py)
acelere os segmentos sem audio (accelerate_silent_segments.py)

no final, deve fazer o join de todos os segmentos de todos arquivos de origem em um unico arquivo -d (destino) obedecendo os \_faster existentes

unir todos os segmentos de todos os videos na ordem recebida (join_segments.py)

deve gravar tambem um arquivo json com o mesmo nome do arquivo -d com extensao json contendo
todos os dados passados como parametro, o array com os arquivos de origem, cada um dos indexes, caso seja criado um \_faster, o indice dele tambem, com todos os dados iguais aos outros, a data e hora de inicio e final, o tempo de processamento, o tamanho de bytes de cada arquivo e o total de bytes de origem, o total de bytes do resultado, a taxa de conversao, a economia de bytes, e um ultimo array do arquivo de resultado com o indice dele tambem e de todos os segmentos que compuseram, ai so vem os \_speech, \_silent e \_faster que foram utilizados no join.

o json tera nesse caso um array com 4 objetos, um pra cada arquivo, e em cada arquivo todos os parametros de video ja presentes no sound_index para cada video, e um array com os segmentos daqueel video, os de origem os segmentos de tempo incluindo os faster, e o de destino com os parametros e um array com os segmentos que compuseram o arquivo destino.

quero que salve um arquivo txt com resumo da seguinte forma:

START: 01/01/2001 01:02:03
END : 01/01/2001 01:02:03
ELAPSED : 01:30:00 ( 630 segundos )
STATUS : SUCCEED
SIZE START: 485.7mb (497658952 bytes)
SIZE END: 254.7mb (231658952 bytes)
SIZE ECO: 135.8 mb (...)
TIME START: 00:32:00 ( 630 segundos )
TIME END: 00:21:00 ( 430 segundos )
TIME ECO: 00:11:00 (...)
FRAME START: 134564 frames
FRAME END: 102548 frames
FRAME ECO: 35214 frames
FILE DEST: /dir/vid/ready/speedup-video.mp4
FILE SRC : /dir/vid/file-01.mp4
/dir/vid/dir1/file2.mp4
/dir/vid/file-03.mov

esse comando devo chamar do terminal, por ex:

pv -d ./ready/speedup-video.mp4 -m 400 -t -42 -p 200 -k 1500 -v 4 -s ./file-01.mp4 ./dir1/file2.mp4 ./ file-03.mov

esse atalho pv deve ser incluido no ~/.zshrc para chamar o script ou programa

os scripts utilizados (segment_video_by_audio.py) (accelerate_silent_segments.py)(join_segments.py)
terao seus nomes modificados para

pv-process(.py|.sh)
pv-step-01-audio-segment.py
pv-step-02-silent-accelerator.py
pv-step-03-segment-join.py

e nao precisam estar no diretorio que faz a chamada, pois irei copiar os arquivos que quero processar e unir no finder e colar apos o comando no console no dir que quero o aruivo de resultado

se algum parametro nao for informado, os indicados devem ser utilizados
se nenhum arquivo de destino for indicado grava como video-join-03-01.01.2001.01.02.03.mp4 para tres arquivos conforme o exemplo

acredito que os scripts serao reformulados para receber os parametros, preciso de indicacoes de como fazer para salvar os scripts completos, onde colocar para estarem disponiveis para o script principal que sera encurtado como pv ou proc-video ou fast-video conforme eu resolver o nome do alias apontando para o pv-process.py
