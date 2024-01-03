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
plotItem2 = None
plotItem3 = None

def loadData(args):
    times = np.array([], dtype=float)
    lostTimes = np.array([], dtype=float)
    losses = np.array([], dtype=int)
    spins = np.array([], dtype=int)
    rtts = np.array([], dtype=float)

    ports = {"interop": 4433, "samplequic": 4567}
    port = 0
    if args.file[0] not in ports:
        port = 4567
    else:
        port = ports[args.file[0]]

    cap = pyshark.FileCapture(f"{args.file[0]}.pcapng")

    initialTime = 0
    prevSpin = 0
    prevTime = 0

    for packet in cap:
        if hasattr(packet, "quic"):
            if initialTime == 0:  # int
                initialTime = packet.sniff_time.timestamp()
            if hasattr(packet.quic, "spin_bit"):
                if packet.udp.srcport == str(port):  # 서버가 전송한 패킷만
                    time = packet.sniff_time.timestamp() - initialTime
                    spin = packet.quic.spin_bit
                    if prevSpin != spin:
                        if prevTime != 0:
                            rtt = time - prevTime
                            rtts = np.append(rtts, float(rtt))  # spin -> rtt 계산
                        prevTime = time
                    times = np.append(times, float(time))
                    spins = np.append(spins, int(spin))
                    prevSpin = spin
                    if (int(packet.number) % 1000) == 0:
                        print(f"{packet.number} packets processed")

    spinFrame = pd.DataFrame({"time": times, "spin": spins})
    throughputFrame = pd.read_csv(f"{args.file[0]}.csv")
    print(throughputFrame)
    print(
        throughputFrame["All Packets"],
        throughputFrame["Interval start"],
        throughputFrame["TCP Errors"],
    )

    with open(f"{args.file[0]}.log") as f:
        lines = f.readlines()
        initialLogtime = 0
        for line in lines:
            timeString = str(line.split("]")[2].replace("[", ""))
            if "[S][RX][0] LH Ver:" in line and "Type:I" in line:
                initialLogtime = datetime.strptime(timeString, "%H:%M:%S.%f")
            elif "Lost: " in line and "[conn]" in line:
                logTime = (
                    datetime.strptime(timeString, "%H:%M:%S.%f") - initialLogtime
                ).total_seconds()
                lossCount = int(line.split("Lost: ")[1].split(" ")[0])
                print(logTime, lossCount)
                if lossCount > 0:
                    lostTimes = np.append(lostTimes, float(logTime))
                    losses = np.append(losses, int(lossCount))

    throughputFrame["All Packets"] = [
        (x * 8 / 1000000) / throughputFrame["Interval start"][1]
        for x in throughputFrame["All Packets"]
    ]  # Bp100ms -> Mbps
    lostFrame = pd.DataFrame({"time": lostTimes, "loss": losses})

    print(lostTimes)
    print(f"평균 rtt(spin bit 기준): {statistics.mean(rtts)}")
    print(f"평균 throughput: {statistics.mean(throughputFrame['All Packets'])}Mbps")
    print(f"Lost 개수: {sum(losses)}")

    return spinFrame, throughputFrame, lostFrame


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, args):
        super().__init__()
        self.spinFrame, self.throughputFrame, self.lostFrame = loadData(args)
        self.drawGraph()

    def drawGraph(self):
        global plotItem1, plotItem2, plotItem3
        self.plotGraph = pg.PlotWidget()
        self.setCentralWidget(self.plotGraph)
        self.plotGraph.show()
        self.plotGraph.clear()
        self.plotGraph.showGrid(x=True, y=True)
        self.plotGraph.setBackground("w")
        allTimes = np.append(self.spinFrame["time"], self.lostFrame["time"])
        # self.plotGraph.getAxis("bottom").setTicks([[(time, f"{time:.6f}") for time in allTimes]])
        # self.plotGraph.getAxis("bottom").setticks()

        pgLayout = self.plotGraph.plotItem.layout
        plotItem1 = self.plotGraph.plotItem
        plotItem1.setLabel("left", "Spin bit", units="bit개")
        plotItem1.setLabel("bottom", "Time", units="s")

        plotItem2 = pg.ViewBox()
        plotItem1.showAxis("right")
        plotItem1.scene().addItem(plotItem2)
        plotItem1.getAxis("right").linkToView(plotItem2)
        plotItem2.setXLink(plotItem1)
        plotItem1.getAxis("right").setLabel("Throughput", units="Mbps")

        plotItem3 = pg.ViewBox()
        axis3 = pg.AxisItem("left")
        plotItem1.layout.addItem(axis3, 2, 1)
        plotItem1.scene().addItem(plotItem3)
        axis3.linkToView(plotItem3)
        axis3.setZValue(-10000)
        axis3.setLabel("Lost", units="개")
        plotItem3.setXLink(plotItem1)
        plotItem3.setYLink(plotItem1)

        def updateViews():
            global plotItem1, plotItem2, plotItem3
            ## view has resized; update auxiliary views to match
            plotItem2.setGeometry(plotItem1.vb.sceneBoundingRect())
            plotItem3.setGeometry(plotItem1.vb.sceneBoundingRect())
            ## need to re-update linked axes since this was called
            ## incorrectly while views had different shapes.
            ## (probably this should be handled in ViewBox.resizeEvent)
            plotItem2.linkedViewChanged(plotItem1.vb, plotItem2.XAxis)
            plotItem3.linkedViewChanged(plotItem1.vb, plotItem3.XAxis)
        
        updateViews()
        plotItem1.vb.sigResized.connect(updateViews)

        plotItem1.plot(self.spinFrame["time"].values.flatten(), self.spinFrame["spin"].values.flatten(), pen="b")
        plotItem2.addItem(pg.PlotCurveItem(
            self.throughputFrame["Interval start"].values.flatten(),
            self.throughputFrame["All Packets"].values.flatten(),
            pen="g",)
        )
        plotItem3.addItem(pg.ScatterPlotItem(self.lostFrame["time"].values.flatten(), self.lostFrame["loss"].values.flatten(), pen="r", symbol="o", symbolPen = "r", symbolBrush = "r", symbolSize = 10))


class PyPlotGraph:
    def __init__(self, args):
        self.spinFrame, self.throughputFrame, self.lostFrame = loadData(args)

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
    args = parser.parse_args()

    app = QtWidgets.QApplication([])
    mainProgram = MainWindow(args)
    mainProgram.show()
    app.exec()


if __name__ == "__main__":
    main()
