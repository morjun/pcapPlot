import subprocess
import shlex
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
import signal
from time import sleep
import select
import multiprocessing
import threading
import csv
from datetime import datetime
import pyshark
import statistics

MSQUIC_LOG_PATH = "/msquic_logs"
SSLKEYLOGFILE = "/root/sslkey.log"

class QuicRunner:
    def __init__(self, args):
        self.args = args
        self.server, self.client = self.runContainers()

    def send_signal_to_exec(self, container, exec_id, signal):
        # exec_inspect를 사용하여 exec 프로세스의 PID를 가져옴
        exec_info = self.dockerClient.api.exec_inspect(exec_id)

        # 주의!!!!!!!!!!!!! 호스트 네임스페이스의 PID임
        pid = exec_info["Pid"]
        print(f"pid: {pid}")

        # 컨테이너 내부의 프로세스에 신호를 보냄

        if os.name == "nt":
            # Windows
            kill_command = f"kill -{signal} {pid}"
            exec_id = self.dockerClient.api.exec_create(container.id, kill_command)["Id"]
            self.dockerClient.api.exec_start(exec_id)
            # os.system(f"taskkill /pid {pid} /f")

        elif os.name == "posix":
            # Linux
            # 도커 내부에서 실행해봤자, 의미 없음
            os.kill(pid, signal)

        print(f"Signal {signal} sent to PID {pid}")

    def runQuic(self, lossRate, delay):
        self.lossRate = lossRate
        self.delay = delay

        filename = f"l{lossRate}b{self.args.bandwidth}d{delay}"
        filename_ext = filename
        if self.number > 0:
             filename_ext += f"_{self.number + 1}"

        self.run_command_in_container(
            self.server, "rm -rf msquic_lttng*", wildcard=True
        )
        self.run_command_in_container(self.server, "rm l*b*d*.pcap", wildcard=True)
        self.run_command_in_container(self.server, "rm l*b*d*.log", wildcard=True)
        self.run_command_in_container(self.server, "rm l*b*d*_lost.csv", wildcard=True)
        self.run_command_in_container(self.server, "rm l*b*d*_spin.csv", wildcard=True)
        self.run_command_in_container(self.server, "rm l*b*d*_cwnd.csv", wildcard=True)
        self.run_command_in_container(self.server, "rm l*b*d*_wMax.csv", wildcard=True)
        self.run_command_in_container(self.server, "rm l*b*d*.csv", wildcard=True)
        self.run_command_in_container(self.server, "rm -rf l*b*d*/", wildcard=True)

        self.run_command_in_container(self.server, "tc qdisc del dev eth1 root netem")
        if self.args.bandwidth > 0:
            self.run_command_in_container(
                self.server,
                f"tc qdisc add dev eth1 root netem loss {lossRate}% delay {delay}ms rate {self.args.bandwidth}mbit",
            )
        else:
            self.run_command_in_container(
                self.server,
                f"tc qdisc add dev eth1 root netem loss {lossRate}% delay {delay}ms",
            )

        # self.run_command_in_container(self.server, "export SSLKEYLOGFILE=/root/sslkey.log") # 해당 쉘 세션에만 적용됨

        # 서버 컨테이너 실행
        # self.run_command_in_container(self.server,f"tcpdump -s 0 -i eth1 -w {filename}.pcap & ./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Debug_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Basic.Light")

        # command = f"tcpdump -s 262144 -i eth1 -w {filename}.pcap & ./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Debug_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Full.Verbose"
        commands = [
            f"tshark -i eth1 -w {filename_ext}.pcap -o tls.keylog_file:{SSLKEYLOGFILE}",
            "./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Debug_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Full.Verbose",
        ]

        exec_id = self.run_command_in_container(self.server, commands[0], detach=True)
        print(f"exec_id: {exec_id[0]}")
        sock, _ = self.run_command_in_container(
            self.server, commands[1], stream=False, stdin=True, tty=True
        )

        outputThread = threading.Thread(target=self.getSocketOutput, args=(sock,))
        outputThread.start()

        sleep(5)

        self.run_command_in_container(
            self.client,
            f"./artifacts/bin/linux/x64_Debug_openssl/quicsample -client -unsecure -target:{self.serverIp}",
        )

        # 클라이언트 실행 종료 시 서버에서 tshark 종료 & 서버에 엔터 키 전송

        self.send_signal_to_exec(self.server, exec_id[0], signal=signal.SIGINT)
        # 여기서 실행된 tshark가 종료되지 않음 -> 메모리 누수, 추후 수정할 것

        self.server.exec_run("echo ''", detach=False, tty=True)
        sock._sock.send(b"\n")
        print("엔터 키 전송 완료")

        outputThread.join()
        print("outputThread 종료")

        self.run_command_in_container(
            self.server, f"mv msquic_lttng0/quic.log ./{filename_ext}.log"
        )
        # log 파일이 정상적으로 옮겨지는 것까지는 확인 완료
        self.run_command_in_container(
            self.server,
            f"""sh -c \'tshark -r {filename_ext}.pcap -q -z io,stat,0.1 \
| grep -P \"\\d+\\.?\\d*\\s+<>\\s+|Interval +\\|\" \
| tr -d \" \" | tr \"|\" \",\" | sed -E \"s/<>/,/; s/(^,|,$)//g; s/Interval/Start,Stop/g\" > {filename_ext}.csv\'""",
        )

        self.run_command_in_container(self.server, f"mkdir {filename}")
        self.run_command_in_container(self.server, f"mv -f {filename_ext}.* {filename}/", wildcard=True)

        self.run_command_in_container(
            self.server,
            f"python loadSpinData.py -c ./{filename_ext}",
        )

        # self.run_command_in_container(self.server, f"rm -rf {MSQUIC_LOG_PATH}/{filename}")
        self.run_command_in_container(self.server, f"cp -rf {filename} {MSQUIC_LOG_PATH}/")
        self.run_command_in_container(self.server, f"rm -rf {filename}")
        self.run_command_in_container(self.server, "rm -rf msquic_lttng0")

        self.run_command_in_container(self.server, "tc qdisc del dev eth1 root")
        self.run_command_in_container(self.client, f"cp {SSLKEYLOGFILE} {MSQUIC_LOG_PATH}/")


