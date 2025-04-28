import pandas as pd
import numpy as np
import subprocess
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description='Generate probability distribution plots for avgThroughput.')
    parser.add_argument("file_path", type=str, help="Path to the dataset file(stats.csv).")
    args = parser.parse_args()


    # Load the dataset
    # file_path = '/mnt/data/stats.csv'
    file_path = args.file_path

    data = pd.read_csv(file_path)

    # Group by lossRate, bandwidth, and delay
    grouped = data.groupby(['lossRate', 'bandwidth', 'delay'])

    # Generate a probability distribution for each group
    for (lossRate, bandwidth, delay), group in grouped:
        avg_throughput = group['avgThroughput']
        
        # Save avgThroughput distribution to a temporary file for Gnuplot
        temp_file = f"temp_{lossRate}_{bandwidth}_{delay}.dat"
        avg_throughput.to_csv(temp_file, index=False, header=False)

        # Generate Gnuplot script
        gnuplot_script = f"""
        set terminal png size 800,600
        set output 'distribution_{lossRate}_{bandwidth}_{delay}.png'
        set title 'Probability Distribution of avgThroughput(Mbps) (lossRate={lossRate}%, bandwidth={bandwidth}Mbps, delay={delay}ms)'
        set xlabel 'avgThroughput(Mbps)'
        set ylabel 'Probability Density'
        bin_width = 0.5
        bin(x, width) = width * floor(x / width) + width / 2.0
        plot '{temp_file}' using (bin($1, bin_width)):(1.0) smooth freq with boxes title 'avgThroughput'
        """

        # Save Gnuplot script to a file
        script_file = f"plot_{lossRate}_{bandwidth}_{delay}.plt"
        with open(script_file, 'w') as f:
            f.write(gnuplot_script)

        # Execute Gnuplot script
        subprocess.run(['gnuplot', script_file])

        # Optionally remove temporary files
        os.remove(temp_file)
        os.remove(script_file)

    print("Plots have been generated for each group.")

if __name__ == "__main__":
    main()
