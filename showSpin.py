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

    ports = {"interop": 4433, "samplequic": 4567}
    port = 0
    if args.file[0] not in ports:
        port = 4567
    else:
        port = ports[args.file[0]]

    try:
        spinFrame = pd.read_csv(f"{args.file[0]}_spin.csv")
    except FileNotFoundError:
        cap = pyshark.FileCapture(f"{args.file[0]}.pcapng")
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
        spinFrame.to_csv(f"{args.file[0]}_spin.csv", index=False)

    throughputFrame = pd.read_csv(f"{args.file[0]}.csv")
    with open(f"{args.file[0]}.log") as f:
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
    print(f"Lost 개수: {len(lostFrame["loss"])}개")
    print(f"Loss reason 0: {len(lostFrame[lostFrame['loss'] == 0])}개")
    print(f"Loss reason 1: {len(lostFrame[lostFrame['loss'] == 1])}개")
    print(f"Loss reason 2: {len(lostFrame[lostFrame['loss'] == 2])}개")

    if args.bandwidth >= 0 and prevTime > 0:
        with open("stats.csv", "a") as f:
            f.write(
                f"{args.loss}, {args.bandwidth}, {args.delay}, {spinFrequency}, {avgThroughput}, {sum(lossReasons)}\n"
            )

    lostFrame.to_csv(f"{args.file[0]}_lost.csv", index=False)
    cwndFrame.to_csv(f"{args.file[0]}_cwnd.csv", index=False)
    wMaxFrame.to_csv(f"{args.file[0]}_wMax.csv", index=False)

    # cf1 = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest", tolerance=0.01)
    # cf2 = pd.merge_asof(lostFrame, spinFrame, on="time", direction="nearest", tolerance=0.01)
    # cf3 = pd.concat([cf1, cf2[cf2['loss'].isnull()]]).sort_index()
    # cf3 = pd.merge(spinFrame, lostFrame, on="time", how="outer", sort=True)

    # combinedFrame = pd.merge_asof(spinFrame, lostFrame, on="time", direction="nearest")
    # combinedFrame = pd.merge_asof(combinedFrame, cwndFrame, on="time", direction="nearest")
    # combinedFrame.to_csv(f"{args.file[0]}_combined.csv", index=False)

    return spinFrame, throughputFrame, lostFrame, cwndFrame, wMaxFrame


