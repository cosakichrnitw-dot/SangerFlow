from PySide6.QtWidgets import QApplication, QWidget


app = QApplication([])


window = QWidget()

window.setWindowTitle(
    "SangerFlow Test"
)

window.resize(
    400,
    300
)


window.show()


app.exec()
