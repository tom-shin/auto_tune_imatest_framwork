import sys
import os
import cv2
import multiprocessing
import time
import numpy as np
from queue import Empty

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap

from ..head import log_info
def process_frame(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

class ConsumerThread(QThread):
    frame_ready = pyqtSignal(int, np.ndarray, np.ndarray)
    finished_processing = pyqtSignal()

    def __init__(self, queue: multiprocessing.Queue, pause_event: multiprocessing.Event, stop_event: multiprocessing.Event):
        super().__init__()
        self.queue = queue
        self.pause_event = pause_event
        self.stop_event = stop_event

    def run(self):
        time_out = 3
        cnt = 0
        while not self.stop_event.is_set() and not self.isInterruptionRequested():
            self.pause_event.wait()
            try:
                # 일정 시간 동안 프레임이 오지 않으면 종료 시그널
                frame = self.queue.get(timeout=time_out)  # 5초간 프레임이 없으면 종료 판단
                # print(frame)
                processed = process_frame(frame)

                cnt += 1
                self.frame_ready.emit(cnt, frame, processed)
            except Empty:
                log_info("info", f"ConsumerThread: {time_out}초 동안 프레임이 들어오지 않아 종료합니다.")
                self.finished_processing.emit()
                break