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

    def drawGraph(self):

        layoutWidget = pg.GraphicsLayoutWidget()
        layoutWidget.setBackground("w")
        self.setCentralWidget(layoutWidget)

        self.spinStatFrame["bandwidth"] *= 1000000
        self.spinStatFrame["delay"] /= 1000

        xAxes = {0: "lossRate", 1: "bandwidth", 2: "delay"}
        units = {"lossRate": "%", "bandwidth": "bps", "delay": "s"}

        FIXED_BANDWIDTH = 17000000
        FIXED_LOSSRATE = 0.45
        FIXED_DELAY = 0.033

        for i in range(0, 3):
            plotItem1 = pg.PlotItem()
            view1 = plotItem1.getViewBox()
            layoutWidget.addItem(plotItem1, 1, 3+i*3, 1, 1)
            pgLayout = layoutWidget
            plotItem1.setLabel("left", "Spin Frequency", units="Hz")
            plotItem1.setLabel("bottom", xAxes[i], units=units[xAxes[i]])

            # plotItem1.getAxis("bottom").setTicks([[(lossRate, f"{lossRate:.2f}") for lossRate in self.spinStatFrame["lossRate"].values.flatten()]])

            # plotItem1.axis_left = plotItem1.getAxis("left")
            # pgLayout.addItem(plotItem1.axis_left, 1, 2+i*3, 1, 1)

            if i == 0:
                self.fixedFrame = self.spinStatFrame[(self.spinStatFrame["bandwidth"] == FIXED_BANDWIDTH) & (self.spinStatFrame["delay"] == FIXED_DELAY)]
                self.text = pg.LabelItem(text=f"Bandwidth: {FIXED_BANDWIDTH/1000000}Mbps\n Delay: {FIXED_DELAY*1000}ms")
                self.text.setParentItem(plotItem1)
                self.text.anchor(itemPos = (0, 0), parentPos = (0, 0))
            elif i == 1:
                self.fixedFrame = self.spinStatFrame[(self.spinStatFrame["lossRate"] == FIXED_LOSSRATE) & (self.spinStatFrame["delay"] == FIXED_DELAY)]
                self.text = pg.LabelItem(text=f"Loss Rate: {FIXED_LOSSRATE}%\n Delay: {FIXED_DELAY*1000}ms")
                self.text.setParentItem(plotItem1)
                self.text.anchor(itemPos = (0, 0), parentPos = (0, 0))
            elif i == 2:
                self.fixedFrame = self.spinStatFrame[(self.spinStatFrame["bandwidth"] == FIXED_BANDWIDTH) & (self.spinStatFrame["lossRate"] == FIXED_LOSSRATE)]
                self.text = pg.LabelItem(text=f"Bandwidth: {FIXED_BANDWIDTH/1000000}Mbps\n Loss Rate: {FIXED_LOSSRATE}%")
                self.text.setParentItem(plotItem1)
                self.text.anchor(itemPos = (0, 0), parentPos = (0, 0))

            view1.addItem(pg.ScatterPlotItem(self.fixedFrame[xAxes[i]].values.flatten(), self.fixedFrame["spinFreq"].values.flatten(), pen="b"))

def main():
    parser = argparse.ArgumentParser(description="Show Spin Frequency")
    parser.add_argument("-x", "--x", type=str, default="loss", help="x axis", required=False)
    args = parser.parse_args()

    app = QtWidgets.QApplication([])
    mainProgram = MainWindow(args)
    app.exec()

if __name__ == "__main__":
    main()
