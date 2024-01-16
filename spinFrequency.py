import numpy as np
import pandas as pd

import argparse

import pyqtgraph as pg
from PyQt5 import QtWidgets

def loadData():
    spinStatFrame = pd.read_csv("stats.csv")
    return spinStatFrame

class MainWindow(QtWidgets.QMainWindow): # main view
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.spinStatFrame = loadData()
        self.drawGraph()
        self.show()
    
    def putPlot(self, row, col, text, x, x_unit, rowSpan = 1, colSpan = 1, y = "Spin Frequency", y_unit = "Hz"):
        plotItem1 = pg.PlotItem()
        self.view1 = plotItem1.getViewBox()
        self.layoutWidget.addItem(plotItem1, row, col, rowSpan, colSpan)
        plotItem1.setLabel("left", y, units=y_unit)
        plotItem1.setLabel("bottom", x, units=x_unit)
        self.text = pg.LabelItem(text=text)
        self.text.setParentItem(plotItem1)
        self.text.anchor(itemPos = (0.5, 0.1), parentPos = (0.5, 0.1))

    def drawGraph(self):

        self.layoutWidget = pg.GraphicsLayoutWidget()
        self.layoutWidget.setBackground("w")
        self.setCentralWidget(self.layoutWidget)

        self.spinStatFrame["bandwidth"] *= 1000000
        self.spinStatFrame["delay"] /= 1000

        self.xAxes = {0: "lossRate", 1: "bandwidth", 2: "delay"}
        self.units = {"lossRate": "%", "bandwidth": "bps", "delay": "s", "spinFreq": "Hz"}

        FIXED_BANDWIDTH = 17000000
        FIXED_LOSSRATE = 0.45
        FIXED_DELAY = 0.033

        textSet = {0: f"Bandwidth: {FIXED_BANDWIDTH/1000000}Mbps\n Delay: {FIXED_DELAY*1000}ms",
                1: f"Loss Rate: {FIXED_LOSSRATE}%\n Delay: {FIXED_DELAY*1000}ms",
                2: f"Bandwidth: {FIXED_BANDWIDTH/1000000}Mbps\n Loss Rate: {FIXED_LOSSRATE}%"}

        self.spinStatFrame["avgThroughput"] *= 1000000

        for i in range(0, 3):
            self.putPlot(i%2, i//2, textSet[i], self.xAxes[i], self.units[self.xAxes[i]])

            # plotItem1.getAxis("bottom").setTicks([[(lossRate, f"{lossRate:.2f}") for lossRate in self.spinStatFrame["lossRate"].values.flatten()]])
            # plotItem1.axis_left = plotItem1.getAxis("left")
            # pgLayout.addItem(plotItem1.axis_left, 1, 2+i*3, 1, 1)

            if i == 0:
                self.fixedFrame = self.spinStatFrame[(self.spinStatFrame["bandwidth"] == FIXED_BANDWIDTH) & (self.spinStatFrame["delay"] == FIXED_DELAY)]
            elif i == 1:
                self.fixedFrame = self.spinStatFrame[(self.spinStatFrame["lossRate"] == FIXED_LOSSRATE) & (self.spinStatFrame["delay"] == FIXED_DELAY)]
            elif i == 2:
                self.fixedFrame = self.spinStatFrame[(self.spinStatFrame["bandwidth"] == FIXED_BANDWIDTH) & (self.spinStatFrame["lossRate"] == FIXED_LOSSRATE)]

            self.view1.addItem(pg.ScatterPlotItem(self.fixedFrame[self.xAxes[i]].values.flatten(), self.fixedFrame["spinFreq"].values.flatten(), pen="b"))

        self.putPlot(1, 1, f"Bandwidth: {FIXED_BANDWIDTH/1000000}Mbps\n Loss Rate: 0%", self.xAxes[2], self.units[self.xAxes[2]], 1, 1)
        self.fixedFrame = self.spinStatFrame[(self.spinStatFrame["bandwidth"] == FIXED_BANDWIDTH) & (self.spinStatFrame["lossRate"] == 0)]
        self.view1.addItem(pg.ScatterPlotItem(self.fixedFrame[self.xAxes[2]].values.flatten(), self.fixedFrame["spinFreq"].values.flatten(), pen="b"))

        self.fixedFrame = self.spinStatFrame[(self.spinStatFrame["bandwidth"] == FIXED_BANDWIDTH) & (((self.spinStatFrame["lossRate"] > FIXED_LOSSRATE) & (self.spinStatFrame["delay"] == FIXED_DELAY)) | ((self.spinStatFrame["lossRate"] == 0) & (self.spinStatFrame["delay"] > FIXED_DELAY)))]
        print(self.fixedFrame)
        self.boxFrame = pd.DataFrame(columns=["spinFreq", "avgThroughput", "top", "bottom"])
        for spinFreq in self.fixedFrame["spinFreq"].values.flatten():
            avgPerSF = self.fixedFrame.loc[abs(self.fixedFrame["spinFreq"] - int(spinFreq)) < 0.5]["avgThroughput"].mean()
            maxPerSF = self.fixedFrame.loc[abs(self.fixedFrame["spinFreq"] - int(spinFreq)) < 0.5]["avgThroughput"].max()
            minPerSF = self.fixedFrame.loc[abs(self.fixedFrame["spinFreq"] - int(spinFreq)) < 0.5]["avgThroughput"].min()
            if self.boxFrame.loc[self.boxFrame["spinFreq"] == int(spinFreq)].empty:
                self.boxFrame.loc[len(self.boxFrame.index)] = [int(spinFreq), avgPerSF, maxPerSF-avgPerSF, avgPerSF-minPerSF]

        self.boxFrame.sort_values(by=["spinFreq"], inplace=True)
        print(self.boxFrame)

        self.putPlot(2, 0, "", "spinFreq", self.units["spinFreq"], y = "Avg. Throughput", y_unit = "bps", rowSpan = 1, colSpan = 2)
        error = pg.ErrorBarItem(beam=0.3, pen = "r")
        error.setData(x = self.boxFrame["spinFreq"].values.flatten(), y = self.boxFrame["avgThroughput"].values.flatten(), top = self.boxFrame["top"].values.flatten(), bottom = self.boxFrame["bottom"].values.flatten(), pen="b")
        self.view1.addItem(pg.PlotCurveItem(x=self.boxFrame["spinFreq"].values.flatten(), y=self.boxFrame["avgThroughput"].values.flatten(), pen = "g", symbol = "o"))
        self.view1.addItem(pg.ScatterPlotItem(x=self.boxFrame["spinFreq"].values.flatten(), y=self.boxFrame["avgThroughput"].values.flatten(), pen = "r", brush = "r", symbol = "o"))
        self.view1.addItem(pg.ScatterPlotItem(x=self.fixedFrame["spinFreq"].values.flatten(), y=self.fixedFrame["avgThroughput"].values.flatten(), pen = "b", symbol = "o"))
        self.view1.addItem(error)


def main():
    parser = argparse.ArgumentParser(description="Show Spin Frequency")
    parser.add_argument("-x", "--x", type=str, default="loss", help="x axis", required=False)
    args = parser.parse_args()

    app = QtWidgets.QApplication([])
    mainProgram = MainWindow(args)
    app.exec()

if __name__ == "__main__":
    main()
