import pyshark
import numpy as np
import pandas as pd
import statistics
import argparse
import os
import re
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

    stats_file = open("stats.csv", "a", encoding="utf8")

    full_path = args.file[0] # 입력: .../l0b0d0_t0_n
    full_path = os.path.relpath(full_path)

    splitted_path = os.path.split(full_path) # ('...', 'l0b0d0_t0_n')

    arg_path = splitted_path[-1] # l0b0d0_t0_n
    parametric_path = arg_path.split("_t")[0] # l0b0d0
    arg_path_parts = arg_path.split("_")
    filename_prefix = parametric_path
    if len(arg_path_parts) > 2:
        index = arg_path.split("_")[-1] # n
        filename_prefix = f"{parametric_path}_{index}" # l0b0d0_n
    print(f"filename prefix: {filename_prefix}")

    filename_reg = r"l(\d+(.\d+)?)b(\d+)d(\d+)"
    filename_reg = re.compile(filename_reg)
    filename_match = filename_reg.match(filename_prefix)

    loss = float(filename_match.group(1))
    bandwidth = int(filename_match.group(3))
    delay = int(filename_match.group(4))

    print(f"loss: {loss}, bandwidth: {bandwidth}, delay: {delay}")

    # full_path = os.path.join(splitted_path[0], filename_prefix.split("_")[0])

    print(f"full path: {full_path}")
    os.chdir(full_path)

    if args.csv:
        tempFrame = pd.read_csv(f"{filename_prefix}.csv")
        tempFrame = tempFrame[["Start", "Bytes"]]
        tempFrame.rename(
            columns={"Start": "Interval start", "Bytes": "All Packets"}, inplace=True
        )
        tempFrame.to_csv(f"{filename_prefix}.csv", index=False)

    file_ports = {"interop": 4433, "samplequic": 4567}
    port = 0
    if filename_prefix not in file_ports:
        port = 4567
    else:
        port = file_ports[filename_prefix]

    try:
        spinFrame = pd.read_csv(f"{filename_prefix}_spin.csv")
    except FileNotFoundError:
        cap = None
        try:
            cap = pyshark.FileCapture(f"{filename_prefix}.pcapng")
        except FileNotFoundError:
            cap = pyshark.FileCapture(f"{filename_prefix}.pcap")
        loadStartTime = datetime.now()
        for packet in cap:
            if hasattr(packet, "quic"):
                if initialTime == 0:  # int
                    initialTime = (
                        packet.sniff_time.timestamp()
                    )  # Initial 패킷의 전송을 기준 시각으로

                    initialTime_datetime = datetime.fromtimestamp(initialTime)

                    # if initialTime_datetime.hour > 12:
                    #     initialTime_datetime = initialTime_datetime.replace(
                    #         hour=initialTime_datetime.hour - 12,
                    #     )

                    # initialTime = initialTime_datetime.timestamp()

                    print(f"Initial time: {initialTime}")
                    print(f"as datetime: {initialTime_datetime}")
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
                        try:
                            spins = np.append(spins, int(spin))
                        except ValueError:
                            if spin == "True":
                                spins = np.append(spins, 1)
                            else:
                                spins = np.append(spins, 0)
                        prevSpin = spin
                        if (int(packet.number) % 1000) == 0:
                            print(f"{packet.number} packets processed")
        print(f"load time: {datetime.now() - loadStartTime}")
        spinFrame = pd.DataFrame({"time": times, "spin": spins})
        spinFrame.to_csv(f"{filename_prefix}_spin.csv", index=False)

    throughputFrame = pd.read_csv(f"{filename_prefix}.csv")
    with open(f"{filename_prefix}.log", encoding="utf8") as f:
        lines = f.readlines()
        initialLogTime = 0
        for line in lines:
            timeString = str(line.split("]")[2].replace("[", ""))
            # if "[S][RX][0] LH Ver:" in line and "Type:I" in line: # 감지가 안 돼.. 어째서지?
            if "Handshake start" in line:
                initialLogTime = datetime.strptime(
                    timeString, "%H:%M:%S.%f"
                )  # Initial 패킷의 전송을 기준 시각으로

                print(f"Initial Log time: {initialLogTime}")
                initialTime_datetime = datetime.fromtimestamp(initialTime)
                initialTime_datetime = initialTime_datetime.replace(
                    year=initialLogTime.year,
                    month=initialLogTime.month,
                    day=initialLogTime.day,
                )
                timeDelta = initialTime_datetime - initialLogTime
                print(f"Time delta: {timeDelta}")
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
        if prevTime != initialSpinTime:
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

    numLosses = len(lostFrame["loss"])
    numRack = len(lostFrame[lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_RACK])
    numFack = len(lostFrame[lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_FACK])
    numProbe = len(lostFrame[lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_PROBE])

    print(f"평균 throughput: {avgThroughput}Mbps")
    print(f"Lost 개수: {numLosses}개")
    print(f"Loss reason 0(QUIC_TRACE_PACKET_LOSS_RACK): {numRack}개")
    print(f"Loss reason 1(QUIC_TRACE_PACKET_LOSS_FACK): {numFack}개")
    print(f"Loss reason 2(QUIC_TRACE_PACKET_LOSS_PROBE): {numProbe}개")

    if bandwidth >= 0 and prevTime > 0:
        stats_file.write(
            f"{loss}, {bandwidth}, {delay}, {spinFrequency}, {avgThroughput}, {numLosses}, {numRack}, {numFack}, {numProbe} \n"
        )

    lostFrame.to_csv(f"{filename_prefix}_lost.csv", index=False)
    cwndFrame.to_csv(f"{filename_prefix}_cwnd.csv", index=False)
    wMaxFrame.to_csv(f"{filename_prefix}_wMax.csv", index=False)

    # cf1 = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest", tolerance=0.01)
    # cf2 = pd.merge_asof(lostFrame, spinFrame, on="time", direction="nearest", tolerance=0.01)
    # cf3 = pd.concat([cf1, cf2[cf2['loss'].isnull()]]).sort_index()
    # cf3 = pd.merge(spinFrame, lostFrame, on="time", how="outer", sort=True)

    # combinedFrame = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest")
    # combinedFrame = pd.merge_asof(combinedFrame, cwndFrame, on="time", direction="nearest")
    # combinedFrame.to_csv(f"{filename}_combined.csv", index=False)

    stats_file.close()
    return spinFrame, throughputFrame, lostFrame, cwndFrame, wMaxFrame


def main():
    parser = argparse.ArgumentParser(description="Show spin bit")
    parser.add_argument("file", metavar="file", type=str, nargs=1)
    parser.add_argument(
        "-c",
        "--csv",
        action="store_true",
        help="Additional csv handling for tshark captured files",
        default=False,
        required=False,
    )

    args = parser.parse_args()
    loadData(args)


if __name__ == "__main__":
    main()
