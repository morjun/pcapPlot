import pandas as pd
import numpy as np
import subprocess
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description='Generate lost packet detection plots.')
    parser.add_argument("csv_path", type=str, help="Path to the lost dataset file(l*b*d*_lost.csv).")
    parser.add_argument("-o", "--output", type=str, help="Path to the output file.")
    parser.add_argument("-t", "--title", type=str, help="Title of the plot.")
    args = parser.parse_args()

    output_path = args.output
    csv_path = args.csv_path

    # Generate Gnuplot script
    gnuplot_script = f"""
        set terminal png size 800,300
        set output "{output_path}"
        set datafile separator "," 
        
        set title "Loss Detection; {args.title}"
        set xlabel "time (sec.)"
        set ylabel ""
        set xtics 10
        set ytics nomirror

        # Define the plot styles
        set style line 1 lc rgb 'purple' pt "+" ps 1.5   # PROBE, FACK, RACK color and point styles

        # Time and loss data; 
        # plot loss column where 0 corresponds to RACK, 1 to FACK, and 2 to PROBE

        # Set y-axis range (adjust the values as needed)
        set yrange [0:2]

        set ytics ("RACK" 0, "FACK" 1, "PROBE" 2)
        plot "{csv_path}" using 1:2 with points pt "+" title 'Loss'

        # plot "{csv_path}" using 1:($2==0 ? 1/0 : 1/1):1 with points linestyle 1 title 'RACK', \
        #     "{csv_path}" using 1:($2==1 ? 1/0 : 1/1):1 with points linestyle 1 title 'FACK', \
        #     "{csv_path}" using 1:($2==2 ? 1/0 : 1/1):1 with points linestyle 1 title 'PROBE'
    """

    # Save Gnuplot script to a file
    script_file = f"plot.plt"
    with open(script_file, 'w') as f:
        f.write(gnuplot_script)

    # Execute Gnuplot script
    subprocess.run(['gnuplot', script_file])

    # Optionally remove temporary files
    # os.remove(temp_file)
    os.remove(script_file)

    print("Plots have been generated for each group.")

if __name__ == "__main__":
    main()