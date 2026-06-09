import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QGroupBox, QLabel
from PyQt6.QtCore import Qt

class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None):
        super(CollapsibleBox, self).__init__(parent)

        self.toggle_button = QPushButton(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.clicked.connect(self.on_pressed)

        self.content_area = QWidget()
        self.content_area.setVisible(False)
        self.content_layout = QVBoxLayout(self.content_area)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

    def on_pressed(self):
        checked = self.toggle_button.isChecked()
        self.content_area.setVisible(checked)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        box1 = CollapsibleBox("Box 1")
        box1.content_layout.addWidget(QLabel("Content 1"))
        layout.addWidget(box1)

        box2 = CollapsibleBox("Box 2")
        box2.content_layout.addWidget(QLabel("Content 2"))
        layout.addWidget(box2)

        layout.addStretch()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
