#!/usr/bin/env python3
import os.path
import multiprocessing
import time

import cv2

from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QThread
from PyQt5.QtGui import QBrush, QColor
from source.head import *

from source.source_files.producer import ProducerProcess
from source.source_files.consumer import ConsumerThread

if getattr(sys, 'frozen', False):  # PyInstaller로 패키징된 경우
    BASE_DIR = os.path.dirname(sys.executable)  # 실행 파일이 있는 폴더
    RESOURCE_DIR = sys._MEIPASS  # 임시 폴더(내부 리소스 저장됨)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = BASE_DIR  # 개발 환경에서는 현재 폴더 사용


class JoinThread(QThread):
    def __init__(self, tasks, on_done_callback=None):
        super().__init__()
        self.tasks = tasks
        self.on_done_callback = on_done_callback

    def run(self):
        for task in self.tasks:
            if task is None:
                continue
            if isinstance(task, multiprocessing.Process):
                if task.is_alive():
                    task.join(timeout=5)
                    if task.is_alive():
                        log_info("info", "ProducerProcess did not stop in time, terminate forced.")
                        task.terminate()
                    log_info("info", "Closed ProducerProcess")
            elif isinstance(task, QThread):
                if task.isRunning():
                    task.quit()
                    task.wait(3000)
                log_info("info", "Closed ConsumerThread")

        if self.on_done_callback:
            self.on_done_callback()

