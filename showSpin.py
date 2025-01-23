
import argparse

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import ticker

import pandas as pd
import numpy as np


from PyQt5 import QtWidgets
import pyqtgraph as pg
from loadSpinData import loadData

QUIC_TRACE_PACKET_LOSS_RACK = 0
QUIC_TRACE_PACKET_LOSS_FACK = 1
QUIC_TRACE_PACKET_LOSS_PROBE = 2

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

        self.containerWidget = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(self.containerWidget)
        self.layout.addWidget(self.layoutWidget)
        self.setCentralWidget(self.containerWidget)

        # layoutWidget.showGrid(x=True, y=True)
        # self.plotGraph.show()
        # self.plotGraph.clear()
        # Set window name
        self.setWindowTitle(f"{self.args.file[0]} number {self.args.number}")

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

    # 추세선 계산
        bin_count = 20  # x축을 나눌 구간 수
        bins = np.linspace(ctFrame["cwnd"].min(), ctFrame["cwnd"].max(), bin_count + 1)
        ctFrame["bin"] = pd.cut(ctFrame["cwnd"], bins, labels=False)
        
        trend_data = ctFrame.groupby("bin").agg(
            x_mean=("cwnd", "mean"),
            y_mean=("All Packets", "mean")
        ).dropna()
        
        # 추세선 그리기
        trend_line = pg.PlotDataItem(
            trend_data["x_mean"].values,
            trend_data["y_mean"].values,
            pen=pg.mkPen(color="r", width=2),
            symbol=None
        )
        view5.addItem(trend_line)

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
        spinItem_dot = pg.ScatterPlotItem(
            self.spinFrame["time"].values.flatten(),
            self.spinFrame["spin"].values.flatten(),
            pen="b",
            symbol="o",
            symbolPen="b",
            symbolBrush="b",
            symbolSize=5,
        )
        throughputItem = pg.PlotCurveItem(
            self.throughputFrame["Interval start"].values.flatten(),
            self.throughputFrame["All Packets"].values.flatten(),
            pen="g",
        )
        throughputItem_dot = pg.ScatterPlotItem(
            self.throughputFrame["Interval start"].values.flatten(),
            self.throughputFrame["All Packets"].values.flatten(),
            pen="g",
            symbol="o",
            symbolPen="g",
            symbolBrush="g",
            symbolSize=5,
        )
        lossItem0 = pg.ScatterPlotItem(
            rackFrame["time"].values.flatten(),
            rackFrame.mask(self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_RACK, 2)["loss"].values.flatten(),
            pen="r",
            symbol="star",
            symbolPen="r",
            symbolBrush="r",
            symbolSize=20,
        )
        lossItem1 = pg.ScatterPlotItem(
            fackFrame["time"].values.flatten(),
            fackFrame.mask(self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_FACK, 2)["loss"].values.flatten(),
            pen="c",
            symbol="star",
            symbolPen="c",
            symbolBrush="c",
            symbolSize=5,
        )
        lossItem2 = pg.ScatterPlotItem(
            probeFrame["time"].values.flatten(),
            probeFrame.mask(self.lostFrame["loss"] == QUIC_TRACE_PACKET_LOSS_PROBE, 2)["loss"].values.flatten(),
            pen="y",
            symbol="star",
            symbolPen="y",
            symbolBrush="y",
            symbolSize=5,
        )
        cwndItem = pg.PlotCurveItem(
            self.cwndFrame["time"].values.flatten(),
            self.cwndFrame["cwnd"].values.flatten(),
            pen="m",
        )
        cwndItem_dot = pg.ScatterPlotItem(
            self.cwndFrame["time"].values.flatten(),
            self.cwndFrame["cwnd"].values.flatten(),
            pen="m",
            symbol="o",
            symbolPen="m",
            symbolBrush="m",
            symbolSize=5,
        )
        wMaxItem = pg.PlotCurveItem(
            self.wMaxFrame["time"].values.flatten(),
            self.wMaxFrame["wMax"].values.flatten(),
            pen="k",
        )

        view1.addItem(spinItem)
        view1.addItem(spinItem_dot)

        view2.addItem(throughputItem)
        view2.addItem(throughputItem_dot)

        view3.addItem(lossItem0)
        view3.addItem(lossItem1)
        view3.addItem(lossItem2)

        view4.addItem(cwndItem)
        view4.addItem(cwndItem_dot)

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
        self.spinFrame, self.throughputFrame, self.lostFrame, self.cwndFrame, _ = loadData(
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

    args = parser.parse_args()

    app = QtWidgets.QApplication([])
    mainProgram = MainWindow(args)
    app.exec()

if __name__ == "__main__":
    main()
