import pyshark

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statistics

import argparse
from datetime import datetime

from matplotlib import ticker


#파일명.csv (throughput 기록), 파일명.pcapng (wireshark 패킷트레이스), 파일명.log(msquic log, loss 추적용) 필요
def main():
    parser = argparse.ArgumentParser(description='Show spin bit')
    parser.add_argument('file', metavar='file', type=str, nargs=1)
    args = parser.parse_args()
    prevSpin = 0
    prevTime = 0

    times = []
    lostTimes = []
    spins = []
    rtts = []

    ports = {"interop" : 4433, "samplequic" : 4567}
    port = 0
    if args.file[0] not in ports:
        port = 4567
    else:
        port = ports[args.file[0]]

    cap = pyshark.FileCapture(f"{args.file[0]}.pcapng")
    initialTime = cap[0].sniff_time.timestamp()
    for packet in cap:
        if int(packet.number) > 100:
            # print("out")
            break

        elif hasattr(packet, 'quic'):
            if (initialTime == 0):
                initialTime = packet.sniff_time.timestamp()
            if hasattr(packet.quic, 'spin_bit'):
                if hasattr(packet, 'udp'):
                    if packet.udp.srcport == str(port):
                        time = packet.sniff_time.timestamp() - initialTime
                        spin = packet.quic.spin_bit
                        if prevSpin != spin:
                            if (prevTime != 0):
                                rtt = time - prevTime
                                rtts.append(float(rtt)) # spin -> rtt 계산
                            prevTime = time
                        times.append(float(time))
                        spins.append(int(spin))
                        prevSpin = spin
                else:
                    print(packet)

    print(f"평균 rtt(spin bit 기준): {statistics.mean(rtts)}")

    df = pd.DataFrame({'time': times, 'spin': spins})
    throughputFrame = pd.read_csv(f"{args.file[0]}.csv")
    print(throughputFrame)
    print(throughputFrame['All Packets'], throughputFrame['Interval start'], throughputFrame['TCP Errors'])

    with open(f"{args.file[0]}.log") as f:
        lines = f.readlines()
        timeString = str(lines[0].split(']')[2].replace('[', ''))
        initialLogtime = datetime.strptime(timeString, '%H:%M:%S.%f')
        for line in lines:
            if "Lost: " in line and "[conn]" in line:
                logTime = (datetime.strptime(line.split(']')[2].replace('[', ''), '%H:%M:%S.%f') - initialLogtime).total_seconds()
                lossCount = int(line.split('Lost: ')[1].split(' ')[0])
                if (lossCount > 0):
                    lostTimes.append(logTime)


    fig, ax = plt.subplots(sharex=True, sharey=True)
    fig.set_size_inches(15, 3)

    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter('%0.9f'))
    ax.set_ylabel('Spin bit')
    ax.set_yticks([1.0, 0.0])
    ax.set_ylim([0, 2])

    ax.plot(df.time,df.spin, markersize=1,)
    drop = ax.plot(lostTimes, np.ones(len(lostTimes)), 'r*', markersize=10, label='drop')

    ax2 = ax.twinx()
    ax2.set_ylabel('Throughput (Mbps)')
    throughputFrame['All Packets'] = [(x*8/ 1000000)/throughputFrame['Interval start'][1] for x in throughputFrame['All Packets']] # Bp100ms -> Mbps

    ax2.set_ylim([0, max(throughputFrame['All Packets']) * 1.1])
    ax2.yaxis.set_major_locator(ticker.AutoLocator())

    throughput = ax2.plot(throughputFrame['Interval start'], throughputFrame['All Packets'], 'g', label='throughput')

    ax.legend(loc='upper left')
    ax2.legend(loc='upper right')

    plt.xticks(times, rotation = 45)
    # plt.xlim(0, 20.0)
    plt.show()


if __name__ == '__main__':
    main()