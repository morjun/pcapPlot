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

TIME_CUT_OFF = 20

class DataLoader:
    def __init__(self, args):
        self.args = args
        self.spin_supported = True
        self.times = np.array([], dtype=float)
        self.lostTimes = np.array([], dtype=float)
        self.cwndTimes = np.array([], dtype=float)
        self.wMaxTimes = np.array([], dtype=float)

        self.lossReasons = np.array([], dtype=int)
        self.spins = np.array([], dtype=int)
        self.rtts = np.array([], dtype=float)
        self.cwnds = np.array([], dtype=int)
        self.wMaxes = np.array([], dtype=int)

        self.throughputFrame = None
        self.spinFrame = None
        self.lostFrame = None
        self.cwndFrame = None
        self.wMaxFrame = None

        self.initialTime = 0
        self.initialSpinTime = 0
        self.prevSpin = -1  # 처음 Short Header Packet 감지용
        self.prevTime = 0
        self.prevTimeBefore20s = 0
        self.numSpin = -1  # 처음 Short Header Packet의 spin bit 0이 발견되는 순간 spin 횟수 0

        self.full_path = None
        self.parametric_path = None
        self.filename_prefix = None
        self.stats_path = None
        self.stats_20s_path = None

        self.time_datetime = None

        self.loss = 2.7
        self.bandwidth = 17
        self.delay = 33

        self.index = 1
        self.port = 0 

        self.spinFrame = None
        self.pathology = False
    
    def parse_path(self):
        self.full_path = self.args.file[0] # 입력: .../l0b0d0_t0
        self.index = self.args.number # 입력: n

        self.full_path = os.path.relpath(self.full_path)
        self.full_abs_path = os.path.abspath(self.full_path)
        splitted_path = os.path.split(self.full_path) # ('...', 'l0b0d0_t0')
        splitted_abs_path = os.path.split(self.full_abs_path) # ('...', 'l0b0d0_t0')

        self.stats_path = os.path.join(splitted_abs_path[0], "stats.csv") # 상위 디렉토리에 stats.csv를 저장하기 위해 경로 변경 전에 현재 경로를 저장
        self.stats_20s_path = os.path.join(splitted_abs_path[0], "stats_20s.csv")

        arg_path_parts = splitted_path[1].split("_") # ['l0b0d0', 't0']
        self.parametric_path = arg_path_parts[0] # l0b0d0

        time = 0
        if len(arg_path_parts) > 1:
            time = arg_path_parts[1] # t0
            time = time[1:] # 0

        self.time_datetime = datetime.fromtimestamp(int(time))
        self.filename_prefix = self.parametric_path # 초기화

        if self.index > 1:
            self.filename_prefix = f"{self.parametric_path}_{self.index}" # l0b0d0_n

        print(f"filename prefix: {self.filename_prefix}")

        filename_reg = r"l(\d+(.\d+)?)b(\d+)d(\d+)"
        filename_reg = re.compile(filename_reg)
        filename_match = filename_reg.match(self.filename_prefix)

        self.loss = float(filename_match.group(1))
        self.bandwidth = int(filename_match.group(3))
        self.delay = int(filename_match.group(4))

        print(f"loss: {self.loss}, bandwidth: {self.bandwidth}, delay: {self.delay}")

        # self.full_path = os.path.join(splitted_path[0], filename_prefix.split("_")[0])

        print(f"full path: {self.full_path}")
        os.chdir(self.full_path)
    
    def thorughput_csv_convert(self):
        tempFrame = pd.read_csv(f"{self.filename_prefix}.csv")
        tempFrame = tempFrame[["Start", "Bytes"]]
        tempFrame.rename(
            columns={"Start": "Interval start", "Bytes": "All Packets"}, inplace=True
        )
        tempFrame.to_csv(f"{self.filename_prefix}.csv", index=False)
    
    def load_throughput(self):
        self.throughputFrame = pd.read_csv(f"{self.filename_prefix}.csv")
        # 마지막에 0바이트 구간 컷
        zero_count = 0
        initial_zero_index = None
        for row in self.throughputFrame.iterrows():
            if initial_zero_index is None:
                initial_zero_index = row[0]
            if row[1]["All Packets"] == 0:
                zero_count += 1
            else:
                zero_count = 0
                initial_zero_index = None
            if zero_count > 50 and row[0] > 100:
                self.throughputFrame = self.throughputFrame.drop(self.throughputFrame.index[initial_zero_index:])
                break

        print(f"throughput frame: {self.throughputFrame}")
        self.throughputFrame["All Packets"] = [
            # (x * 8 / 1000000) / self.throughputFrame["Interval start"][1]
            (x * 8) / self.throughputFrame["Interval start"][1]
            for x in self.throughputFrame["All Packets"]
        ]  # Bp100ms -> Mbps
    
    def load_log(self):
        return

    def calc_spinFrequency(self):
        # --- Configuration ---
        window_size = 2.5  # seconds
        step_size = 0.1    # seconds
        input_filename = f"{self.filename_prefix}_spin.csv"
        output_filename = f"{self.filename_prefix}_spinFreq.csv"
        # ---

        try:
            # Load the data
            df = self.spinFrame.copy() 

            # Validate columns
            if 'time' not in df.columns or 'spin' not in df.columns:
                raise ValueError("CSV file must contain 'time' and 'spin' columns.")

            # Sort by time (important for diff and windowing)
            df = df.sort_values(by='time').reset_index(drop=True)

            # Calculate spin changes (1 if change occurred, 0 otherwise)
            df['spin_diff'] = df['spin'].diff().fillna(0)
            df['spin_change'] = df['spin_diff'].abs().apply(lambda x: 1 if x != 0 else 0)

            # --- Sliding Window Calculation ---
            results = []
            min_time = df['time'].min()
            max_time = df['time'].max()

            # Find the indices of spin changes for efficient lookup
            change_indices = df.index[df['spin_change'] == 1].tolist()
            # Get the actual times of changes as a NumPy array for faster comparison
            change_times = df.loc[change_indices, 'time'].values

            # Iterate through window start times
            # Start from min_time, end when the window start + window_size exceeds max_time
            current_window_start_time = min_time
            # Adjust loop condition to ensure windows covering the last data point are potentially included
            # The window center will be plotted, so we need windows whose centers are meaningful
            while current_window_start_time <= max_time: # Iterate as long as the window can start within the data range

                window_end_time = current_window_start_time + window_size

                # Count changes within the current window [start, end)
                # Efficiently count changes using pre-calculated change times
                # Find changes that are >= start_time and < end_time
                count_in_window = np.sum((change_times >= current_window_start_time) & (change_times < window_end_time))

                # Calculate rate in Hz (changes per second)
                rate_hz = count_in_window / window_size

                # Calculate the center time of the window
                window_center_time = current_window_start_time + window_size / 2.0

                # Store result
                results.append({'time_center': window_center_time, 'change_rate_hz': rate_hz})

                # Move the window start time forward
                current_window_start_time += step_size
                # Handle potential floating point inaccuracies by rounding slightly if needed
                current_window_start_time = round(current_window_start_time, 6) # Adjust precision as needed

            # Convert results to DataFrame
            output_df = pd.DataFrame(results)

            # Remove potential duplicate times if any (unlikely with rounding but safe)
            output_df = output_df.drop_duplicates(subset=['time_center'])

            # Save the results
            if not output_df.empty:
                output_df.to_csv(output_filename, sep=',', index=False, header=False, float_format='%.6f')
                print(f"Sliding window analysis complete. Results saved to '{output_filename}'.")
                print("\nData preview:")
                print(output_df.head())
            else:
                print("No results generated. Check data range and window/step sizes.")


        except FileNotFoundError:
            print(f"Error: The file '{input_filename}' was not found.")
        except ValueError as ve:
            print(f"Data Error: {ve}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
    
    def load_spin(self):
        if self.args.reprocess:
            try:
                os.remove(f"{self.filename_prefix}_spin.csv")
            except FileNotFoundError:
                pass
        try:
            self.spinFrame = pd.read_csv(f"{self.filename_prefix}_spin.csv")
            print(f"Loaded {self.filename_prefix}_spin.csv")
        except FileNotFoundError:
            print(f"Loading {self.filename_prefix}.pcap(ng)")
            cap = None
            try:
                cap = pyshark.FileCapture(f"{self.filename_prefix}.pcapng")
            except FileNotFoundError:
                cap = pyshark.FileCapture(f"{self.filename_prefix}.pcap")
            print(f"Loaded {self.filename_prefix}.pcap(ng)")
            loadStartTime = datetime.now()
            for packet in cap:
                # print(f"processing packet {packet.number}")
                if hasattr(packet, "quic"):
                    if self.initialTime == 0:  # int
                        self.initialTime = (
                            packet.sniff_time.timestamp()
                        )  # Initial 패킷의 전송을 기준 시각으로

                        initialTime_datetime = datetime.fromtimestamp(self.initialTime)

                        # if initialTime_datetime.hour > 12:
                        #     initialTime_datetime = initialTime_datetime.replace(
                        #         hour=initialTime_datetime.hour - 12,
                        #     )

                        # initialTime = initialTime_datetime.timestamp()

                        print(f"Initial time: {self.initialTime}")
                        print(f"as datetime: {initialTime_datetime}")
                    if hasattr(packet.quic, "spin_bit"):
                        # print("It has spin bit")
                        if packet.udp.srcport == str(self.port):  # 서버가 전송한 패킷만
                            time = packet.sniff_time.timestamp() - self.initialTime
                            spin = packet.quic.spin_bit
                            # print(f"spin: {spin}")
                            if self.prevSpin != spin:
                                self.numSpin += 1
                                if self.prevTime != 0:
                                    rtt = time - self.prevTime
                                    self.rtts = np.append(self.rtts, float(rtt))  # spin -> rtt 계산
                                else:
                                    self.initialSpinTime = time
                                self.prevTime = time
                                if self.prevTime < TIME_CUT_OFF:
                                    self.prevTimeBefore20s = self.prevTime
                            self.times = np.append(self.times, float(time))
                            try:
                                self.spins = np.append(self.spins, int(spin))
                            except ValueError:
                                if spin == "True":
                                    self.spins = np.append(self.spins, 1)
                                else:
                                    self.spins = np.append(self.spins, 0)
                            self.prevSpin = spin

                            if (int(packet.number) % 1000) == 0:
                                print(f"{packet.number} packets processed")
                        # else:
                        #     print("It has spin bit but not from server")
            print(f"load time: {datetime.now() - loadStartTime}")
            self.spinFrame = pd.DataFrame({"time": self.times, "spin": self.spins})
            self.spinFrame.to_csv(f"{self.filename_prefix}_spin.csv", index=False)
        finally:
            self.calc_spinFrequency()

    def get_spin_stats(self):
        spinFrequency = 0
        spinFrequency_before_20s = 0
        if self.prevTime > 0: # spin handling
            print(self.prevTime, self.initialSpinTime)
            if self.prevTime != self.initialSpinTime:
                spinFrequency = self.numSpin / (2 * (self.prevTime - self.initialSpinTime))
                spinFrequency_before_20s = self.numSpin / (2 * (self.prevTimeBefore20s - self.initialSpinTime))
            else:
                print("DIVISION BY ZERO, perhaps spin bit is not supported by the library?")
                exit(1)
            print(f"첫 short packet time: {self.initialSpinTime}초")
            print(f"마지막 spin time: {self.prevTime}초")

            print(f"평균 spin frequency: {spinFrequency}Hz")
            print(f"20초 이전 평균 spin frequency: {spinFrequency_before_20s}Hz")
        if self.numSpin >= 0:
            print(f"총 spin 수 : {self.numSpin}")
            print(f"평균 rtt(spin bit 기준): {statistics.mean(self.rtts)}초")
        
        return spinFrequency, spinFrequency_before_20s
    
    def make_csv(self):
        spinFrequency = 0
        spinFrequency_before_20s = 0
        self.lostFrame = pd.DataFrame({"time": self.lostTimes, "loss": self.lossReasons})
        self.cwndFrame = pd.DataFrame({"time": self.cwndTimes, "cwnd": self.cwnds})
        self.wMaxFrame = pd.DataFrame({"time": self.wMaxTimes, "wMax": self.wMaxes})
        avgThroughput = statistics.mean(self.throughputFrame["All Packets"]) / 1000000
        avgThroughput_before_20s = statistics.mean(self.throughputFrame[self.throughputFrame["Interval start"] < TIME_CUT_OFF]["All Packets"]) / 1000000

        if self.spin_supported:
            (spinFrequency, spinFrequency_before_20s) = self.get_spin_stats()

        numLosses = len(self.lostFrame["loss"])

        numRack = len(self.lostFrame[self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_RACK])
        numFack = len(self.lostFrame[self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_FACK])
        numProbe = len(self.lostFrame[self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_PROBE])

        numRack_before_20s = len(self.lostFrame[(self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_RACK) & (self.lostFrame["time"] < TIME_CUT_OFF)])
        numFack_before_20s = len(self.lostFrame[(self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_FACK) & (self.lostFrame["time"] < TIME_CUT_OFF)])
        numProbe_before_20s = len(self.lostFrame[(self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_PROBE) & (self.lostFrame["time"] < TIME_CUT_OFF)])

        print(f"평균 throughput: {avgThroughput}Mbps")
        print(f"Lost 개수: {numLosses}개")
        print(f"Loss reason 0(QUIC_TRACE_PACKET_LOSS_RACK): {numRack}개")
        print(f"Loss reason 1(QUIC_TRACE_PACKET_LOSS_FACK): {numFack}개")
        print(f"Loss reason 2(QUIC_TRACE_PACKET_LOSS_PROBE): {numProbe}개")

        # if avgThroughput < 5:
        fackRatio = 0
        if numRack > 0:
            fackRatio = numFack / numRack
        elif numFack > 0: 
            fackRatio = 1
        else:
            fackRatio = 0
        if fackRatio < 5 or avgThroughput < 5:
            self.pathology = True

        print(f"Pathology: {self.pathology}")

        with open(self.stats_path, "a", encoding="utf8") as stats_file:
            # print(f"bandwidth: {self.bandwidth} prevTime: {self.prevTime}")
            # if self.bandwidth >= 0 and self.prevTime > 0: # prevTime 0인 경우가 있음
            print("writing to stats.csv")
            if self.spin_supported:
                stats_file.write(
                    f"{self.time_datetime}, {self.index}, {self.loss}, {self.bandwidth}, {self.delay}, {spinFrequency}, {avgThroughput}, {numLosses}, {numRack}, {numFack}, {numProbe}, {self.pathology}\n"
                )
            else:
                stats_file.write(
                    f"{self.time_datetime}, {self.index}, {self.loss}, {self.bandwidth}, {self.delay}, {avgThroughput}, {numLosses}, {numRack}, {numFack}, {numProbe}, {self.pathology}\n"
                )
            print(f"written to stats.csv: {self.stats_path}")
        
        with open(self.stats_20s_path, "a", encoding="utf8") as stats_20s_file:
            # if self.bandwidth >= 0 and self.prevTime > 0:
            print("writing to stats_20s.csv")
            if self.spin_supported:
                stats_20s_file.write(
                    f"{self.time_datetime}, {self.index}, {self.loss}, {self.bandwidth}, {self.delay}, {spinFrequency_before_20s}, {avgThroughput_before_20s}, {numRack_before_20s}, {numFack_before_20s}, {numProbe_before_20s}, {self.pathology}\n"
                )
            else:
                stats_20s_file.write(
                    f"{self.time_datetime}, {self.index}, {self.loss}, {self.bandwidth}, {self.delay}, {avgThroughput_before_20s}, {numRack_before_20s}, {numFack_before_20s}, {numProbe_before_20s}, {self.pathology}\n"
                )
            print("written to stats_20s.csv")

        self.lostFrame.to_csv(f"{self.filename_prefix}_lost.csv", index=False)
        self.cwndFrame.to_csv(f"{self.filename_prefix}_cwnd.csv", index=False)
        self.wMaxFrame.to_csv(f"{self.filename_prefix}_wMax.csv", index=False)

        # cf1 = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest", tolerance=0.01)
        # cf2 = pd.merge_asof(lostFrame, spinFrame, on="time", direction="nearest", tolerance=0.01)
        # cf3 = pd.concat([cf1, cf2[cf2['loss'].isnull()]]).sort_index()
        # cf3 = pd.merge(spinFrame, lostFrame, on="time", how="outer", sort=True)

        # combinedFrame = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest")
        # combinedFrame = pd.merge_asof(combinedFrame, cwndFrame, on="time", direction="nearest")
        # combinedFrame.to_csv(f"{filename}_combined.csv", index=False)
    
    def load_csv(self):
        try:
            self.lostFrame = pd.read_csv(f"{self.filename_prefix}_lost.csv")
            self.cwndFrame = pd.read_csv(f"{self.filename_prefix}_cwnd.csv")
            self.wMaxFrame = pd.read_csv(f"{self.filename_prefix}_wMax.csv")
            return True
        except FileNotFoundError as e:
            print(f"File not found: {e}. Continue to make new csv files.")
            return False
    
    def load_data(self):
        self.parse_path()
        if self.args.csv:
            self.thorughput_csv_convert()
        self.load_throughput()
        self.load_log()
        if self.spin_supported:
            self.load_spin()
        print("Trying to load pre-saved csv files")
        if not self.load_csv():
            self.make_csv()
        return self.spinFrame, self.throughputFrame, self.lostFrame, self.cwndFrame, self.wMaxFrame

class msquicLoader(DataLoader):
    def __init__(self, args):
        super().__init__(args)
        self.file_ports = {"interop": 4433, "samplequic": 4567}
        self.port = 4567
    
    def load_log(self):
        try:
            with open(f"{self.filename_prefix}.log", encoding="utf8") as f:
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
                        initialTime_datetime = datetime.fromtimestamp(self.initialTime)
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
                        logTimeStamp = datetime.strptime(timeString, "%H:%M:%S.%f")
                        logTime = (
                            logTimeStamp - initialLogTime
                        ).total_seconds()

                        if logTimeStamp < initialLogTime:
                            # add 12 hours
                            logTime += 43200

                        if "Lost: " in line and "[conn]" in line:
                            lossReason = int(line.split("Lost: ")[1].split(" ")[0])
                            self.lostTimes = np.append(self.lostTimes, float(logTime))
                            self.lossReasons = np.append(self.lossReasons, int(lossReason))
                        elif "OUT: " in line and "CWnd=" in line:
                            cwnd = int(line.split("CWnd=")[1].split(" ")[0])
                            self.cwnds = np.append(self.cwnds, int(cwnd))
                            self.cwndTimes = np.append(self.cwndTimes, float(logTime))
                        elif "WindowMax" in line:
                            wMax = int(line.split("WindowMax=")[1].split(" ")[0])
                            self.wMaxes = np.append(self.wMaxes, int(wMax))
                            self.wMaxTimes = np.append(self.wMaxTimes, float(logTime))
        except FileNotFoundError:
            print(f"File {self.filename_prefix}.log not found.")

        def load_spin(self):
            if self.filename_prefix in self.file_ports:
                self.port = self.file_ports[self.filename_prefix]
            super().load_spin()

class quicGoLoader(DataLoader):
    def __init__(self, args):
        super().__init__(args)
        self.port = 6121
        self.spin_supported = False

    def load_log(self):
        with open(f"{self.filename_prefix}.log", encoding="utf8") as f:
            lines = f.readlines()
            initialLogTime = 0
            for line in lines:
                timeString = line.split(" ")[:2]
                timeString = " ".join(timeString)
                # timeString = re.search(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})", line).group(1)

                if "server 	Long Header{Type: Handshake" in line:
                    initialLogTime = datetime.strptime(
                        timeString, "%Y/%m/%d %H:%M:%S.%f"
                    )  # Initial 패킷의 전송을 기준 시각으로

                    print(f"Initial Log time: {initialLogTime}")

                else:
                    if initialLogTime == 0:
                        continue
                    try:
                        logTime = (
                            datetime.strptime(timeString, "%Y/%m/%d %H:%M:%S.%f") - initialLogTime
                        ).total_seconds()
                    except ValueError: # 막줄에 2025/02/ 이것만 찍히는 경우가 있음 왜인지 모름
                        print(f"Error: {line}")
                        continue
                    if "lost packet" in line:
                        self.lostTimes = np.append(self.lostTimes, float(logTime))
                        if "time threshold" in line:
                            self.lossReasons = np.append(self.lossReasons, QUIC_TRACE_PACKET_LOSS_RACK)
                        elif "reordering threshold" in line:
                            self.lossReasons = np.append(self.lossReasons, QUIC_TRACE_PACKET_LOSS_FACK)
                        else:
                            self.lossReasons = np.append(self.lossReasons, QUIC_TRACE_PACKET_LOSS_PROBE)
                    elif "Congestion limited: " in line and "window " in line:
                        cwnd = int(line.split("window ")[1].split(" ")[0])
                        self.cwnds = np.append(self.cwnds, int(cwnd))
                        self.cwndTimes = np.append(self.cwndTimes, float(logTime))
                    elif "WindowMax" in line:
                        wMax = int(line.split("WindowMax=")[1].split(" ")[0])
                        self.wMaxes = np.append(self.wMaxes, int(wMax))
                        self.wMaxTimes = np.append(self.wMaxTimes, float(logTime))

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

    parser.add_argument(
        "-n",
        "--number",
        type=int,
        default=1,
        help="n-th test in a single epoch",
        required=False,
    )

    parser.add_argument(
        "-t",
        "--type",
        type=str,
        default="msquic",
        help="Type of the server",
        required=False,
    )

    parser.add_argument(
        "-r",
        "--reprocess",
        action="store_true",
        help="Reprocess the data",
        default=False,
    )

    args = parser.parse_args()

    if args.type == "msquic":
        loader = msquicLoader(args)
        loader.load_data()
    elif args.type == "quic-go":
        loader = quicGoLoader(args)
        loader.load_data()


if __name__ == "__main__":
    main()
