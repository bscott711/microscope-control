# src/microscope/initial_testing/superqt_test.py

from qtpy.QtWidgets import QApplication, QPushButton
from superqt import QIconifyIcon

app = QApplication([])

button = QPushButton(QIconifyIcon("mdi:home"), "Home")

button.show()
app.exec_()
