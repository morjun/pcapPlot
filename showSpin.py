import pyshark

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from matplotlib import ticker

def main():
    times = []
    lostTimes = []
    spins = []

    cap = pyshark.FileCapture("interlop.pcapng", display_filter='quic')
    initialTime = cap[0].sniff_time.timestamp()
    for packet in cap:
        if int(packet.number) > 1000:
             break
        if hasattr(packet, 'quic') and hasattr(packet.quic, 'spin_bit'):
                time = packet.sniff_time.timestamp() - initialTime
                spin = packet.quic.spin_bit
                times.append(float(time))
                spins.append(int(spin))

                # print(packet)

    df = pd.DataFrame({'time': times, 'spin': spins})

    # with open("dropLog.txt", "r") as f:
    #     lines = f.readlines()
    #     for line in lines:
    #         if ("RxDrop" in line):
    #             splitted = line.split(' ')
    #             time = splitted[-1]
    #             lostTimes.append(float(time))
    #             print(time)

    fig, ax = plt.subplots(sharex=True, sharey=True)
    fig.set_size_inches(15, 3)

    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter('%0.9f'))
    ax.plot(df.time,df.spin, markersize=1,)

    # ax.plot(lostTimes, np.ones(len(lostTimes)), 'r*', markersize=10, label='drop')
    # ax.legend()

    plt.xticks(times, rotation = 45)
    plt.yticks([1.0, 0.0])
    plt.xlim(1, 5.0)

    plt.show()


if __name__ == '__main__':
    main()