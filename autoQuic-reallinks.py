import signal
import subprocess
from time import sleep
import threading
import shlex
import os
import argparse
import glob
import select
from datetime import datetime
from pathlib import Path

HOME_DIR = Path.home() # root 계정이면 /root임 주의
NETWORK_PATH = f"{HOME_DIR}/network"
MSQUIC_LOG_PATH = f"{NETWORK_PATH}/msquic_logs"
MSQUIC_PATH = f"{NETWORK_PATH}/quic/msquic"
SSLKEYLOGFILE = f"{NETWORK_PATH}/sslkey.log"

class QuicRunner:
    def __init__(self, args):
        self.args = args
        self.msquic_path = args.path
        self.script_path = os.path.dirname(os.path.abspath(__file__))
        self.interface = args.interface
        if args.gilbert_elliot:
            self.gilbert_p = args.gilbert_p
            self.gilbert_r = args.gilbert_r
            self.gilbert_h = args.gilbert_h
            self.gilbert_k = args.gilbert_k
        self.bandwidth = args.bandwidth
        self.isServer = args.server
        self.clientInitiated = {}
        self.current_time_unix = int(datetime.now().timestamp())
        if not self.isServer:
            self.serverIp = args.target
        self.number = 0

    def send_signal_to_process(self, process, signal=signal.SIGINT):
        pid = process.pid

        if os.name == "nt":
            # Windows
            kill_command = f"kill -{signal} {pid}"
            os.system(f"taskkill /pid {pid} /f")

        elif os.name == "posix":
            # Linux
            # 도커 내부에서 실행해봤자, 의미 없음
            os.kill(pid, signal)

        print(f"Signal {signal} sent to PID {pid}")
    
    def read_output(self, process, number = 0, timeout = 30, isServer = True):
        connectionEstablished = False
        ready = None

        if isServer:
            while True:
                if connectionEstablished:
                    ready, _, _ = select.select([process.stdout], [], [], timeout)
                else:
                    ready, _, _ = select.select([process.stdout], [], [],) # Infinitely wait until the client initiates
                if ready:
                    line = process.stdout.readline()
                    print(line, end='')
                    if "All done" in line:
                        break
                    elif "Sent" in line or "sent" in line:
                        connectionEstablished = True
                else:
                    print("Timeout: No output within the specified time.")
                    break
        else:
            while True:
                ready, _, _ = select.select([process.stdout], [], [], timeout)
                if ready:
                    line = process.stdout.readline()
                    print(line, end='')
                    if "All done" in line:
                        break
                    elif "Data received" in line:
                        self.clientInitiated[number] = True
                else:
                    print("Timeout: No output within the specified time.")
                    break

    def read_output_with_communicate(self, process, timeout=30):
        try:
            output, _ = process.communicate(timeout=timeout)
            print(output)
        except subprocess.TimeoutExpired:
            print("Timeout: Process took too long.")
            # process.terminate()  # Optional: terminate the process

    def run_command(
        self, command, cwd=None, shell=False, detach=False, input=False
    ):

        if cwd is None:
            cwd = self.msquic_path

        print(f"명령 입력: {command}")
        os.chdir(cwd)
        args = shlex.split(command)
        # 각 인자에 glob.glob 적용
        expanded_args = []
        for arg in args:
            expanded = glob.glob(arg)  # glob 패턴 매칭
            if expanded:  # 매칭된 결과가 있으면 확장
                expanded_args.extend(expanded)
            else:  # 매칭 결과가 없으면 원래 값을 추가
                expanded_args.append(arg)
        args = expanded_args

        if detach:
            process = None
            if input:
                process = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    # stderr=subprocess.PIPE,
                    shell=shell,
                    cwd=cwd,
                    text=True,
                )
            else:
                process = subprocess.Popen(
                    args,
                    # stdout=subprocess.PIPE,
                    # stderr=subprocess.PIPE,
                    shell=shell,
                    cwd=cwd,
                    text=True,
                )
            return process
        else:
            return subprocess.run(
                args,
                # stdout=subprocess.PIPE,
                # stderr=subprocess.PIPE,
                shell=shell,
                cwd=cwd,
            )

    def runQuic(self, lossRate, delay):
        isServer = self.isServer
        bandwidth = self.bandwidth

        filename = f"l{lossRate}b{bandwidth}d{delay}"
        foldername = f"{filename}_t{self.current_time_unix}"

        filename_ext = filename
        if self.number > 0:
            filename_ext += f"_{self.number + 1}"

        if isServer:
            self.run_command("rm -rf msquic_lttng*")
            self.run_command("rm l*b*d*.pcap")
            self.run_command("rm l*b*d*.log")
            self.run_command("rm l*b*d*_lost.csv")
            self.run_command("rm l*b*d*_spin.csv")
            self.run_command("rm l*b*d*_cwnd.csv")
            self.run_command("rm l*b*d*_wMax.csv")
            self.run_command("rm l*b*d*.csv")
            self.run_command("rm -rf l*b*d*/")

            self.run_command(f"tc qdisc del dev {self.interface} root netem")

        if isServer:
            if bandwidth > 0:
                if self.args.gilbert_elliot:
                    self.run_command(
                        f"tc qdisc add dev {self.interface} root netem delay {delay}ms rate {bandwidth}mbit loss gemodel {self.gilbert_p} {self.gilbert_r} {100.0-self.gilbert_h} {100.0-self.gilbert_k}",
                    )
                else:
                    self.run_command(
                        f"tc qdisc add dev {self.interface} root netem loss {lossRate}% delay {delay}ms rate {bandwidth}mbit",
                    )
            else:
                if self.args.gilbert_elliot:
                    self.run_command(
                        f"tc qdisc add dev {self.interface} root netem delay {delay}ms loss gemodel {self.gilbert_p} {self.gilbert_r} {100.0-self.gilbert_h} {100.0-self.gilbert_k}",
                    )
                else:
                    self.run_command(
                        f"tc qdisc add dev {self.interface} root netem loss {lossRate}% delay {delay}ms",
                    )

        commands = []
        command = None

        if isServer:
            commands = [
                f"tshark -q -i {self.interface} -f 'udp port 4567' -w {filename_ext}.pcap -o tls.keylog_file:{SSLKEYLOGFILE}",
                "./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Debug_openssl/quicsample -server -cert_file:./artifacts/bin/linux/x64_Debug_openssl/cert.pem -key_file:./artifacts/bin/linux/x64_Debug_openssl/priv.key --gtest_filter=Full.Verbose",
            ]
        else:
            command = f"./artifacts/bin/linux/x64_Debug_openssl/quicsample -client -unsecure -target:{self.serverIp}"

        if isServer:
            self.run_command(f"touch {filename_ext}.pcap") # Create the file first in order to prevent permission denied error
            tshark_process = self.run_command(commands[0], detach=True)
            print(f"tshark_pid: {tshark_process.pid}")

            log_wrapper_process = self.run_command(
                commands[1], detach=True, input=True
            )

            # 서버: 30초동안 대기
            output_thread = threading.Thread(target=self.read_output, args=(log_wrapper_process,))
            output_thread.start()
            print("Output rhead thread started")

            output_thread.join()
            print("Output thread joined")

            self.run_command("echo ''", input=True)
            log_wrapper_process.stdin.write("\n")
            log_wrapper_process.stdin.flush()

            print("서버: 엔터 키 전송 완료")

            log_wrapper_process.wait()

        else:
            while True:
                log_wrapper_processes = []
                for i in range(self.args.flows):
                    log_wrapper_process = self.run_command(command, detach=True, input=True)
                    output_thread = threading.Thread(target=self.read_output, args=(log_wrapper_process, i, 30, False))

                    log_wrapper_processes.append((log_wrapper_process, output_thread))

                    output_thread.start()
                    print("Output read thread started")
                
                for log_wrapper_process, output_thread in log_wrapper_processes:
                    output_thread.join()
                    print("Output thread joined")

                    # self.run_command("echo ''", input=True)
                    # log_wrapper_process.stdin.write("\n")
                    # log_wrapper_process.stdin.flush()

                    # print(f"클라이언트에 엔터 키 전송 완료: {log_wrapper_process.pid}")

                    log_wrapper_process.wait()

                initiation_count = 0
                for item in self.clientInitiated.items():
                    if item[1]:
                        initiation_count += 1
                        self.clientInitiated[item[0]] = False
                if initiation_count == self.args.flows:
                    # sleep(120) # 2분 대기
                    break
                else: # 서버 안 열려도 리턴코드 0임 initial 몇번 보내고 포기 -> 리턴코드 0
                    print("The server is not open, Retrying in 5 sec...")
                    sleep(5)

        if isServer:
            # 실행 종료 시 tshark 종료
            self.send_signal_to_process(tshark_process, signal=signal.SIGINT)

            self.run_command(f"mv msquic_lttng0/quic.log ./{filename_ext}.log")
            # log 파일이 정상적으로 옮겨지는 것까지는 확인 완료

            self.run_command(
                f"""sh -c \'tshark -r {filename_ext}.pcap -q -z io,stat,0.1 \
    | grep -P \"\\d+\\.?\\d*\\s+<>\\s+|Interval +\\|\" \
    | tr -d \" \" | tr \"|\" \",\" | sed -E \"s/<>/,/; s/(^,|,$)//g; s/Interval/Start,Stop/g\" > {filename_ext}.csv\'""",
            )

            self.run_command(f"mkdir {foldername}")
            self.run_command(f"mv -f {filename_ext}.* {foldername}/")

            self.run_command(
                f"python loadSpinData.py -c -n {self.number + 1} {self.msquic_path}/{foldername}",
                cwd=self.script_path,
            )

            self.run_command(f"cp -rf {foldername} {MSQUIC_LOG_PATH}/")
            self.run_command(f"rm -rf {foldername}")
            self.run_command("rm -rf msquic_lttng0")

            self.run_command(f"tc qdisc del dev {self.interface} root")

        # if not isServer:
        #     self.run_command(f"mv {SSLKEYLOGFILE} {MSQUIC_LOG_PATH}/")

        print("Run complete")