def main():

    parser = argparse.ArgumentParser(description="Run Quic")

    parser.add_argument(
        "-l",
        "--loss",
        type=float,
        default=-1.0,
        help="Loss rate in percentage",
        required=False,
    )
    parser.add_argument(
        "-b",
        "--bandwidth",
        type=int,
        default=17,
        help="Bandwidth in Mbps",
        required=False,
    )
    parser.add_argument(
        "-d", "--delay", type=int, default=-1, help="Delay in ms", required=False
    )

    parser.add_argument(
        "-i", "--instance", type=int, default=1, help="QUIC Server & Client pair instance number", required=False
    )

    parser.add_argument(
        "-n",
        "--number",
        type=int,
        default=1,
        help="Number of times to run the test",
        required=False,
    )

    args = parser.parse_args()

    lastValues = []
    lossRates = []
    delays = []
    if args.loss >= 0:
        lossRates = [args.loss]
    else:
        lossRates = range(0, 11, 1)
    # bitRatesinMbps = range(0, 100)
    if args.delay >= 0:
        delays = [args.delay]
    else:
        delays = range(0, 200, 5)

    if args.loss < 0 and args.delay < 0:
        try:
            with open("lastValues.txt", "r", encoding="utf-8") as f:
                lastValues = f.readlines()
                lossRates = range(int(lastValues[0]), 11, 1)
                delays = range(int(lastValues[1]), 200, 5)
        except FileNotFoundError:
            pass

    runner = QuicRunner(args)
    for i in range(args.number):
        print(f"Running test number {i+1}")
        runner.number = i
        for lossRate in lossRates:
            for delay in delays:
                print(
                    "Running for loss rate: "
                    + str(lossRate)
                    + " and delay: "
                    + str(delay)
                )
                runner.runQuic(lossRate, delay)
                print(
                    "Done running for loss rate: "
                    + str(lossRate)
                    + " and delay: "
                    + str(delay)
                )
                if args.loss < 0 and args.delay < 0:
                    lastValues = [lossRate, delay]
                    with open("lastValues.txt", "w", encoding="utf-8") as f:
                        for value in lastValues:
                            f.write(str(value) + "\n")
            if args.loss < 0 and args.delay < 0:
                delays = range(0, 200, 5)  # 한바퀴 돌고 리셋


if __name__ == "__main__":
    main()
