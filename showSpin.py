import pyshark

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from matplotlib import ticker

def main():
    times = []
    lostTimes = []
    spins = []

    cap = pyshark.FileCapture("interlop.pcapng")
    initialTime = cap[0].sniff_time.timestamp()
    for packet in cap:
        if int(packet.number) > 2000:
             break
        if hasattr(packet, 'icmp') and packet.icmp.type == '3':
            time = packet.sniff_time.timestamp() - initialTime
            lostTimes.append(float(time))
        elif hasattr(packet, 'quic') and hasattr(packet.quic, 'spin_bit'):
            if hasattr(packet, 'udp'):
                if packet.udp.dstport == '4433':
                    time = packet.sniff_time.timestamp() - initialTime
                    spin = packet.quic.spin_bit
                    times.append(float(time))
                    spins.append(int(spin))
            else:
                print(packet)

    df = pd.DataFrame({'time': times, 'spin': spins})

    fig, ax = plt.subplots(sharex=True, sharey=True)
    fig.set_size_inches(15, 3)

    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter('%0.9f'))
    ax.plot(df.time,df.spin, markersize=1,)

    ax.plot(lostTimes, np.ones(len(lostTimes)), 'r*', markersize=10, label='drop')
    ax.legend()

    plt.xticks(times, rotation = 45)
    plt.yticks([1.0, 0.0])
    plt.xlim(1, 5.0)

    plt.show()


if __name__ == '__main__':
    main()