def main():

    parser = argparse.ArgumentParser(description="Run Quic with msquic. If loss rate or delay is not specified, the script will run for several sample values.")

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
        "-i",
        "--instance",
        type=int,
        default=1,
        help="QUIC Server & Client pair instance number",
        required=False,
    )

    parser.add_argument(
        "-if",
        "--interface",
        type=str,
        default="eth0",
        help="Network interface",
        required=False,
    )

    parser.add_argument(
        "-n",
        "--number",
        type=int,
        default=1,
        help="Number of times to run the test",
        required=False,
    )

    gilbert_elliot_group = parser.add_argument_group("Gilbert Elliot model")

    gilbert_elliot_group.add_argument(
        "-ge",
        "--gilbert_elliot",
        action="store_true",
        help="Use Gilbert Elliot model",
        required=False,
    )

    # Mutually exclusive group for --server and --client
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--server', action='store_true', help="Run as server")
    group.add_argument('--client', action='store_true', help="Run as client")

    parser.add_argument(
        "-t",
        "--target",
        type=str,
        help="Target IP address (required in --client mode)",
    )

    gilbert_elliot_group.add_argument(
        "-gp",
        "--gilbert_p",
        type=float,
        help="Gilbert Elliot model p value",
    )

    gilbert_elliot_group.add_argument(
        "-gr",
        "--gilbert_r",
        type=float,
        help="Gilbert Elliot model r value",
    )

    gilbert_elliot_group.add_argument(
        "-gh",
        "--gilbert_h",
        type=float,
        help="Gilbert Elliot model h value",
    )

    gilbert_elliot_group.add_argument(
        "-gk",
        "--gilbert_k",
        type=float,
        help="Gilbert Elliot model k value",
    )

    parser.add_argument(
        "-f",
        "--flows",
        type=int,
        default=1,
        help="Number of flows",
        required=False,
    )

    parser.add_argument(
        "-p",
        "--path",
        type=str,
        default=MSQUIC_PATH,
        help="Path to msquic",
        required=False,
    )

    args = parser.parse_args()
    if args.client and not args.target:
        parser.error("--target is required in --client mode")
    
    if args.gilbert_elliot:
        if not args.gilbert_p or not args.gilbert_r or not args.gilbert_h or not args.gilbert_k:
            parser.error("Gilbert Elliot model requires --gilbert_p, --gilbert_r, --gilbert_h, and --gilbert_k")

    lastValues = []
    lossRates = []
    delays = []
    if args.loss >= 0:
        lossRates = [args.loss]
    elif args.gilbert_elliot:
        lossRates = [0.0]
    else:
        # lossRates = range(0, 11, 1)
        lossRates = [0.5, 2.7, 4.0]
    # bitRatesinMbps = range(0, 100)
    if args.delay >= 0:
        delays = [args.delay]
    else:
        # delays = range(0, 200, 5)
        delays = [10, 33, 60]

    # if args.loss < 0 and args.delay < 0:
    #     try:
    #         with open("lastValues.txt", "r", encoding="utf-8") as f:
    #             lastValues = f.readlines()
    #             lossRates = range(int(lastValues[0]), 11, 1)
    #             delays = range(int(lastValues[1]), 200, 5)
    #     except FileNotFoundError:
    #         pass

    runner = QuicRunner(args)

    
    full_command = " ".join(["python3"] + ["autoQuic-reallinks.py"] + [f"{k} {v}" for k, v in vars(args).items()])
    with open(f"fullCommand_{runner.current_time_unix}.txt", "w", encoding="utf-8") as f:
        f.write(full_command)
    runner.run_command(f"cp fullCommand_{runner.current_time_unix}.txt {MSQUIC_LOG_PATH}/")

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
            # if args.loss < 0 and args.delay < 0:
            #     delays = range(0, 200, 5)  # 한바퀴 돌고 리셋


if __name__ == "__main__":
    main()
