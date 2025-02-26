#!/bin/bash

# command line argument로 입력 파일과 출력 파일을 받음
INPUT_FILE=$1
OUTPUT_FILE=$2

echo $INPUT_FILE
echo $OUTPUT_FILE
# Gnuplot 스크립트 실행
gnuplot <<- EOF
    set terminal pngcairo size 800,600
    set output "$OUTPUT_FILE"
    
    set title "Loss Detection"
    set xlabel "time (sec.)"
    set ylabel "Signals"
    set xtics 10
    set ytics nomirror

    # Define the plot styles
    set style line 1 lc rgb 'purple' pt 7 ps 1.5   # PROBE, FACK, RACK color and point styles

    # Time and loss data; 
    # plot loss column where 0 corresponds to RACK, 1 to FACK, and 2 to PROBE
    plot "$INPUT_FILE" using 1:($2==0 ? 1/0 : 1/1) with points linestyle 1 title 'RACK', \
         "$INPUT_FILE" using 1:($2==1 ? 1/0 : 1/1) with points linestyle 1 title 'FACK', \
         "$INPUT_FILE" using 1:($2==2 ? 1/0 : 1/1) with points linestyle 1 title 'PROBE'
EOF

