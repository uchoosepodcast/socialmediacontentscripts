import re

with open('gui.py', 'r') as f:
    content = f.read()

collapsible_class = """
class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None):
        super(CollapsibleBox, self).__init__(parent)

        self.toggle_button = QPushButton(title)
        self.toggle_button.setStyleSheet("text-align: left; padding: 5px; font-weight: bold; border: none; background-color: transparent;")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.clicked.connect(self.on_pressed)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

    def on_pressed(self):
        checked = self.toggle_button.isChecked()
        self.content_area.setVisible(checked)
"""

# Insert CollapsibleBox class before MainWindow
content = content.replace("class MainWindow(QMainWindow):", collapsible_class + "\nclass MainWindow(QMainWindow):")

# Replace QGroupBox with CollapsibleBox
content = content.replace('QGroupBox("API Credentials")', 'CollapsibleBox("▶ API Credentials")')
content = content.replace('QGroupBox("Source Priorities")', 'CollapsibleBox("▶ Source Priorities")')
content = content.replace('QGroupBox("Search Constraints")', 'CollapsibleBox("▶ Search Constraints")')
content = content.replace('QGroupBox("Brand Assets")', 'CollapsibleBox("▶ Brand Assets")')
content = content.replace('QGroupBox("Platforms")', 'CollapsibleBox("▶ Platforms")')

# Replace .setLayout(...) with .content_layout.addLayout(...) or similar
content = content.replace('cred_group.setLayout(cred_layout)', 'cred_group.content_layout.addLayout(cred_layout)')
content = content.replace('source_group.setLayout(source_layout)', 'source_group.content_layout.addLayout(source_layout)')
content = content.replace('search_group.setLayout(search_layout)', 'search_group.content_layout.addLayout(search_layout)')
content = content.replace('brand_group.setLayout(brand_layout)', 'brand_group.content_layout.addLayout(brand_layout)')
content = content.replace('platform_group.setLayout(platform_layout)', 'platform_group.content_layout.addLayout(platform_layout)')

with open('gui.py', 'w') as f:
    f.write(content)
