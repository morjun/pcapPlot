import pyshark

import matplotlib.pyplot as plt
from matplotlib import ticker
import numpy as np
import pandas as pd
import statistics

import argparse
from datetime import datetime

import matplotlib
import pyqtgraph as pg
from PyQt5 import QtWidgets


plotItem1 = None
view2 = None
view3 = None
view4 = None

def loadData(args):
    times = np.array([], dtype=float)
    lostTimes = np.array([], dtype=float)
    cwndTimes = np.array([], dtype=float)

    losses = np.array([], dtype=int)
    spins = np.array([], dtype=int)
    rtts = np.array([], dtype=float)
    cwnds = np.array([], dtype=int)

    ports = {"interop": 4433, "samplequic": 4567}
    port = 0
    if args.file[0] not in ports:
        port = 4567
    else:
        port = ports[args.file[0]]

    cap = pyshark.FileCapture(f"{args.file[0]}.pcapng")

    initialTime = 0
    prevSpin = -1 # 처음 Short Header Packet 감지용 
    prevTime = 0
    numSpin = -1 # 처음 Short Header Packet의 spin bit 0이 발견되는 순간 spin 횟수 0

    loadTime = datetime.now()
    for packet in cap:
        if hasattr(packet, "quic"):
            if initialTime == 0:  # int
                initialTime = packet.sniff_time.timestamp() #Initial
            if hasattr(packet.quic, "spin_bit"):
                if packet.udp.srcport == str(port):  # 서버가 전송한 패킷만
                    time = packet.sniff_time.timestamp() - initialTime
                    spin = packet.quic.spin_bit
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
    
    print(f"load time: {datetime.now() - loadTime}")
    spinFrame = pd.DataFrame({"time": times, "spin": spins})
    throughputFrame = pd.read_csv(f"{args.file[0]}.csv")

    with open(f"{args.file[0]}.log") as f:
        lines = f.readlines()
        initialLogTime = 0
        for line in lines:
            timeString = str(line.split("]")[2].replace("[", ""))
            if "[S][RX][0] LH Ver:" in line and "Type:I" in line:
                initialLogTime = datetime.strptime(timeString, "%H:%M:%S.%f")
            elif "Lost: " in line and "[conn]" in line:
                logTime = (
                    datetime.strptime(timeString, "%H:%M:%S.%f") - initialLogTime
                ).total_seconds()
                lossCount = int(line.split("Lost: ")[1].split(" ")[0])
                if lossCount > 0:
                    lostTimes = np.append(lostTimes, float(logTime))
                    losses = np.append(losses, int(lossCount))
            elif "OUT: " in line and "CWnd=" in line:
                if initialLogTime == 0:
                    continue
                logTime = (
                    datetime.strptime(timeString, "%H:%M:%S.%f") - initialLogTime
                ).total_seconds()
                cwnd = int(line.split("CWnd=")[1].split(" ")[0])
                cwnds = np.append(cwnds, int(cwnd))
                cwndTimes = np.append(cwndTimes, float(logTime))

    throughputFrame["All Packets"] = [
        # (x * 8 / 1000000) / throughputFrame["Interval start"][1]
        (x * 8) / throughputFrame["Interval start"][1]
        for x in throughputFrame["All Packets"]
    ]  # Bp100ms -> Mbps
    lostFrame = pd.DataFrame({"time": lostTimes, "loss": losses})
    cwndFrame = pd.DataFrame({"time" : cwndTimes, "cwnd": cwnds})
    spinFrequency = numSpin / 2 * (prevTime - initialSpinTime)

    print(f"평균 rtt(spin bit 기준): {statistics.mean(rtts)}")
    print(f"평균 throughput: {statistics.mean(throughputFrame['All Packets'])/1000000}Mbps")
    print(f"Lost 개수: {sum(losses)}")
    print(f"총 spin 수 : {numSpin}")
    print(f"spin frequency: {spinFrequency}")

    with open("stats.csv", "a") as f:
        f.write(f"{args.loss}, {args.bandwidth}, {args.delay}, {spinFrequency}\n")

    return spinFrame, throughputFrame, lostFrame, cwndFrame 


