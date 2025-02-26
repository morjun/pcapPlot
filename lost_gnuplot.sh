#!/bin/bash

# command line argument로 입력 파일과 출력 파일을 받음
INPUT_FILE=$1
OUTPUT_FILE=$2

# Gnuplot 스크립트 생성
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

    plot "$INPUT_FILE" using 1:2 with points linestyle 1 title 'PROBE', \
         "$INPUT_FILE" using 1:3 with points linestyle 1 title 'FACK', \
         "$INPUT_FILE" using 1:4 with points linestyle 1 title 'RACK'
EOF
