import signal
from time import sleep
import argparse
import subprocess
import shlex
import os
import glob

MSQUIC_LOG_PATH = "/msquic_logs"
MSQUIC_PATH = "/root/network/quic/msquic"
SSLKEYLOGFILE = "/root/sslkey.log"


class QuicRunner:
    def __init__(self, args):
        self.args = args
        self.serverIp = args.target
        self.lossRate = 0.0
        self.delay = 0.0
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

    def run_command(
        self, command, shell=False, cwd=MSQUIC_PATH, detach=False, input=False
    ):
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
        self.lossRate = lossRate
        self.delay = delay

        filename = f"l{lossRate}b{self.args.bandwidth}d{delay}"
        filename_ext = filename
        if self.number > 0:
            filename_ext += f"_{self.number + 1}"

        self.run_command("rm -rf msquic_lttng*")
        self.run_command("rm l*b*d*.pcap")
        self.run_command("rm l*b*d*.log")
        self.run_command("rm l*b*d*_lost.csv")
        self.run_command("rm l*b*d*_spin.csv")
        self.run_command("rm l*b*d*_cwnd.csv")
        self.run_command("rm l*b*d*_wMax.csv")
        self.run_command("rm l*b*d*.csv")
        self.run_command("rm -rf l*b*d*/")

        self.run_command("tc qdisc del dev eth1 root netem")

        # if self.args.bandwidth > 0:
        #     self.run_command(
        #         f"tc qdisc add dev eth1 root netem loss {lossRate}% delay {delay}ms rate {self.args.bandwidth}mbit",
        #     )
        # else:
        #     self.run_command(
        #         f"tc qdisc add dev eth1 root netem loss {lossRate}% delay {delay}ms",
        #     )

        commands = [
            f"tshark -i eth1 -w {filename_ext}.pcap -o tls.keylog_file:{SSLKEYLOGFILE}",
            f"./scripts/log_wrapper.sh ./artifacts/bin/linux/x64_Debug_openssl/quicsample -client -unsecure -target:{self.serverIp} --gtest_filter=Full.Verbose",
        ]

        tshark_process = self.run_command(commands[0], detach=True)
        print(f"tshark_pid: {tshark_process.pid}")

        while True:
            log_wrapper_process = self.run_command(commands[1])
            if log_wrapper_process.returncode == 0:
                break
            else:
                print("The server is not open, Retrying in 5 sec...")
                sleep(5)

        # 클라이언트: All Done 출력될 때까지 계속 대기
        # for line in iter(log_wrapper_process.stdout.readline, b''):
        #     # print(line.decode(), end='')
        #     if "All Done" in line.decode():
        #         break

        # 클라이언트 실행 종료 시 tshark 종료
        self.send_signal_to_process(tshark_process, signal=signal.SIGINT)

        self.run_command(f"mv msquic_lttng0/quic.log ./{filename_ext}.log")
        # log 파일이 정상적으로 옮겨지는 것까지는 확인 완료

        self.run_command(
            f"""sh -c \'tshark -r {filename_ext}.pcap -q -z io,stat,0.1 \
| grep -P \"\\d+\\.?\\d*\\s+<>\\s+|Interval +\\|\" \
| tr -d \" \" | tr \"|\" \",\" | sed -E \"s/<>/,/; s/(^,|,$)//g; s/Interval/Start,Stop/g\" > {filename_ext}.csv\'""",
        )

        self.run_command(f"mkdir {filename}")
        self.run_command(f"mv -f {filename_ext}.* {filename}/")

        self.run_command(
            f"python loadSpinData.py -c ./{filename_ext}",
        )

        self.run_command(f"cp -rf {filename} {MSQUIC_LOG_PATH}/")
        self.run_command(f"rm -rf {filename}")
        self.run_command("rm -rf msquic_lttng0")

        self.run_command("tc qdisc del dev eth1 root")
        self.run_command(f"cp {SSLKEYLOGFILE} {MSQUIC_LOG_PATH}/")


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
        "-i",
        "--instance",
        type=int,
        default=1,
        help="QUIC Server & Client pair instance number",
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

    parser.add_argument(
        "-t",
        "--target",
        type=str,
        help="Target IP address",
        required=True,
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