class MainWindow(QtWidgets.QMainWindow): # main view
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.spinFrame, self.throughputFrame, self.lostFrame, self.cwndFrame = loadData(self.args)
        self.drawGraph()
        self.show()

    def drawGraph(self):
        global plotItem1, view2, view3, view4

        # self.plotGraph = pg.PlotWidget()
        # self.setCentralWidget(self.plotGraph)

        layoutWidget = pg.GraphicsLayoutWidget()
        layoutWidget.setBackground("w")
        # layoutWidget.showGrid(x=True, y=True)
        self.setCentralWidget(layoutWidget)
        # self.plotGraph.show()
        # self.plotGraph.clear()
        #Set window name
        self.setWindowTitle(self.args.file[0])

        # self.plotGraph.showGrid(x=True, y=True)
        # self.plotGraph.setBackground("w")

        allTimes = np.append(self.spinFrame["time"], self.lostFrame["time"])
        # self.plotGraph.getAxis("bottom").setTicks([[(time, f"{time:.6f}") for time in allTimes]])
        # self.plotGraph.getAxis("bottom").setticks()

        # plotItem1 = self.plotGraph.plotItem
        plotItem1 = pg.PlotItem()
        view1 = plotItem1.getViewBox()
        layoutWidget.addItem(plotItem1, 1, 3, 1, 1)

        pgLayout = layoutWidget
        plotItem1.setLabel("left", "Spin bit", units="bit")
        plotItem1.setLabel("bottom", "Time", units="s")
        plotItem1.axis_left = plotItem1.getAxis("left")
        pgLayout.addItem(plotItem1.axis_left, 1, 2, 1, 1)

        # blankAx = pg.AxisItem("bottom")
        # blankAx.setPen('#000000')
        # layoutWidget.addItem(blankAx, 2, 3)

        view2 = pg.ViewBox()
        axis2 = pg.AxisItem("right")
        pgLayout.addItem(axis2, 1, 4, 1, 1)
        plotItem1.scene().addItem(view2)
        view2.setXLink(plotItem1)
        axis2.setLabel("Throughput", units="bps")
        axis2.linkToView(view2)
        # plotItem1.showAxis("right")
        # plotItem1.getAxis("right").linkToView(plotItem2)
        # plotItem1.getAxis("right").setLabel("Throughput", units="Mbps")

        view3 = pg.ViewBox()
        axis3 = pg.AxisItem("left")
        pgLayout.addItem(axis3, 1, 1, 1, 1)
        plotItem1.scene().addItem(view3)
        axis3.linkToView(view3)
        axis3.setZValue(-10000)
        axis3.setLabel("Lost", units="개")
        view3.setXLink(plotItem1)
        view3.setYLink(plotItem1)

        view4 = pg.ViewBox()
        axis4 = pg.AxisItem("right")
        pgLayout.addItem(axis4, 1, 5, 1, 1)
        plotItem1.scene().addItem(view4)
        axis4.linkToView(view4)
        axis4.setZValue(-10000)
        axis4.setLabel("CWnd", units="Bytes")
        view4.setXLink(plotItem1)
        
        def updateViews():
            ## view has resized; update auxiliary views to match
            view2.setGeometry(plotItem1.vb.sceneBoundingRect())
            view3.setGeometry(plotItem1.vb.sceneBoundingRect())
            view4.setGeometry(plotItem1.vb.sceneBoundingRect())
            ## need to re-update linked axes since this was called
            ## incorrectly while views had different shapes.
            ## (probably this should be handled in ViewBox.resizeEvent)
            view2.linkedViewChanged(plotItem1.vb, view2.XAxis)
            view3.linkedViewChanged(plotItem1.vb, view3.XAxis)
            view4.linkedViewChanged(plotItem1.vb, view4.XAxis)
        
        updateViews()
        plotItem1.vb.sigResized.connect(updateViews)

        plotItem1.plot(self.spinFrame["time"].values.flatten(), self.spinFrame["spin"].values.flatten(), pen="b")
        view2.addItem(pg.PlotCurveItem(
            self.throughputFrame["Interval start"].values.flatten(),
            self.throughputFrame["All Packets"].values.flatten(),
            pen="g",)
        )
        view3.addItem(pg.ScatterPlotItem(self.lostFrame["time"].values.flatten(), self.lostFrame["loss"].values.flatten(), pen="r", symbol="o", symbolPen = "r", symbolBrush = "r", symbolSize = 10))
        view4.addItem(pg.PlotCurveItem(
            self.cwndFrame["time"].values.flatten(),
            self.cwndFrame["cwnd"].values.flatten(),
            pen="m",)
        )


class PyPlotGraph:
    def __init__(self, args):
        self.spinFrame, self.throughputFrame, self.lostFrame, self.cwndFrame = loadData(args)

    # 파일명.csv (throughput 기록), 파일명.pcapng (wireshark 패킷트레이스), 파일명.log(msquic log, loss 추적용) 필요
    def pyplotGraph(self):
        matplotlib.use("TkAgg")
        fig, ax = plt.subplots(sharex=True, sharey=True)
        fig.set_size_inches(15, 3)

        ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%0.9f"))

        ax.plot(
            self.spinFrame["time"],
            self.spinFrame["spin"],
            markersize=1,
        )
        ax.plot(
            self.lostFrame["time"],
            self.lostFrame["loss"],
            "r*",
            markersize=10,
            label="lost",
        )

        ax.set_ylabel("Spin bit & # Lost")
        ax.set_yticks([1.0, 0.0])
        ax.set_ylim([0, max(self.lostFrame["loss"]) * 1.1])

        ax2 = ax.twinx()
        ax2.set_ylabel("Throughput (Mbps)")

        ax2.set_ylim([0, max(self.throughputFrame["All Packets"]) * 1.1])
        ax2.yaxis.set_major_locator(ticker.AutoLocator())

        ax2.plot(
            self.throughputFrame["Interval start"],
            self.throughputFrame["All Packets"],
            "g",
            label="throughput",
        )

        ax.legend(loc="upper left")
        ax2.legend(loc="upper right")
        ax.set_xticks(
            self.spinFrame["time"],
            [f"{x:.6f}" for x in self.spinFrame["time"]],
            rotation=45,
            color="blue",
        )
        ax.set_xticks(
            self.lostFrame["time"],
            [f"{x:.6f}" for x in self.lostFrame["time"]],
            rotation=45,
            color="red",
            minor=True,
        )
        # plt.xlim(0, 20.0)
        plt.show()


def main():
    parser = argparse.ArgumentParser(description="Show spin bit")
    parser.add_argument("file", metavar="file", type=str, nargs=1)

    parser.add_argument("-l", "--loss", type=float, default=0.0, help="loss rate of the link", required=False)
    parser.add_argument("-d", "--delay", type=int, default=0, help="delay of the link(ms)", required=False)
    parser.add_argument("-b", "--bandwidth", type=int, default=0, help="bandwidth of the link(Mbps)", required=False)

    args = parser.parse_args()

    app = QtWidgets.QApplication([])
    mainProgram = MainWindow(args)
    app.exec()


if __name__ == "__main__":
    main()
