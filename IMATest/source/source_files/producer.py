import os
import cv2
import multiprocessing
import time
from queue import Empty

from ..head import log_info
def ProducerProcess(queue: multiprocessing.Queue,
                    pause_event: multiprocessing.Event,
                    stop_event: multiprocessing.Event,
                    web_cam: bool,
                    video_paths: list = None):  # 리스트로 받음

    def process_image(image_path):
        # queue.put(image_path)

        img = cv2.imread(image_path)
        if img is None:
            log_info("info", f"이미지 파일 열기 실패: {image_path}")
            return
        if not queue.full():
            queue.put(img.copy())
        else:
            log_info("info", "큐가 가득 차서 이미지를 넣을 수 없습니다.")

    def process_video(video_path, is_webcam=False):
        cap = cv2.VideoCapture(0 if is_webcam else video_path)

        if not cap.isOpened():
            log_info("info", f"비디오 파일 열기 실패: {video_path}")
            return
        while not stop_event.is_set():
            pause_event.wait()
            ret, frame = cap.read()
            if not ret:
                log_info("info", f"{video_path} 끝났음.")
                break

            if not queue.full():
                queue.put(frame)
            else:
                time.sleep(0.01)
        cap.release()

    if web_cam:
        process_video(video_path=None, is_webcam=True)
    else:
        if not video_paths or not isinstance(video_paths, list):
            log_info("info", "video_paths 리스트가 비어있거나 잘못되었습니다.")
            stop_event.set()
            return

        for path in video_paths:
            if stop_event.is_set():
                break
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.mp4', '.avi', '.mov', '.mkv']:
                process_video(video_path=path, is_webcam=False)
            elif ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                process_image(image_path=path)
                time.sleep(1.5)
            else:
                log_info("info", f"지원하지 않는 파일 형식: {path}")
                continue