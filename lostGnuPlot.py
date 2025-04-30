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
        # Gnuplot script to plot RACK, FACK, PROBE with different colors

        # Set terminal and output file
        set terminal png size 800,400
        set output "{output_path}" # Replace {output_path} with your desired output PNG file name

        # Set data file specifics
        set datafile separator ","

        # Set graph titles and labels
        set title "{args.title}" # Replace {args.title} with your desired title
        set xlabel "time (sec.)"
        set ylabel "" # Y-axis label is handled by ytics

        # Set axis ticks
        # set xtics 10
        set ytics nomirror
        # Define custom y-axis labels for the values 0, 1, 2
        set ytics ("RACK" 0, "FACK" 1, "PROBE" 2)
        # Set y-axis range explicitly to ensure all labels are shown
        set yrange [-1.0:3.0] # Adjust range slightly for better visibility of points at 0 and 2

        # --- Grid ---
        set grid

        # --- Plotting ---
        # Use point type 7 (filled circle) and adjust point size (ps) if needed.
        # Use lc rgb 'colorname' for specific colors.
        # Plot data conditionally:
        #   using 1:($2==0 ? 0 : 1/0) -> If column 2 is 0, plot at y=0, otherwise plot undefined (skip)
        #   '' -> shortcut to reuse the last specified datafile ("{csv_path}")

        plot "{csv_path}" using 1:($2==0 ? 0 : 1/0) with points pt "+" ps 1.5 lc rgb 'red' title 'RACK', \
            '' using 1:($2==1 ? 1 : 1/0) with points pt "+" ps 1.5 lc rgb 'cyan' title 'FACK', \
            '' using 1:($2==2 ? 2 : 1/0) with points pt "+" ps 1.5 lc rgb 'purple' title 'PROBE'

        # Optional: Unset output if you want Gnuplot to potentially show the plot in a window afterwards
        # unset output

        # Optional: Pause script execution if running from command line
        # pause -1 "Press Enter to exit..."
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