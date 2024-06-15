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

BANDWIDTH = 17

class QuicRunner:
    def __init__(self):
        self.server, self.client = self.runContainers()
    
    def run_command_in_container(self, container, command):
            exec_id = self.dockerClient.api.exec_create(container.id, command, stdout=True, stderr=True, stdin=False, tty=False)
            logs = self.dockerClient.api.exec_start(exec_id, stream=True)
            
            # 출력을 실시간으로 받아오기
            for line in logs:
                print(line.decode('utf-8').strip())

            # 실행 결과 받기
            exit_code = self.dockerClient.api.exec_inspect(exec_id)['ExitCode']
            return exit_code

    def runContainers(self):
        self.dockerClient = docker.from_env()

        ServerContainer = self.dockerClient.containers.get("quicserver")
        ClientContainer = self.dockerClient.containers.get("quicclient")

        ServerContainer.start()
        ClientContainer.start()

        self.serverIp = self.dockerClient.containers.get("quicserver").attrs['NetworkSettings']['IPAddress']
        print(self.serverIp)

        ServerContainer.exec_run(f"cd /root/network/quic/msquic")
        ClientContainer.exec_run(f"cd /root/network/quic/msquic")

        return ServerContainer, ClientContainer

    def runQuic(self, lossRate, delay):
            filename = f"l{lossRate}b{BANDWIDTH}d{delay}"
            self.run_command_in_container(self.server,f"tc qdisc add dev eth1 root netem loss {lossRate}% delay {delay}ms rate {BANDWIDTH}mbit")

            # 서버 컨테이너에 실행
            exec_id = self.dockerClient.api.exec_create(self.server.id, f"tcpdump -s 0 -i eth1 -w {filename}.pcap & ./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Release_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Basic.Light", stdin=True, tty=True)
            sock = self.dockerClient.api.exec_start(exec_id, socket=True)

            self.run_command_in_container(self.client,f"./artifacts/bin/linux/x64_Release_openssl/quicsample -client -unsecure -target:{self.serverIp}")

            # 클라이언트 실행 종료 시 엔터 키 전송
            sock._sock.send(b'\n')

            while True:
                self.server.reload()
                if self.server.status == 'exited':
                    print("Server has exited.")
                    break
            
            self.run_command_in_container(self.server,f"mv {filename}.pcap /msquic_logs")
            self.run_command_in_container(self.server,f"msquic_lttng0/quic.log /msquic_logs/{filename}.log")
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