class IMATestControl(FileManager, QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.widget_ui = None
        self.producer_proc = None
        self.consumer_thread = None
        self.join_thread = None
        self.frame_queue = None
        self.pause_event = None
        self.stop_event = None

        # 웹캠 또는 파일 설정
        self.use_webcam = False  # 기본: 파일 사용

        # 기존 UI 로드
        rt = load_module_func(module_name="source.ui_designer.main_frame")
        self.mainFrame_ui = rt.Ui_MainWindow()
        self.mainFrame_ui.setupUi(self)

        self.mainFrameInitialize()


    def closeEvent(self, event):
        self.stop_event.set()
        if self.producer_proc and self.producer_proc.is_alive():
            self.producer_proc.terminate()
        event.accept()

    def mainFrameInitialize(self):
        self.set_buttons_enabled(start=True, suspend=False, resume=False, stop=False)

    def ctrl_log_browser(self):
        """Show 또는 Hide 액션에 따라 QGroupBox 상태 변경"""
        sender = self.sender()  # 어떤 QAction이 호출되었는지 확인
        if sender.text() == "Show":
            self.mainFrame_ui.loggroupBox.show()
        else:
            self.mainFrame_ui.loggroupBox.hide()

    def normalOutputWritten(self, text):
        cursor = self.mainFrame_ui.logtextbrowser.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)

        # 기본 글자 색상 설정
        color_format = cursor.charFormat()
        if "><" in text:
            color_format.setForeground(QtCore.Qt.red)
        else:
            color_format.setForeground(QtCore.Qt.black)

        cursor.setCharFormat(color_format)
        cursor.insertText(text)

        # 커서를 최신 위치로 업데이트
        self.mainFrame_ui.logtextbrowser.setTextCursor(cursor)
        self.mainFrame_ui.logtextbrowser.ensureCursorVisible()


    def cleanLogBrowser(self):
        self.mainFrame_ui.logtextbrowser.clear()

    def connectSlotSignal(self):
        """ sys.stdout redirection """
        sys.stdout = EmittingStream(textWritten=self.normalOutputWritten)

        self.mainFrame_ui.actionShow.triggered.connect(self.ctrl_log_browser)
        self.mainFrame_ui.actionHide.triggered.connect(self.ctrl_log_browser)

        self.mainFrame_ui.start_btn.clicked.connect(self.start_process)
        self.mainFrame_ui.suspend_btn.clicked.connect(self.suspend_process)
        self.mainFrame_ui.resume_btn.clicked.connect(self.resume_process)
        self.mainFrame_ui.stop_btn.clicked.connect(self.stop_process)

        self.mainFrame_ui.fileopen_btn.clicked.connect(self.selection_files)
        self.mainFrame_ui.widgetclear_btn.clicked.connect(
            lambda: self.mainFrame_ui.filelistlistWidget.clear()
        )

        self.mainFrame_ui.log_clear_pushButton.clicked.connect(self.cleanLogBrowser)


    def selection_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "파일 선택", "", "All Files (*)")

        if not file_paths:
            return

        self.mainFrame_ui.filelistlistWidget.clear()

        normalized_paths = [os.path.normpath(path) for path in file_paths]
        self.mainFrame_ui.filelistlistWidget.addItems(normalized_paths)

    def set_buttons_enabled(self, start, suspend, resume, stop):
        self.mainFrame_ui.start_btn.setEnabled(start)
        self.mainFrame_ui.suspend_btn.setEnabled(suspend)
        self.mainFrame_ui.resume_btn.setEnabled(resume)
        self.mainFrame_ui.stop_btn.setEnabled(stop)


    def clear_queue(self, q):
        try:
            while not q.empty():
                q.get_nowait()
        except Exception as e:
            log_info("error", f"Queue clear error: {e}")

    def start_process(self):
        self.use_webcam = self.mainFrame_ui.webcam_radioButton.isChecked()

        if self.use_webcam:
            video_paths = []
        else:

            video_paths = [
                self.mainFrame_ui.filelistlistWidget.item(i).text()
                for i in range(self.mainFrame_ui.filelistlistWidget.count())
            ]
            if len(video_paths) == 0:
                print("Select file")
                return

            # 이미지 파일 확장자 목록 (필요에 따라 추가 가능)
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']

            # video_paths에서 이미지 파일만 필터링
            image_files = [
                file for file in video_paths if os.path.splitext(file)[1].lower() in image_extensions
            ]

            # 만약 모든 파일이 이미지 파일이라면
            if len(image_files) == len(video_paths):
                # 프로그래스바의 최대값을 이미지 파일 개수로 설정
                self.mainFrame_ui.progressBar.setMaximum(len(image_files))
            else:
                # 그렇지 않으면 100으로 설정
                self.mainFrame_ui.progressBar.setMaximum(100)

        self.frame_queue = multiprocessing.Queue(maxsize=60*60*5)   #60fps * 5분 분량
        self.pause_event = multiprocessing.Event()
        self.stop_event = multiprocessing.Event()

        self.pause_event.set()
        self.stop_event.clear()
        self.clear_queue(self.frame_queue)

        self.producer_proc = multiprocessing.Process(
            target=ProducerProcess,
            args=(
                self.frame_queue,
                self.pause_event,
                self.stop_event,
                self.use_webcam,
                video_paths  # 리스트 전달
            )
        )
        self.producer_proc.start()

        self.consumer_thread = ConsumerThread(self.frame_queue, self.pause_event, self.stop_event)
        self.consumer_thread.frame_ready.connect(self.update_frames)
        self.consumer_thread.finished_processing.connect(self.stop_process)  # 자동 종료 처리
        self.consumer_thread.start()

        self.set_buttons_enabled(start=False, suspend=True, resume=False, stop=True)

    def suspend_process(self):
        self.pause_event.clear()
        self.set_buttons_enabled(start=False, suspend=False, resume=True, stop=True)

    def resume_process(self):
        self.pause_event.set()
        self.set_buttons_enabled(start=False, suspend=True, resume=False, stop=True)

    def reset_progress_bar(self):
        self.mainFrame_ui.progressBar.reset()

    def stop_process(self):
        self.mainFrame_ui.progressBar.setValue(100)

        QTimer.singleShot(500, self.reset_progress_bar)

        self.stop_event.set()

        if self.consumer_thread:
            self.consumer_thread.requestInterruption()
            self.consumer_thread.quit()

        self.join_thread = JoinThread(
            tasks=[self.producer_proc, self.consumer_thread],
            on_done_callback=self.on_all_stopped
        )
        self.join_thread.start()

        self.producer_proc = None
        self.consumer_thread = None

        QtWidgets.QMessageBox.information(
            self,
            "Test Done",
            "[INFO] All Finished Done !.",
            QtWidgets.QMessageBox.Ok
        )

    def on_all_stopped(self):
        log_info("info", "All processes and threads finished.")
        self.set_buttons_enabled(start=True, suspend=False, resume=False, stop=False)
        self.mainFrame_ui.org_label.clear()
        self.mainFrame_ui.processed_label.clear()

    def update_frames(self, cnt, orig_frame, proc_frame):
        self.mainFrame_ui.org_label.setPixmap(QPixmap.fromImage(self.convert_cv_to_qt(orig_frame)))
        self.mainFrame_ui.processed_label.setPixmap(QPixmap.fromImage(self.convert_cv_to_qt(proc_frame)))

        if cnt is not None and isinstance(cnt, int) and cnt >= 0:
            self.mainFrame_ui.progressBar.setValue(cnt % 100)

    def convert_cv_to_qt(self, frame):
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        return QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888).scaled(
            580, 440, Qt.KeepAspectRatio
        )


if __name__ == "__main__":
    import sys

    multiprocessing.set_start_method('spawn')
    app = QtWidgets.QApplication(sys.argv)  # QApplication 생성 (필수)

    app.setStyle("Fusion")
    ui = IMATestControl()
    ui.showMaximized()
    # ui.show()
    ui.connectSlotSignal()

    sys.exit(app.exec_())
