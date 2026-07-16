import sys

from PySide6.QtWidgets import QApplication, QLabel, QWidget


def main():
    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("SangerFlow")
    window.resize(800, 600)

    label = QLabel("Hello, SangerFlow!", parent=window)
    label.move(300, 280)

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()