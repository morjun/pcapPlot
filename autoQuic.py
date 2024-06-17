import subprocess
import sys
from shutil import copy
from shutil import rmtree
from distutils.dir_util import copy_tree
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
import showSpin

BANDWIDTH = 17

class QuicRunner:
    def __init__(self):
        self.server, self.client = self.runContainers()
    
    def run_command_in_container(self, container, command, stream = True, stdin=False, tty=False, detach=False):
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
                    if not output:
                        break
                    print(output.decode('utf-8').strip())
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
            filename = f"l{lossRate}b{BANDWIDTH}d{delay}"
            self.run_command_in_container(self.server,f"tc qdisc del dev eth1 root netem")
            self.run_command_in_container(self.server,f"tc qdisc add dev eth1 root netem loss {lossRate}% delay {delay}ms rate {BANDWIDTH}mbit")

            # 서버 컨테이너 실행
            # self.run_command_in_container(self.server,f"tcpdump -s 0 -i eth1 -w {filename}.pcap & ./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Release_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Basic.Light")

            # command = f"tcpdump -s 262144 -i eth1 -w {filename}.pcap & ./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Release_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Basic.Light"
            commands = [f"tcpdump -s 0 -i eth1 -w {filename}.pcap", f"./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Release_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Basic.Light"]


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

            # Throughput .csv파일 뽑아내기
            NotImplemented
            showSpin.loadData()

            self.run_command_in_container(self.server,f"mv {filename}.pcap /msquic_logs")
            self.run_command_in_container(self.server,f"mv {filename}.log /msquic_logs")
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