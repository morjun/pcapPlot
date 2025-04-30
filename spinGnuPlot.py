import pandas as pd
import numpy as np
import subprocess
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description='Generate spin bit plots.')
    parser.add_argument("csv_path", type=str, help="Path to the lost dataset file(l*b*d*_spin.csv).")
    parser.add_argument("-o", "--output", type=str, help="Path to the output file.")
    parser.add_argument("-t", "--title", type=str, help="Title of the plot.")
    args = parser.parse_args()

    output_path = args.output
    csv_path = args.csv_path

    # Generate Gnuplot script
    gnuplot_script = f"""
        # Gnuplot 스크립트: 시간 경과에 따른 처리량(Throughput) 그래프 생성

        # --- 출력 설정 ---
        # PNG 파일로 저장 설정 (파일 이름과 크기, 글꼴 등은 필요에 따라 수정)
        # set terminal pngcairo size 800,600 enhanced font 'Verdana,10'
        set terminal pngcairo size 800,600
        set output '{output_path}'  # 저장할 파일 이름

        # --- 데이터 파일 설정 ---
        # CSV 파일의 구분자 설정 (쉼표로 가정)
        set datafile separator ","

        # --- 그래프 제목 및 축 레이블 ---
        set title "{args.title}" # 그래프 전체 제목 (필요한 경우 주석 해제)
        set xlabel "time (sec.)"          # x축 레이블
        set ylabel "spin bit"     # y축 레이블

        # --- 축 범위 및 눈금 ---
        # x축 범위 설정 (데이터에 맞게 자동 설정하려면 주석 처리)
        # set xr [0:220]  # 예시 이미지와 유사하게 설정 (데이터에 따라 조절 필요)
        # y축 범위 설정 (데이터에 맞게 자동 설정하려면 주석 처리)
        set yr [0:10]   # 예시 이미지와 유사하게 설정 (데이터에 따라 조절 필요)

        # 축 눈금 간격 설정 (자동 설정을 원하면 주석 처리)
        # set xtics 50
        # set ytics 2

        # --- 그리드 ---
        # 그래프 배경에 그리드(격자) 표시
        set grid

        # --- 범례 (Key/Legend) ---
        # 범례 위치 및 스타일 설정 (그래프 안쪽, 오른쪽 상단)
        set key top right inside

        set tmargin 5  # 숫자 3은 문자 높이 기준이며, 적절히 조절 (예: 4, 5)

        # 데이터 파일 그리기
        # 'your_data.csv' 부분을 실제 데이터 파일 이름으로 변경해야 합니다.
        # using 1: (...) : 1번 컬럼(time interval start)을 x축으로 사용하고,
        #                  2번 컬럼(total bytes sent)을 megabits_per_sec 함수에 넣어 계산한 결과를 y축으로 사용합니다.
        # with lines : 선 그래프로 그립니다.
        # title '...' : 범례에 표시될 제목을 설정합니다.
        # lc rgb "green" #: 선 색상을 보라색으로 설정합니다.
        # plot '{csv_path}' using 1:(megabits_per_sec(column(2))) with lines title 'CUBIC; normal' lc rgb "green"
        plot '{csv_path}' using 1:2 with lines title 'spin bit' lc rgb "blue"

        # --- 종료 ---
        # 출력 설정을 해제 (일부 터미널에서는 필요)
        # set output
    """

    # Save Gnuplot script to a file
    script_file = f"plot.plt"
    with open(script_file, 'w', encoding="utf-8") as f:
        f.write(gnuplot_script)

    # Execute Gnuplot script
    subprocess.run(['gnuplot', script_file])

    # Optionally remove temporary files
    # os.remove(temp_file)
    os.remove(script_file)

    print("Plots have been generated for each group.")

if __name__ == "__main__":
    main()