#!/usr/bin/env python3
import sys
import cv2
import multiprocessing
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer
import numpy as np
import time

# shared memory queue
from multiprocessing import Queue, Event


def producer(queue: Queue, pause_event: Event, stop_event: Event):
    cnt = 0
    cap = cv2.VideoCapture('sample_video.mp4')
    while not stop_event.is_set():
        pause_event.wait()
        ret, frame = cap.read()
        if not ret:
            break
        if not queue.full():
            cnt+=1
            print("put >> ", cnt)
            queue.put(frame)
        else:
            time.sleep(0.01)
    cap.release()


def process_frame(frame):
    # CPU 예시 처리 (grayscale)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)  # 3채널로 복원 (일관성 위해)


def consumer(queue: Queue, output_queue: Queue, pause_event: Event, stop_event: Event):
    cnt = 0
    while not stop_event.is_set():
        pause_event.wait()
        if not queue.empty():
            frame = queue.get()
            processed = process_frame(frame)
            if not output_queue.full():
                cnt += 1
                print("get >>>>>>>>>>>>>>> ", cnt)
                output_queue.put((frame, processed))
        else:
            time.sleep(0.01)
    print("Closed Consumer")


class VideoApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Processing GUI")
        self.setGeometry(200, 200, 1200, 600)

        # layout setup
        layout = QVBoxLayout()
        hlayout = QHBoxLayout()
        self.original_label = QLabel("Original Frame")
        self.processed_label = QLabel("Processed Frame")

        self.original_label.setFixedSize(580, 440)
        self.processed_label.setFixedSize(580, 440)

        hlayout.addWidget(self.original_label)
        hlayout.addWidget(self.processed_label)

        self.start_btn = QPushButton("Start")
        self.suspend_btn = QPushButton("Suspend")
        self.resume_btn = QPushButton("Resume")
        self.stop_btn = QPushButton("Stop")

        layout.addLayout(hlayout)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.suspend_btn)
        layout.addWidget(self.resume_btn)
        layout.addWidget(self.stop_btn)
        self.setLayout(layout)

        # event binding
        self.start_btn.clicked.connect(self.start_process)
        self.suspend_btn.clicked.connect(self.suspend_process)
        self.resume_btn.clicked.connect(self.resume_process)
        self.stop_btn.clicked.connect(self.stop_process)

        # multiprocessing
        self.frame_queue = multiprocessing.Queue(maxsize=100)
        self.output_queue = multiprocessing.Queue(maxsize=100)
        self.pause_event = multiprocessing.Event()
        self.stop_event = multiprocessing.Event()
        self.producer_proc = None
        self.consumer_proc = None

        # Timer for GUI updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frames)

    def start_process(self):
        self.pause_event.set()
        self.stop_event.clear()

        self.producer_proc = multiprocessing.Process(
            target=producer,
            args=(self.frame_queue, self.pause_event, self.stop_event)
        )
        self.consumer_proc = multiprocessing.Process(
            target=consumer,
            args=(self.frame_queue, self.output_queue, self.pause_event, self.stop_event)
        )

        self.producer_proc.start()
        self.consumer_proc.start()
        self.timer.start(30)  # update every ~30ms (approx 30 FPS)

    def suspend_process(self):
        self.pause_event.clear()

    def resume_process(self):
        self.pause_event.set()

    def stop_process(self):
        self.stop_event.set()
        self.timer.stop()

        if self.producer_proc:
            self.producer_proc.join()
        if self.consumer_proc:
            self.consumer_proc.join()

    def update_frames(self):
        if not self.output_queue.empty():
            orig_frame, proc_frame = self.output_queue.get()

            orig_qimage = self.convert_cv_to_qt(orig_frame)
            proc_qimage = self.convert_cv_to_qt(proc_frame)

            self.original_label.setPixmap(QPixmap.fromImage(orig_qimage))
            self.processed_label.setPixmap(QPixmap.fromImage(proc_qimage))

    def convert_cv_to_qt(self, frame):
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        return QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888).scaled(
            580, 440
        )


if __name__ == '__main__':
    multiprocessing.set_start_method('spawn')
    app = QApplication(sys.argv)
    win = VideoApp()
    win.show()
    sys.exit(app.exec_())
