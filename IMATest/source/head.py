import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

import sys
import os
import json
import logging
import re
import traceback
import shutil
import chardet
import platform

from collections import OrderedDict
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QObject
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton,
                             QHBoxLayout, QSpacerItem, QSizePolicy, QRadioButton, QFileDialog)

# Enable or disable logging
ENABLE_LOGGING = True

# ANSI escape code pattern
ANSI_ESCAPE = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')

# 로그 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


def log_info(level, *args):
    """로그 메시지를 주어진 레벨로 출력"""
    if ENABLE_LOGGING:
        message = " ".join(map(str, args))

        if level.lower() == "info":
            logging.info(message)
        elif level.lower() == "warning":
            logging.warning(message)
        elif level.lower() == "error":
            logging.error(message)
        elif level.lower() == "critical":
            logging.critical(message)
        else:
            logging.debug(message)  # 기본값: DEBUG


def load_module_func(module_name):
    mod = __import__(f"{module_name}", fromlist=[module_name])
    return mod


def check_environment():
    env = ''
    system = platform.system()
    if system == "Windows":
        # Windows인지 확인, WSL 포함
        if "microsoft" in platform.version().lower() or "microsoft" in platform.release().lower():
            env = "WSL"  # Windows Subsystem for Linux
        env = "Windows"  # 순수 Windows
    elif system == "Linux":
        # Linux에서 WSL인지 확인
        try:
            with open("/proc/version", "r") as f:
                version_info = f.read().lower()
            if "microsoft" in version_info:
                env = "WSL"  # WSL 환경
        except FileNotFoundError:
            pass
        env = "Linux"  # 순수 Linux
    else:
        env = "Other"  # macOS 또는 기타 운영체제

    return env


def handle_exception(e):
    traceback.print_exc()
    sys.exit(1)


class EmittingStream(QObject):
    textWritten = pyqtSignal(str)

    def write(self, text):
        self.textWritten.emit(str(text))

    def flush(self):
        pass


class ProgressDialog(QDialog):
    progress_stop_signal = pyqtSignal()

    def __init__(self, message, modal=True, show_close_button=False, parent=None,
                 remove_percent_sign=False, auto_increment=False):
        super().__init__(parent)
        self.setWindowTitle(message)
        self.remove_percent_sign = remove_percent_sign
        self.auto_increment = auto_increment
        self.count = 0
        self.max_count = 100

        self.setModal(modal) if modal else self.setWindowModality(QtCore.Qt.NonModal)
        self.resize(700, 100)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMaximum(self.max_count)
        if self.remove_percent_sign:
            self.progress_bar.setFormat("")

        self.label = QLabel("", self)
        self.radio_button = QRadioButton("", self)
        self.close_button = QPushButton("Close", self)
        self.close_button.setVisible(show_close_button)

        # Layout configuration
        h_layout = QHBoxLayout()
        h_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        h_layout.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.label)
        layout.addWidget(self.radio_button)
        layout.addLayout(h_layout)
        self.setLayout(layout)

        # Timer for blinking radio button
        self.timer = QTimer(self)
        self.radio_state = False
        self.timer.timeout.connect(self.toggle_radio_button)
        self.timer.start(100)

        # Signals and Slots
        self.close_button.clicked.connect(self.close)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint & ~Qt.WindowContextHelpButtonHint)

    def set_progress_max(self, max_value):
        # log_info("info", "max cnt: ", max_value)
        self.max_count = max_value
        self.progress_bar.setMaximum(max_value)

    def update_progress(self, value):
        self.progress_bar.setValue(int(value))

    def update_text(self, text):
        self.label.setText(text)

    def show_progress(self):
        super().exec_() if self.isModal() else self.show()

    def toggle_radio_button(self):
        if self.auto_increment:
            self.count += 1
            self.update_progress(self.count % self.max_count)

        # self.radio_state가 없을 경우 기본값 설정
        if not hasattr(self, "radio_state"):
            self.radio_state = False

        self.radio_button.setStyleSheet(f"""
            QRadioButton::indicator {{
                width: 12px;
                height: 12px;
                background-color: {'red' if self.radio_state else 'blue'};
                border-radius: 5px;
            }}
        """)
        self.radio_state = not self.radio_state

    def closeEvent(self, event):
        log_info("info", "popup closedEvent")

        # self.timer가 존재하는지 확인 후 stop()
        if hasattr(self, "timer") and self.timer is not None:
            self.timer.stop()

        # progress_stop_signal이 존재하는지 확인 후 emit()
        if hasattr(self, "progress_stop_signal"):
            self.progress_stop_signal.emit()

        event.accept()


class FileManager:
    @staticmethod
    def is_directory(path):
        return os.path.isdir(path)

    @staticmethod
    def is_file(path):
        return os.path.isfile(path)

    @staticmethod
    def save_json(file_path, data, use_encoding=False):
        try:
            if not file_path.endswith(".json"):
                file_path += ".json"
            encoding = FileManager.detect_encoding(file_path) if use_encoding else "utf-8"

            with open(file_path, "w", encoding=encoding) as f:
                json.dump(data, f, indent=4, ensure_ascii=False, sort_keys=False)
            return True
        except Exception as e:
            handle_exception(e)

    @staticmethod
    def load_json(file_path, use_encoding=False):
        try:
            encoding = FileManager.detect_encoding(file_path) if use_encoding else "utf-8"
            with open(file_path, "r", encoding=encoding) as f:
                return True, json.load(f, object_pairs_hook=OrderedDict)
        except Exception as e:
            handle_exception(e)
            return False, None

    @staticmethod
    def save_file(file_path=None, data="", use_encoding=False):
        try:
            if file_path is None:
                print("Select File Path")
                return

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            handle_exception(e)

    @staticmethod
    def save_text(file_path, data, use_encoding=False):
        try:
            if not file_path.endswith(".txt"):
                file_path += ".txt"
            encoding = FileManager.detect_encoding(file_path) if use_encoding else "utf-8"
            with open(file_path, "w", encoding=encoding) as f:
                f.write(data)
        except Exception as e:
            handle_exception(e)

    @staticmethod
    def save_html(file_path, data, use_encoding=False):
        try:
            if not file_path.endswith(".html"):
                file_path += ".html"
            encoding = FileManager.detect_encoding(file_path) if use_encoding else "utf-8"
            with open(file_path, "w", encoding=encoding) as f:
                f.write(data)
        except Exception as e:
            handle_exception(e)

    @staticmethod
    def detect_encoding(file_path):
        try:
            with open(file_path, 'rb') as f:
                return chardet.detect(f.read()).get('encoding', 'utf-8')
        except Exception:
            return 'utf-8'

    @staticmethod
    def recreate_directory(target_dir):
        try:
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.makedirs(target_dir, exist_ok=True)
        except Exception as e:
            handle_exception(e)

    @staticmethod
    def search_files(directory=None, file_filter=None):

        if file_filter is None:
            file_filter = []

        def find_file(root_dir, extensions):
            found_files = []
            for dirpath, _, filenames in os.walk(root_dir):
                for filename in filenames:
                    if any(filename.lower().endswith(ext) for ext in extensions):
                        found_files.append(os.path.join(dirpath, filename))
            return found_files

        files = find_file(os.path.normpath(directory), file_filter)

        return files

    @staticmethod
    def get_file_size(file_path):
        return os.path.getsize(file_path)

    def copy_file(self, src_path, dest_dir):
        if self.is_file(dest_dir):
            os.remove(dest_dir)

        shutil.copy2(src_path, dest_dir)

