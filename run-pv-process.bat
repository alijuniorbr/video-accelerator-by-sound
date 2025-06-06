
echo -d ./ready/speedup-video.mp4 # nome do arquivo de resultado
echo -m 400 # MIN_SILENCE_LEN_MS = 400
echo -t -42 # SILENCE_THRESH_DBFS = -42db
echo -p 200 # SPEECH_START_PADDING_MS = 200
echo -k 1500 # MIN_ORIGINAL_SILENT_DURATION_FOR_SPEEDUP_S = 1.5
echo -v 4 # criar a TIMES_OF_SPEEDUP (taxa de vezes que acelera o video)
echo -j # NAO faz nenhum processamento para segmentacao e aceleracao, apenas une os arquivos de origem
echo -s ./file-01.mp4 ./dir1/file2.mp4 ./ file-03.mov # um ou mais arquivos de origem

python pv-process.py -d "C:\Users\alijunior\Videos\03-pedido-online-parte-01.mp4" -t -42 -p 200 -m 2000 -s "c:\Users\alijunior\FromMac\online-pedido\2025-05-31 21-34-05 - 03-pedido-online-parte-01.mov"
python pv-process.py -d "C:\Users\alijunior\Videos\03-pedido-online-parte-02.mp4" -t -42 -p 200 -m 2000 -s "c:\Users\alijunior\FromMac\online-pedido\2025-05-31 21-34-05 - 03-pedido-online-parte-02.mov"
rem python pv-process.py -d "C:\Users\alijunior\Videos\03-pedido-online-parte-01.mp4" -t -42 -p 200 -m 2000 -s "c:\Users\alijunior\FromMac\online-pedido\2025-05-31 21-27-22 - 03-pedido-online-parte-01.mov" "c:\Users\alijunior\FromMac\online-pedido\2025-05-31 21-34-05 - 03-pedido-online-parte-02.mov"