class MainWindow(QtWidgets.QMainWindow):  # main view
    def __init__(self, args):
        super().__init__()
        self.args = args
        (
            self.spinFrame,
            self.throughputFrame,
            self.lostFrame,
            self.cwndFrame,
            self.wMaxFrame,
        ) = loadData(self.args)

        self.layoutWidget = pg.GraphicsLayoutWidget()
        self.layoutWidget.setBackground("w")

        self.setCentralWidget(self.layoutWidget)
        # layoutWidget.showGrid(x=True, y=True)
        # self.plotGraph.show()
        # self.plotGraph.clear()
        # Set window name
        self.setWindowTitle(self.args.file[0])

        self.drawGraph()
        self.drawTCGraph()
        self.show()

    def drawTCGraph(self):
        plotItem2 = pg.PlotItem()
        view5 = plotItem2.getViewBox()
        self.layoutWidget.addItem(plotItem2, 5, 1, 2, 5)
        plotItem2.setLabel("left", "Throughput", units="bps")
        plotItem2.setLabel("bottom", "CWnd", units="Bytes")
        throughput2 = self.throughputFrame.rename(columns={"Interval start": "time"})
        print(throughput2)
        ctFrame = pd.merge_asof(
            self.cwndFrame, throughput2, on="time", direction="nearest", tolerance=0.01
        )
        print(ctFrame)
        view5.addItem(
            pg.ScatterPlotItem(
                ctFrame["cwnd"].values.flatten(),
                ctFrame["All Packets"].values.flatten(),
                pen="b",
            )
        )

    def drawGraph(self):
        # self.plotGraph = pg.PlotWidget()
        # self.setCentralWidget(self.plotGraph)
        # self.plotGraph.showGrid(x=True, y=True)
        # self.plotGraph.setBackground("w")

        # allTimes = np.append(self.spinFrame["time"], self.lostFrame["time"])
        # self.plotGraph.getAxis("bottom").setTicks([[(time, f"{time:.6f}") for time in allTimes]])
        # self.plotGraph.getAxis("bottom").setticks()

        # plotItem1 = self.plotGraph.plotItem
        plotItem1 = pg.PlotItem()
        legend = plotItem1.addLegend(offset=(30, 30))

        view1 = plotItem1.getViewBox()
        self.layoutWidget.addItem(plotItem1, 1, 3, 2)

        pgLayout = self.layoutWidget
        plotItem1.setLabel("left", "Spin bit", units="bit")
        plotItem1.axis_left = plotItem1.getAxis("left")
        pgLayout.addItem(plotItem1.axis_left, 1, 2, 2)
        # blankAx = pg.AxisItem("bottom")
        # blankAx.setPen("w")
        # layoutWidget.addItem(blankAx, 3, 1, 1, 4)

        view2 = pg.ViewBox()
        axis2 = pg.AxisItem("right")
        pgLayout.addItem(axis2, 1, 4, 2, 1)
        pgLayout.scene().addItem(view2)
        view2.setXLink(plotItem1)
        axis2.setLabel("Throughput", units="bps")
        axis2.linkToView(view2)

        view3 = pg.ViewBox()
        # axis3 = pg.AxisItem("left")
        # pgLayout.addItem(axis3, 1, 1, 2, 1)
        pgLayout.scene().addItem(view3)
        # axis3.linkToView(view3)
        # axis3.setLabel("Lost", units="개")
        view3.setXLink(plotItem1)
        view3.setYLink(plotItem1)

        view4 = pg.ViewBox()
        axis4 = pg.AxisItem("right")
        pgLayout.addItem(axis4, 1, 5, 2, 1)
        pgLayout.scene().addItem(view4)
        axis4.linkToView(view4)
        axis4.setLabel("CWnd", units="Bytes")
        view4.setXLink(plotItem1)

        view6 = pg.ViewBox()
        axis6 = pg.AxisItem("right")
        pgLayout.addItem(axis6, 1, 6, 2, 1)
        pgLayout.scene().addItem(view6)
        axis6.linkToView(view6)
        axis6.setLabel("W_max", units="Bytes")
        view6.setXLink(plotItem1)
        view6.setYLink(view4)

        plotItem1.axis_bottom = plotItem1.getAxis("bottom")
        pgLayout.addItem(plotItem1.axis_bottom, 3, 3, 2, 1)
        plotItem1.setLabel("bottom", "Time", units="s")

        def updateViews():
            ## view has resized; update auxiliary views to match
            view2.setGeometry(plotItem1.vb.sceneBoundingRect())
            view3.setGeometry(plotItem1.vb.sceneBoundingRect())
            view4.setGeometry(plotItem1.vb.sceneBoundingRect())
            view6.setGeometry(plotItem1.vb.sceneBoundingRect())
            ## need to re-update linked axes since this was called
            ## incorrectly while views had different shapes.
            ## (probably this should be handled in ViewBox.resizeEvent)
            view2.linkedViewChanged(plotItem1.vb, view2.XAxis)
            view3.linkedViewChanged(plotItem1.vb, view3.XAxis)
            view4.linkedViewChanged(plotItem1.vb, view4.XAxis)
            view6.linkedViewChanged(plotItem1.vb, view6.XAxis)

        view2.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        view3.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        view4.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        view6.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)

        updateViews()
        plotItem1.vb.sigResized.connect(updateViews)

        rackFrame = self.lostFrame[self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_RACK]
        fackFrame = self.lostFrame[self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_FACK]
        probeFrame = self.lostFrame[self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_PROBE]

        spinItem = pg.PlotCurveItem(
            self.spinFrame["time"].values.flatten(),
            self.spinFrame["spin"].values.flatten(),
            pen="b",
        )
        throughputItem = pg.PlotCurveItem(
            self.throughputFrame["Interval start"].values.flatten(),
            self.throughputFrame["All Packets"].values.flatten(),
            pen="g",
        )
        lossItem0 = pg.ScatterPlotItem(
            rackFrame["time"].values.flatten(),
            rackFrame.mask(self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_RACK, 1)["loss"].values.flatten(),
            pen="r",
            symbol="o",
            symbolPen="r",
            symbolBrush="r",
            symbolSize=10,
        )
        lossItem1 = pg.ScatterPlotItem(
            fackFrame["time"].values.flatten(),
            fackFrame.mask(self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_FACK, 1)["loss"].values.flatten(),
            pen="c",
            symbol="o",
            symbolPen="c",
            symbolBrush="c",
            symbolSize=10,
        )
        lossItem2 = pg.ScatterPlotItem(
            probeFrame["time"].values.flatten(),
            probeFrame.mask(self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_PROBE, 1)["loss"].values.flatten(),
            pen="y",
            symbol="o",
            symbolPen="y",
            symbolBrush="y",
            symbolSize=10,
        )
        cwndItem = pg.PlotCurveItem(
            self.cwndFrame["time"].values.flatten(),
            self.cwndFrame["cwnd"].values.flatten(),
            pen="m",
        )
        wMaxItem = pg.PlotCurveItem(
            self.wMaxFrame["time"].values.flatten(),
            self.wMaxFrame["wMax"].values.flatten(),
            pen="k",
        )

        view1.addItem(spinItem)
        view2.addItem(throughputItem)
        view3.addItem(lossItem0)
        view3.addItem(lossItem1)
        view3.addItem(lossItem2)
        view4.addItem(cwndItem)
        view6.addItem(wMaxItem)

        legend.addItem(spinItem, "Spin bit")
        legend.addItem(lossItem0, "Lost: QUIC_TRACE_PACKET_LOSS_RACK")
        legend.addItem(lossItem1, "Lost: QUIC_TRACE_PACKET_LOSS_FACK")
        legend.addItem(lossItem2, "Lost: QUIC_TRACE_PACKET_LOSS_PROBE")
        legend.addItem(throughputItem, "Throughput")
        legend.addItem(cwndItem, "CWnd")
        legend.addItem(wMaxItem, "W_max")


class PyPlotGraph:
    def __init__(self, args):
        self.spinFrame, self.throughputFrame, self.lostFrame, self.cwndFrame = loadData(
            args
        )

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

    parser.add_argument(
        "-l",
        "--loss",
        type=float,
        default=0.0,
        help="loss rate of the link(%)",
        required=False,
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=int,
        default=0,
        help="delay of the link(ms)",
        required=False,
    )
    parser.add_argument(
        "-b",
        "--bandwidth",
        type=int,
        default=-1,
        help="bandwidth of the link(Mbps)",
        required=False,
    )
    parser.add_argument(
        "-n",
        "--no-plot",
        type=bool,
        default=False,
        help="Only update the data",
        required=False,
    )

    args = parser.parse_args()

    if args.no_plot:
        loadData(args)
        return
    else:
        app = QtWidgets.QApplication([])
        mainProgram = MainWindow(args)
        app.exec()

if __name__ == "__main__":
    main()
