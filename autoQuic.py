import subprocess
import sys
from shutil import copy
from shutil import rmtree
import numpy as np
import pandas as pd
import os
import platform
import argparse
import configparser
import docker
from time import sleep
import select
import multiprocessing
import threading
import csv
from datetime import datetime
import pyshark
import statistics

BANDWIDTH = 17

class QuicRunner:
    def __init__(self):
        self.server, self.client = self.runContainers()
     
    def loadData(self, filename):
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
        if filename not in ports:
            port = 4567
        else:
            port = ports[filename]

        try:
            spinFrame = pd.read_csv(f"{filename}_spin.csv")
        except FileNotFoundError:
            cap = None
            try:
                cap = pyshark.FileCapture(f"{filename}.pcapng")
            except FileNotFoundError:
                cap = pyshark.FileCapture(f"{filename}.pcap")
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
            spinFrame.to_csv(f"{filename}_spin.csv", index=False)

        throughputFrame = pd.read_csv(f"{filename}.csv")
        with open(f"{filename}.log") as f:
            lines = f.readlines()
            initialLogTime = 0
            for line in lines:
                timeString = str(line.split("]")[2].replace("[", ""))
                if "[S][RX][0] LH Ver:" in line and "Type:I" in line:
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

        print(f"평균 throughput: {avgThroughput}Mbps")
        print(f"Lost 개수: {len(lostFrame['loss'])}개")
        print(f"Loss reason 0: {len(lostFrame[lostFrame['loss'] == 0])}개")
        print(f"Loss reason 1: {len(lostFrame[lostFrame['loss'] == 1])}개")
        print(f"Loss reason 2: {len(lostFrame[lostFrame['loss'] == 2])}개")

        if BANDWIDTH >= 0 and prevTime > 0:
            with open("stats.csv", "a") as f:
                f.write(
                    f"{self.lossRate}, {BANDWIDTH}, {self.delay}, {spinFrequency}, {avgThroughput}, {sum(lossReasons)}\n"
                )

        lostFrame.to_csv(f"{filename}_lost.csv", index=False)
        cwndFrame.to_csv(f"{filename}_cwnd.csv", index=False)
        wMaxFrame.to_csv(f"{filename}_wMax.csv", index=False)

        # cf1 = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest", tolerance=0.01)
        # cf2 = pd.merge_asof(lostFrame, spinFrame, on="time", direction="nearest", tolerance=0.01)
        # cf3 = pd.concat([cf1, cf2[cf2['loss'].isnull()]]).sort_index()
        # cf3 = pd.merge(spinFrame, lostFrame, on="time", how="outer", sort=True)

        # combinedFrame = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest")
        # combinedFrame = pd.merge_asof(combinedFrame, cwndFrame, on="time", direction="nearest")
        # combinedFrame.to_csv(f"{filename}_combined.csv", index=False)

        return spinFrame, throughputFrame, lostFrame, cwndFrame, wMaxFrame


    
    def run_command_in_container(self, container, command, stream = True, stdin=False, tty=False, detach=False):
            # full_command = f"sh -c \'{command}\'"
            print(f"{container}에 명령 입력: {command}")
            exec_id = self.dockerClient.api.exec_create(container.id, command, stdout=True, stderr=True, stdin=stdin, tty=tty, workdir="/root/network/quic/msquic")
            if stream:
                logs = self.dockerClient.api.exec_start(exec_id, stream=stream, detach=detach)
                # 출력을 실시간으로 받아오기
                for line in logs:
                    print(line.decode('utf-8').strip())
                # 실행 결과 받기
                exit_code = self.dockerClient.api.exec_inspect(exec_id)['ExitCode']
                return exec_id, exit_code 
            else:
                if detach:
                    self.dockerClient.api.exec_start(exec_id, socket=True, detach=detach)
                    return exec_id
                else:
                    sock = self.dockerClient.api.exec_start(exec_id, socket=True, detach=detach)
                    return sock, exec_id

    def runContainers(self):
        self.dockerClient = docker.from_env()

        ServerContainer = self.dockerClient.containers.get("quicserver")
        ClientContainer = self.dockerClient.containers.get("quicclient")

        ServerContainer.start()
        ClientContainer.start()

        self.serverIp = self.dockerClient.containers.get("quicserver").attrs['NetworkSettings']['Networks']['msquic_quicnet']['IPAddress']
        print(self.serverIp)

        return ServerContainer, ClientContainer
    
    def getSocketOutput(self, sock):
        try:
            while True:
                r, w, e = select.select([sock._sock], [], [], 1)
                if sock._sock in r:
                    output = sock.read(1024)
                    if output:
                        try:
                            print(output.decode('utf-8').strip())
                        except UnicodeDecodeError:
                            print("UnicodeDecodeError 발생")
                            pass
                    else:
                        print("출력이 감지되지 않았습니다.")
                        sleep(5)
                        break
        except Exception as e:
            print(f"An error occurred: {e}")

    
    def send_signal_to_exec(self, container, exec_id, signal):
        # exec_inspect를 사용하여 exec 프로세스의 PID를 가져옴
        exec_info = self.dockerClient.api.exec_inspect(exec_id)
        pid = exec_info['Pid']
        
        # 컨테이너 내부의 프로세스에 신호를 보냄
        kill_command = f"kill -{signal} {pid}"
        self.dockerClient.api.exec_create(container.id, kill_command)

    def runQuic(self, lossRate, delay):
            self.lossRate = lossRate
            self.delay = delay

            filename = f"l{lossRate}b{BANDWIDTH}d{delay}"
            self.run_command_in_container(self.server,f"tc qdisc del dev eth1 root netem")
            self.run_command_in_container(self.server,f"tc qdisc add dev eth1 root netem loss {lossRate}% delay {delay}ms rate {BANDWIDTH}mbit")

            # 서버 컨테이너 실행
            # self.run_command_in_container(self.server,f"tcpdump -s 0 -i eth1 -w {filename}.pcap & ./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Release_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Basic.Light")

            # command = f"tcpdump -s 262144 -i eth1 -w {filename}.pcap & ./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Release_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Basic.Light"
            commands = [f"tshark -i eth1 -w {filename}.pcap", f"./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Release_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Basic.Light"]


            exec_id = self.run_command_in_container(self.server, commands[0], detach=True)
            sock, _ = self.run_command_in_container(self.server, commands[1], stream=False, stdin=True, tty=True)

            outputThread = threading.Thread(target=self.getSocketOutput, args=(sock,))
            outputThread.start()

            sleep(5)

            self.run_command_in_container(self.client,f"./artifacts/bin/linux/x64_Release_openssl/quicsample -client -unsecure -target:{self.serverIp}")

            # 클라이언트 실행 종료 시 서버에서 tcpdump 종료 & 서버에 엔터 키 전송
            self.send_signal_to_exec(self.server, exec_id[0], signal='INT')
            self.server.exec_run("echo ''", detach=False, tty=True)
            sock._sock.send(b'\n')
            print("엔터 키 전송 완료")

            outputThread.join()
            print("outputThread 종료")

            self.run_command_in_container(self.server,f"mv msquic_lttng0/quic.log ./{filename}.log")
            self.run_command_in_container(self.server,f"""sh -c \'tshark -r {filename}.pcap -q -z io,stat,0.1 \
| grep -P \"\\d+\\.?\\d*\\s+<>\\s+|Interval +\\|\" \
| tr -d \" \" | tr \"|\" \",\" | sed -E \"s/<>/,/; s/(^,|,$)//g; s/Interval/Start,Stop/g\" > {filename}.csv\'""")

            self.run_command_in_container(self.server,f"python handleData.py")

            self.run_command_in_container(self.server,f"mv {filename}.pcap /msquic_logs")
            self.run_command_in_container(self.server,f"mv {filename}.log /msquic_logs")
            self.run_command_in_container(self.server,f"mv {filename}_lost.csv /msquic_logs")
            self.run_command_in_container(self.server,f"mv {filename}_spin.csv /msquic_logs")
            self.run_command_in_container(self.server,f"mv {filename}_cwnd.csv /msquic_logs")
            self.run_command_in_container(self.server,f"mv {filename}_wMax.csv /msquic_logs")
            self.run_command_in_container(self.server,f"mv {filename}.csv /msquic_logs")
            self.run_command_in_container(self.server,f"rm -rf msquic_lttng0")

            self.run_command_in_container(self.server,f"tc qdisc del dev eth1 root")

def main():
    lastValues = []
    lossRates = range(0, 11, 1)
    # bitRatesinMbps = range(0, 100)
    delays = range(0, 200, 5)

    try:
        with open("lastValues.txt", "r") as f:
            lastValues = f.readlines()
            lossRates = range(int(lastValues[0]), 11, 1)
            delays = range(int(lastValues[1]), 200, 5)
    except FileNotFoundError:
        pass

    runner = QuicRunner()
    for lossRate in lossRates:
        for delay in delays:
            print("Running for loss rate: " + str(lossRate) + " and delay: " + str(delay))
            runner.runQuic(lossRate, delay)
            print("Done running for loss rate: " + str(lossRate) + " and delay: " + str(delay))
            lastValues = [lossRate, delay]
            with open("lastValues.txt", "w") as f:
                for value in lastValues:
                    f.write(str(value) + "\n")

if __name__ == '__main__':
    main()