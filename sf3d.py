from mpl_toolkits.mplot3d import axes3d
import matplotlib.pyplot as plt
import pandas as pd

def loadData():
    spinStatFrame = pd.read_csv("stats.csv")
    return spinStatFrame

def main():
    spinStatFrame = loadData()
    fixedFrame = spinStatFrame[(spinStatFrame["bandwidth"] == 17) & (spinStatFrame["lossRate"] <= 10)]
    # fixedFrame = spinStatFrame[(spinStatFrame["bandwidth"] == 17)]
    # fixedFrame = spinStatFrame

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.set_xlabel('Loss Rate(%)')
    ax.set_ylabel('Delay(ms)')
    ax.set_zlabel('Spin Frequency(Hz)')

    ax.scatter(fixedFrame['lossRate'].values.flatten(), fixedFrame['delay'].values.flatten(), fixedFrame['spinFreq'].values.flatten())

    plt.show()


if __name__ == "__main__":
    main()