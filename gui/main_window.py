from PySide6.QtWidgets import (
    QMainWindow,
    QPushButton,
    QFileDialog,
    QWidget,
    QVBoxLayout,
    QTextEdit
)

import pyqtgraph as pg

from core.ab1_reader import read_ab1


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("SangerFlow v0.3")
        self.resize(900, 600)

        widget = QWidget()
        self.setCentralWidget(widget)

        layout = QVBoxLayout()
        widget.setLayout(layout)

        self.open_button = QPushButton("Open AB1")
        self.open_button.clicked.connect(self.open_file)

        layout.addWidget(self.open_button)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True)

        layout.addWidget(self.plot)

        self.sequence_box = QTextEdit()
        self.sequence_box.setReadOnly(True)

        layout.addWidget(self.sequence_box)


    def open_file(self):

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open AB1 file",
            "",
            "AB1 files (*.ab1)"
        )

        if filepath:

            result = read_ab1(filepath)

            self.plot.clear()

            traces = result["traces"]

            colors = {
                "A": "green",
                "C": "blue",
                "G": "black",
                "T": "red"
            }

            for base in ["A", "C", "G", "T"]:

                self.plot.plot(
                    traces[base],
                    pen=colors[base],
                    name=base
                )

            sequence = result["sequence"]
            positions = result["positions"]

            for base, x in zip(sequence, positions):

                text = pg.TextItem(
                    base,
                    color=colors.get(base, "black")
                )

                text.setPos(x, 1000)

                self.plot.addItem(text)


            self.sequence_box.setText(
                result["sequence"]
            )