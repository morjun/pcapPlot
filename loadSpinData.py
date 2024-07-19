import pyshark
import numpy as np
import pandas as pd
import statistics
import argparse
from datetime import datetime

QUIC_TRACE_PACKET_LOSS_RACK = 0
QUIC_TRACE_PACKET_LOSS_FACK = 1
QUIC_TRACE_PACKET_LOSS_PROBE = 2

def loadData(args):
    times = np.array([], dtype=float)
    lostTimes = np.array([], dtype=float)
    cwndTimes = np.array([], dtype=float)
    wMaxTimes = np.array([], dtype=float)

    lossReasons = np.array([], dtype=int)
    spins = np.array([], dtype=int)
    rtts = np.array([], dtype=float)
    cwnds = np.array([], dtype=int)
    wMaxes = np.array([], dtype=int)

    initialTime = 0
    initialSpinTime = 0
    prevSpin = -1  # 처음 Short Header Packet 감지용
    prevTime = 0
    numSpin = -1  # 처음 Short Header Packet의 spin bit 0이 발견되는 순간 spin 횟수 0
    spinFrame = None

    ports = {"interop": 4433, "samplequic": 4567}
    port = 0
    if args.file[0] not in ports:
        port = 4567
    else:
        port = ports[args.file[0]]

    try:
        spinFrame = pd.read_csv(f"{args.file[0]}_spin.csv")
    except FileNotFoundError:
        cap = None
        try:
            cap = pyshark.FileCapture(f"{args.file[0]}.pcapng")
        except FileNotFoundError:
            cap = pyshark.FileCapture(f"{args.file[0]}.pcap")
        loadStartTime = datetime.now()
        for packet in cap:
            if hasattr(packet, "quic"):
                if initialTime == 0:  # int
                    initialTime = (
                        packet.sniff_time.timestamp()
                    )  # Initial 패킷의 전송을 기준 시각으로
                if hasattr(packet.quic, "spin_bit"):
                    if packet.udp.srcport == str(port):  # 서버가 전송한 패킷만
                        time = packet.sniff_time.timestamp() - initialTime
                        spin = packet.quic.spin_bit
                        if type(spin) == str:
                            if spin == "True":
                                spin = 1
                            else:  # False
                                spin = 0
                        if prevSpin != spin:
                            numSpin += 1
                            if prevTime != 0:
                                rtt = time - prevTime
                                rtts = np.append(rtts, float(rtt))  # spin -> rtt 계산
                            else:
                                initialSpinTime = time
                            prevTime = time
                        times = np.append(times, float(time))
                        spins = np.append(spins, int(spin))
                        prevSpin = spin
                        if (int(packet.number) % 1000) == 0:
                            print(f"{packet.number} packets processed")
        print(f"load time: {datetime.now() - loadStartTime}")
        spinFrame = pd.DataFrame({"time": times, "spin": spins})
        spinFrame.to_csv(f"{args.file[0]}_spin.csv", index=False)

    throughputFrame = pd.read_csv(f"{args.file[0]}.csv")
    with open(f"{args.file[0]}.log") as f:
        lines = f.readlines()
        initialLogTime = 0
        for line in lines:
            timeString = str(line.split("]")[2].replace("[", ""))
            # if "[S][RX][0] LH Ver:" in line and "Type:I" in line: # 감지가 안 돼.. 어째서지?
            if "Handshake start" in line:
                initialLogTime = datetime.strptime(
                    timeString, "%H:%M:%S.%f"
                )  # Initial 패킷의 전송을 기준 시각으로
            else:
                if initialLogTime == 0:
                    continue
                logTime = (
                    datetime.strptime(timeString, "%H:%M:%S.%f") - initialLogTime
                ).total_seconds()
                if "Lost: " in line and "[conn]" in line:
                    lossReason = int(line.split("Lost: ")[1].split(" ")[0])
                    lostTimes = np.append(lostTimes, float(logTime))
                    lossReasons = np.append(lossReasons, int(lossReason))
                elif "OUT: " in line and "CWnd=" in line:
                    cwnd = int(line.split("CWnd=")[1].split(" ")[0])
                    cwnds = np.append(cwnds, int(cwnd))
                    cwndTimes = np.append(cwndTimes, float(logTime))
                elif "WindowMax" in line:
                    wMax = int(line.split("WindowMax=")[1].split(" ")[0])
                    wMaxes = np.append(wMaxes, int(wMax))
                    wMaxTimes = np.append(wMaxTimes, float(logTime))

    throughputFrame["All Packets"] = [
        # (x * 8 / 1000000) / throughputFrame["Interval start"][1]
        (x * 8) / throughputFrame["Interval start"][1]
        for x in throughputFrame["All Packets"]
    ]  # Bp100ms -> Mbps

    lostFrame = pd.DataFrame({"time": lostTimes, "loss": lossReasons})
    cwndFrame = pd.DataFrame({"time": cwndTimes, "cwnd": cwnds})
    wMaxFrame = pd.DataFrame({"time": wMaxTimes, "wMax": wMaxes})
    avgThroughput = statistics.mean(throughputFrame["All Packets"]) / 1000000

    if prevTime > 0:
        print(prevTime, initialSpinTime)
        if (prevTime != initialSpinTime):
            spinFrequency = numSpin / (2 * (prevTime - initialSpinTime))
        else:
            print("DIVISON BY ZERO")
            exit(1)
        print(f"첫 short packet time: {initialSpinTime}초")
        print(f"마지막 spin time: {prevTime}초")
        print(f"평균 spin frequency: {spinFrequency}Hz")
    if numSpin >= 0:
        print(f"총 spin 수 : {numSpin}")
        print(f"평균 rtt(spin bit 기준): {statistics.mean(rtts)}초")

    numLosses = len(lostFrame['loss'])

    print(f"평균 throughput: {avgThroughput}Mbps")
    print(f"Lost 개수: {numLosses}개")
    print(f"Loss reason 0: {len(lostFrame[lostFrame['loss'] == 0])}개")
    print(f"Loss reason 1: {len(lostFrame[lostFrame['loss'] == 1])}개")
    print(f"Loss reason 2: {len(lostFrame[lostFrame['loss'] == 2])}개")

    if args.bandwidth >= 0 and prevTime > 0:
        with open("stats.csv", "a") as f:
            f.write(
                f"{args.loss}, {args.bandwidth}, {args.delay}, {spinFrequency}, {avgThroughput}, {numLosses}\n"
            )

    lostFrame.to_csv(f"{args.file[0]}_lost.csv", index=False)
    cwndFrame.to_csv(f"{args.file[0]}_cwnd.csv", index=False)
    wMaxFrame.to_csv(f"{args.file[0]}_wMax.csv", index=False)

    # cf1 = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest", tolerance=0.01)
    # cf2 = pd.merge_asof(lostFrame, spinFrame, on="time", direction="nearest", tolerance=0.01)
    # cf3 = pd.concat([cf1, cf2[cf2['loss'].isnull()]]).sort_index()
    # cf3 = pd.merge(spinFrame, lostFrame, on="time", how="outer", sort=True)

    # combinedFrame = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest")
    # combinedFrame = pd.merge_asof(combinedFrame, cwndFrame, on="time", direction="nearest")
    # combinedFrame.to_csv(f"{args.file[0]}_combined.csv", index=False)

    return spinFrame, throughputFrame, lostFrame, cwndFrame, wMaxFrame

def main():
    parser = argparse.ArgumentParser(description="Show spin bit")
    parser.add_argument("file", metavar="file", type=str, nargs=1)
    parser.add_argument(
        "-c",
        "--csv",
        action="store_true",
        help="Additional csv handling",
        required=False,
    )
    parser.add_argument(
        "-l",
        "--loss",
        type=float,
        default=0.0,
        help="loss rate of the link(%)",
        required=False,
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=int,
        default=0,
        help="delay of the link(ms)",
        required=False,
    )
    parser.add_argument(
        "-b",
        "--bandwidth",
        type=int,
        default=-1,
        help="bandwidth of the link(Mbps)",
        required=False,
    )
    args = parser.parse_args()
    if args.csv:
        tempFrame = pd.read_csv(f"{args.file[0]}.csv")
        tempFrame = tempFrame[["Start", "Bytes"]]
        tempFrame.rename(columns={"Start": "Interval start", "Bytes": "All Packets"}, inplace=True)
        tempFrame.to_csv(f"{args.file[0]}.csv", index=False)

    loadData(args)


if __name__ == "__main__":
    main()