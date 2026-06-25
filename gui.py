import sys
import os
import logging
import requests
import tempfile
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QCheckBox, QComboBox, QGroupBox, QSpinBox,
                             QTextEdit, QProgressBar, QFileDialog, QTabWidget,
                             QScrollArea, QListWidget, QDialog, QDialogButtonBox,
                             QToolButton, QAbstractItemView, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon

from core.config import AppConfig, RunConfig, PlatformConfig, IssueMetadata
from core.data_fetcher import PipelineFetcher
from core.image_renderer import ImageRenderer

logger = logging.getLogger(__name__)

def download_image(url: str) -> str:
    if not url: return None
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        fd, temp_path = tempfile.mkstemp(suffix='.jpg')
        with os.fdopen(fd, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return temp_path
    except Exception as e:
        logger.error(f"Failed to download image {url}: {e}")
        return None

class FetchWorker(QThread):
    progress = pyqtSignal(int, str)
    log_msg = pyqtSignal(str)
    ask_user_volume = pyqtSignal(list)
    fetch_finished = pyqtSignal(list)

    def __init__(self, app_config: AppConfig, run_config: RunConfig):
        super().__init__()
        self.app_config = app_config
        self.run_config = run_config
        self.user_volume_choice = None
        self.waiting_for_user = False

    def run(self):
        try:
            self.log_msg.emit("Starting issue fetch...")
            fetcher = PipelineFetcher(self.app_config, self.run_config.sources_priority)

            volume_id = self.run_config.volume_id
            if not volume_id:
                self.progress.emit(10, "Searching for volume ID...")
                candidates = fetcher.find_volume_id(self.run_config.title, self.run_config.publisher, self.run_config.start_year)

                if not candidates:
                    self.log_msg.emit("No volume candidates found.")
                    self.fetch_finished.emit([])
                    return

                if len(candidates) == 1:
                    volume_id = candidates[0]['id']
                    self.log_msg.emit(f"Auto-selected volume: {candidates[0]['name']}")
                else:
                    self.waiting_for_user = True
                    self.ask_user_volume.emit(candidates)
                    while self.waiting_for_user:
                        self.msleep(100)

                    if not self.user_volume_choice:
                        self.log_msg.emit("User cancelled volume selection.")
                        self.fetch_finished.emit([])
                        return
                    volume_id = self.user_volume_choice

            self.run_config.volume_id = volume_id

            self.progress.emit(50, "Fetching issues...")
            start_date = f"{self.run_config.start_year}-01-01"
            end_date = f"{self.run_config.end_year}-12-31"

            issues = fetcher.fetch_issues(volume_id, start_date, end_date, self.run_config.publisher)
            if not issues:
                self.log_msg.emit("No issues found in the given date range.")
                self.fetch_finished.emit([])
                return

            self.log_msg.emit(f"Fetched {len(issues)} issues.")
            self.progress.emit(100, "Fetch complete!")
            self.fetch_finished.emit(issues)

        except Exception as e:
            self.log_msg.emit(f"Error during fetch: {e}")
            self.fetch_finished.emit([])


class RenderWorker(QThread):
    progress = pyqtSignal(int, str)
    log_msg = pyqtSignal(str)
    preview_ready = pyqtSignal(str, str)
    batch_finished = pyqtSignal(bool)

    def __init__(self, run_config: RunConfig, issues: list, is_preview=False, target_issue=None):
        super().__init__()
        self.run_config = run_config
        self.issues = [target_issue] if target_issue else issues
        self.is_preview = is_preview

    def run(self):
        renderer = ImageRenderer()
        total = len(self.issues) * len(self.run_config.platforms)
        completed = 0

        try:
            for platform in self.run_config.platforms:
                p_config = PlatformConfig(
                    name=platform, directory_prefix=platform.lower()[:3],
                    social_post_filename_prefix=platform.lower()[:3],
                    social_post_filename_suffix="_post.jpg",
                    description_word_limit=100
                )

                for issue in self.issues:
                    self.progress.emit(int((completed / total) * 100), f"Rendering {issue.name or 'Issue'} #{issue.issue_number} for {platform}")

                    cover_path = None
                    if issue.image_url:
                        self.log_msg.emit(f"Downloading cover for issue #{issue.issue_number}...")
                        cover_path = download_image(issue.image_url)

                    if not cover_path:
                        self.log_msg.emit(f"No cover image available for issue #{issue.issue_number}")
                        from PIL import Image, ImageDraw
                        img = Image.new('RGB', (600, 900), color=(100, 100, 150))
                        d = ImageDraw.Draw(img)
                        d.text((50,50), "NO COVER", fill=(255,255,255))
                        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tf:
                            cover_path = tf.name
                        img.save(cover_path)

                    out_path = f"output/{platform}/{issue.issue_number}_social.jpg"
                    if self.is_preview:
                        with tempfile.NamedTemporaryFile(suffix='_preview.jpg', delete=False) as tf:
                            out_path = tf.name

                    success = renderer.render_social_image(self.run_config, p_config, issue, cover_path, out_path)

                    if success:
                        self.log_msg.emit(f"Created {out_path}")
                        if self.is_preview:
                            self.preview_ready.emit(f"Issue #{issue.issue_number} ({platform})", out_path)
                    else:
                        self.log_msg.emit(f"Failed to create {out_path}")

                    try:
                        os.remove(cover_path)
                    except:
                        pass

                    completed += 1

            self.progress.emit(100, "Rendering complete!")
            self.batch_finished.emit(True)

        except Exception as e:
            self.log_msg.emit(f"Error during rendering: {e}")
            self.batch_finished.emit(False)


class VolumeSelectDialog(QDialog):
    def __init__(self, candidates, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Volume")
        self.selected_id = None

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()

        for cand in candidates:
            self.list_widget.addItem(f"{cand['name']} (ID: {cand['id']}, Year: {cand['start_year']}, Publisher: {cand['publisher']})")

        layout.addWidget(QLabel("Multiple volumes found. Please select one:"))
        layout.addWidget(self.list_widget)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_selected_id(self):
        idx = self.list_widget.currentRow()
        if idx >= 0:
            return idx
        return -1


from PyQt6.QtCore import pyqtSignal, QObject

class LogSignals(QObject):
    log_msg = pyqtSignal(str)

class QTextEditLogger(logging.Handler):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.signals = LogSignals()
        self.signals.log_msg.connect(self.widget.append)

    def emit(self, record):
        msg = self.format(record)
        self.signals.log_msg.emit(msg)


class PasswordEdit(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.line_edit = QLineEdit()
        self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.toggle_btn = QToolButton()
        self.toggle_btn.setText("👁")
        self.toggle_btn.clicked.connect(self.toggle_visibility)
        layout.addWidget(self.line_edit)
        layout.addWidget(self.toggle_btn)

    def toggle_visibility(self):
        if self.line_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def text(self):
        return self.line_edit.text()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Comic Social Creator")
        self.resize(1200, 800)
        self.issues = []

        # Main Layout (Splitter)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Left Panel (Controls)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_panel)
        splitter.addWidget(left_scroll)

        # Credentials
        cred_group = QGroupBox("API Credentials")
        cred_layout = QVBoxLayout()
        self.vine_key = PasswordEdit()
        self.marvel_pub = PasswordEdit()
        self.marvel_priv = PasswordEdit()
        self.mistral_key = PasswordEdit()

        cred_layout.addWidget(QLabel("Comic Vine API Key:"))
        cred_layout.addWidget(self.vine_key)
        cred_layout.addWidget(QLabel("Marvel Public Key:"))
        cred_layout.addWidget(self.marvel_pub)
        cred_layout.addWidget(QLabel("Marvel Private Key:"))
        cred_layout.addWidget(self.marvel_priv)
        cred_layout.addWidget(QLabel("Mistral API Key:"))
        cred_layout.addWidget(self.mistral_key)
        cred_group.setLayout(cred_layout)
        left_layout.addWidget(cred_group)

        # Source Priority
        source_group = QGroupBox("Source Priorities")
        source_layout = QVBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItems([
            "ComicVine -> Marvel -> GoogleBooks",
            "Marvel -> ComicVine -> GoogleBooks",
            "ComicVine Only"
        ])
        source_layout.addWidget(self.source_combo)
        source_group.setLayout(source_layout)
        left_layout.addWidget(source_group)

        # Search Constraints
        search_group = QGroupBox("Search Constraints")
        search_layout = QVBoxLayout()
        self.title_input = QLineEdit()
        self.publisher_input = QLineEdit()
        self.volume_input = QLineEdit()
        self.start_year = QSpinBox()
        self.start_year.setRange(1900, 2100)
        self.start_year.setValue(2020)
        self.end_year = QSpinBox()
        self.end_year.setRange(1900, 2100)
        self.end_year.setValue(2023)

        search_layout.addWidget(QLabel("Title:"))
        search_layout.addWidget(self.title_input)
        search_layout.addWidget(QLabel("Publisher:"))
        search_layout.addWidget(self.publisher_input)
        search_layout.addWidget(QLabel("Volume Number:"))
        search_layout.addWidget(self.volume_input)
        search_layout.addWidget(QLabel("Start Year:"))
        search_layout.addWidget(self.start_year)
        search_layout.addWidget(QLabel("End Year:"))
        search_layout.addWidget(self.end_year)
        search_group.setLayout(search_layout)
        left_layout.addWidget(search_group)

        # Brand Assets
        brand_group = QGroupBox("Brand Assets")
        brand_layout = QVBoxLayout()
        self.footer_input = QLineEdit()
        self.footer_input.setMaxLength(50)

        logo_layout = QHBoxLayout()
        self.logo_path_lbl = QLabel("No logo selected")
        self.logo_btn = QPushButton("Browse")
        self.logo_btn.clicked.connect(self.browse_logo)
        logo_layout.addWidget(self.logo_path_lbl)
        logo_layout.addWidget(self.logo_btn)

        brand_layout.addWidget(QLabel("Footer Text (max 50 chars):"))
        brand_layout.addWidget(self.footer_input)
        brand_layout.addWidget(QLabel("Custom Logo:"))
        brand_layout.addLayout(logo_layout)
        brand_group.setLayout(brand_layout)
        left_layout.addWidget(brand_group)

        # Platforms
        plat_group = QGroupBox("Platforms")
        plat_layout = QVBoxLayout()
        self.cb_ig = QCheckBox("Instagram")
        self.cb_fb = QCheckBox("Facebook")
        self.cb_tw = QCheckBox("Twitter (X)")
        self.cb_ig.setChecked(True)
        plat_layout.addWidget(self.cb_ig)
        plat_layout.addWidget(self.cb_fb)
        plat_layout.addWidget(self.cb_tw)
        plat_group.setLayout(plat_layout)
        left_layout.addWidget(plat_group)

        self.btn_fetch = QPushButton("1. Fetch Issues")
        self.btn_fetch.clicked.connect(self.start_fetch)
        left_layout.addWidget(self.btn_fetch)

        left_layout.addStretch()

        # Center Panel (List of Issues)
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.addWidget(QLabel("Fetched Issues:"))
        self.issue_list = QListWidget()
        self.issue_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.issue_list.itemSelectionChanged.connect(self.preview_selected_issue)
        center_layout.addWidget(self.issue_list)

        self.btn_export = QPushButton("2. Batch Export All")
        self.btn_export.clicked.connect(self.start_batch_export)
        self.btn_export.setEnabled(False)
        center_layout.addWidget(self.btn_export)

        splitter.addWidget(center_panel)

        # Right Panel (Preview & Logs)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.tabs = QTabWidget()

        # Preview Tab
        self.preview_scroll = QScrollArea()
        self.preview_label = QLabel("Select an issue to preview.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setWidgetResizable(True)
        self.tabs.addTab(self.preview_scroll, "WYSIWYG Preview")

        # Logs Tab
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.tabs.addTab(self.log_text, "Console Logs")

        right_layout.addWidget(self.tabs)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        right_layout.addWidget(self.progress_bar)

        splitter.addWidget(right_panel)

        # Ratios
        splitter.setSizes([300, 300, 600])

        # Setup custom logger
        log_handler = QTextEditLogger(self.log_text)
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.logo_path = None

    def browse_logo(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Select Logo', '', 'Images (*.png *.jpg *.jpeg)')
        if fname:
            self.logo_path = fname
            self.logo_path_lbl.setText(os.path.basename(fname))

    def get_priorities(self):
        idx = self.source_combo.currentIndex()
        if idx == 0: return ["comicvine", "marvel", "googlebooks"]
        if idx == 1: return ["marvel", "comicvine", "googlebooks"]
        return ["comicvine"]

    def start_fetch(self):
        if not self.vine_key.text() or not self.title_input.text() or not self.publisher_input.text():
            logging.error("Comic Vine API Key, Title, and Publisher are required.")
            return

        app_config = AppConfig(
            comic_vine_api_key=self.vine_key.text(),
            marvel_public_key=self.marvel_pub.text(),
            marvel_private_key=self.marvel_priv.text(),
            mistral_api_key=self.mistral_key.text()
        )

        run_config = RunConfig(
            title=self.title_input.text(),
            publisher=self.publisher_input.text(),
            volume_number=self.volume_input.text(),
            start_year=self.start_year.value(),
            end_year=self.end_year.value(),
            sources_priority=self.get_priorities()
        )

        self.btn_fetch.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.issue_list.clear()
        self.issues = []
        self.progress_bar.setValue(0)
        self.log_text.clear()

        self.fetch_worker = FetchWorker(app_config, run_config)
        self.fetch_worker.progress.connect(self.update_progress)
        self.fetch_worker.log_msg.connect(self.append_log)
        self.fetch_worker.ask_user_volume.connect(self.prompt_volume_selection)
        self.fetch_worker.fetch_finished.connect(self.on_fetch_finished)
        self.fetch_worker.start()

    def update_progress(self, value, msg):
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(f"%p% - {msg}")

    def append_log(self, msg):
        logging.info(msg)

    def prompt_volume_selection(self, candidates):
        dialog = VolumeSelectDialog(candidates, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            idx = dialog.get_selected_id()
            if idx >= 0:
                self.fetch_worker.user_volume_choice = candidates[idx]['id']
            else:
                self.fetch_worker.user_volume_choice = None
        else:
            self.fetch_worker.user_volume_choice = None

        self.fetch_worker.waiting_for_user = False

    def on_fetch_finished(self, issues):
        self.btn_fetch.setEnabled(True)
        self.issues = issues
        if issues:
            self.btn_export.setEnabled(True)
            for issue in issues:
                self.issue_list.addItem(f"Issue #{issue.issue_number} - {issue.name or 'Untitled'} ({issue.cover_date})")
        else:
            self.append_log("Fetch completed with 0 issues.")

    def preview_selected_issue(self):
        idx = self.issue_list.currentRow()
        if idx < 0 or idx >= len(self.issues): return

        issue = self.issues[idx]

        platforms = []
        if self.cb_ig.isChecked(): platforms.append("Instagram")
        if self.cb_fb.isChecked(): platforms.append("Facebook")
        if self.cb_tw.isChecked(): platforms.append("Twitter")

        if not platforms: return

        run_config = RunConfig(
            title=self.title_input.text(),
            publisher=self.publisher_input.text(),
            volume_number=self.volume_input.text(),
            start_year=self.start_year.value(),
            end_year=self.end_year.value(),
            platforms=platforms[:1], # Just preview the first selected platform
            custom_footer_text=self.footer_input.text(),
            logo_image_path=self.logo_path
        )

        self.progress_bar.setValue(0)
        self.render_worker = RenderWorker(run_config, [], is_preview=True, target_issue=issue)
        self.render_worker.progress.connect(self.update_progress)
        self.render_worker.log_msg.connect(self.append_log)
        self.render_worker.preview_ready.connect(self.show_preview)
        self.render_worker.start()

    def show_preview(self, title, path):
        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(self.preview_scroll.width() - 20,
                                       self.preview_scroll.height() - 20,
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                self.preview_label.setPixmap(scaled)

    def start_batch_export(self):
        if not self.issues: return

        platforms = []
        if self.cb_ig.isChecked(): platforms.append("Instagram")
        if self.cb_fb.isChecked(): platforms.append("Facebook")
        if self.cb_tw.isChecked(): platforms.append("Twitter")

        if not platforms:
            logging.error("Select at least one platform.")
            return

        run_config = RunConfig(
            title=self.title_input.text(),
            publisher=self.publisher_input.text(),
            volume_number=self.volume_input.text(),
            start_year=self.start_year.value(),
            end_year=self.end_year.value(),
            platforms=platforms,
            custom_footer_text=self.footer_input.text(),
            logo_image_path=self.logo_path
        )

        self.btn_export.setEnabled(False)
        self.btn_fetch.setEnabled(False)
        self.progress_bar.setValue(0)

        self.render_worker = RenderWorker(run_config, self.issues, is_preview=False)
        self.render_worker.progress.connect(self.update_progress)
        self.render_worker.log_msg.connect(self.append_log)
        self.render_worker.batch_finished.connect(self.on_batch_finished)
        self.render_worker.start()

    def on_batch_finished(self, success):
        self.btn_export.setEnabled(True)
        self.btn_fetch.setEnabled(True)
        if success:
            logging.info("Batch export completed successfully.")
        else:
            logging.error("Batch export encountered errors.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
