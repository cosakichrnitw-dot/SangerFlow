import sys

from PySide6.QtWidgets import QApplication


app = QApplication(sys.argv)

from gui.main_window import MainWindow


window = MainWindow()
window.show()

sys.exit(app.exec())
