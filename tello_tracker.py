#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DJI Tello — Multi-mode Tracker
Режимы: MANUAL (джойстики) → FACE (детекция лица) → CSRT (захват цели мышью)
Переключение: кнопка MODE или клавиша 't'
Джойстики всегда работают как override поверх любого автопилота
"""

import socket
import threading
import time
import queue
import cv2
import numpy as np
import logging

from libs.pid import PIDController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELLO_IP = "192.168.10.1"
TELLO_PORT = 8889
STATUS_PORT = 8890
VIDEO_PORT = 11111

FRAME_W, FRAME_H = 960, 720
PANEL_H = 160
WINDOW_H = FRAME_H + PANEL_H

JOY_RADIUS = 50
KNOB_RADIUS = 18
BTN_W, BTN_H = 110, 40

TARGET_FACE_AREA = 0.08
AREA_STOP_RATIO = 1.5
AREA_RETREAT_RATIO = 2.0
RETREAT_SPEED = -40

MODE_MANUAL = 0
MODE_FACE = 1
MODE_CSRT = 2
MODE_NAMES = ["MANUAL", "FACE", "CSRT"]
MODE_COLORS = [(0, 180, 255), (0, 255, 0), (255, 200, 0)]


# ---------------------------------------------------------------------------
class VirtualJoystick:
    def __init__(self, cx: int, cy: int, label_x: str, label_y: str):
        self.cx, self.cy = cx, cy
        self.label_x, self.label_y = label_x, label_y
        self.knob_x, self.knob_y = cx, cy
        self.active = False

    def hit_test(self, x: int, y: int) -> bool:
        return abs(x - self.cx) <= JOY_RADIUS and abs(y - self.cy) <= JOY_RADIUS

    def drag(self, x: int, y: int):
        self.knob_x = int(np.clip(x, self.cx - JOY_RADIUS, self.cx + JOY_RADIUS))
        self.knob_y = int(np.clip(y, self.cy - JOY_RADIUS, self.cy + JOY_RADIUS))

    def release(self):
        self.knob_x, self.knob_y = self.cx, self.cy
        self.active = False

    def value_x(self) -> int:
        return int((self.knob_x - self.cx) / JOY_RADIUS * 100)

    def value_y(self) -> int:
        return int((self.cy - self.knob_y) / JOY_RADIUS * 100)

    def is_centered(self) -> bool:
        return self.knob_x == self.cx and self.knob_y == self.cy

    def draw(self, img: np.ndarray):
        overlay = img.copy()
        cv2.rectangle(overlay,
                      (self.cx - JOY_RADIUS, self.cy - JOY_RADIUS),
                      (self.cx + JOY_RADIUS, self.cy + JOY_RADIUS),
                      (50, 50, 50), -1)
        cv2.addWeighted(overlay, 0.5, img, 0.5, 0, img)
        cv2.rectangle(img,
                      (self.cx - JOY_RADIUS, self.cy - JOY_RADIUS),
                      (self.cx + JOY_RADIUS, self.cy + JOY_RADIUS),
                      (180, 180, 180), 2)
        cv2.line(img, (self.cx, self.cy - JOY_RADIUS), (self.cx, self.cy + JOY_RADIUS), (80, 80, 80), 1)
        cv2.line(img, (self.cx - JOY_RADIUS, self.cy), (self.cx + JOY_RADIUS, self.cy), (80, 80, 80), 1)
        cv2.circle(img, (self.knob_x, self.knob_y), KNOB_RADIUS, (0, 200, 255), -1)
        cv2.circle(img, (self.knob_x, self.knob_y), KNOB_RADIUS, (255, 255, 255), 2)
        cv2.putText(img, f"{self.label_x}/{self.label_y}",
                    (self.cx - JOY_RADIUS, self.cy + JOY_RADIUS + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)


# ---------------------------------------------------------------------------
class Button:
    def __init__(self, x: int, y: int, w: int, h: int, text: str, color: tuple):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.text = text
        self.color = color

    def hit_test(self, mx: int, my: int) -> bool:
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h

    def draw(self, img: np.ndarray, text_override: str | None = None):
        cv2.rectangle(img, (self.x, self.y), (self.x + self.w, self.y + self.h), self.color, -1)
        cv2.rectangle(img, (self.x, self.y), (self.x + self.w, self.y + self.h), (255, 255, 255), 1)
        txt = text_override or self.text
        ts = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        tx = self.x + (self.w - ts[0]) // 2
        ty = self.y + (self.h + ts[1]) // 2
        cv2.putText(img, txt, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)


# ---------------------------------------------------------------------------
class TelloTracker:
    def __init__(self):
        self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.cmd_sock.settimeout(10)
        self.rc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._cmd_lock = threading.Lock()
        self._cmd_queue: queue.Queue = queue.Queue()

        self.is_connected = False
        self.is_flying = False
        self.battery = "?"
        self.cmd_status = ""

        self.mode = MODE_MANUAL

        self.yaw_pid = PIDController(P=0.4, I=0.0, D=0.2, minVal=-100, maxVal=100,
                                     thresholdVal=80, minOut=-100, maxOut=100)
        self.thr_pid = PIDController(P=0.4, I=0.0, D=0.2, minVal=-100, maxVal=100,
                                     thresholdVal=80, minOut=-80, maxOut=80)
        self.pit_pid = PIDController(P=0.3, I=0.0, D=0.1, minVal=-100, maxVal=100,
                                     thresholdVal=80, minOut=-60, maxOut=60)

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        self.tracker: cv2.legacy.TrackerCSRT | None = None
        self.tracking = False
        self.initial_area = 0.0

        self._selecting = False
        self._sel_start = (0, 0)
        self._sel_end = (0, 0)
        self._sel_done = False

        panel_y = FRAME_H + PANEL_H // 2
        self.joy_left = VirtualJoystick(100, panel_y, "Yaw", "Thr")
        self.joy_right = VirtualJoystick(FRAME_W - 100, panel_y, "Roll", "Pit")

        bx = FRAME_W // 2
        self.btn_takeoff = Button(bx - 235, FRAME_H + 10, BTN_W, BTN_H, "TAKEOFF", (0, 140, 0))
        self.btn_land = Button(bx - 115, FRAME_H + 10, BTN_W, BTN_H, "LAND", (0, 0, 180))
        self.btn_mode = Button(bx + 5, FRAME_H + 10, BTN_W, BTN_H, "MODE", (140, 80, 0))
        self.btn_reset = Button(bx + 125, FRAME_H + 10, BTN_W, BTN_H, "RESET", (100, 50, 50))

        self._status_thread = None
        self._cmd_thread = None
        self._stop = False

    # -- network ---------------------------------------------------------------

    def _send(self, cmd: str, timeout: float = 7) -> str:
        with self._cmd_lock:
            self.cmd_sock.settimeout(timeout)
            self.cmd_sock.sendto(cmd.encode(), (TELLO_IP, TELLO_PORT))
            try:
                data, _ = self.cmd_sock.recvfrom(1024)
                return data.decode().strip()
            except socket.timeout:
                return ""

    def _send_rc(self, a: int, b: int, c: int, d: int):
        a = int(np.clip(a, -100, 100))
        b = int(np.clip(b, -100, 100))
        c = int(np.clip(c, -100, 100))
        d = int(np.clip(d, -100, 100))
        self.rc_sock.sendto(f"rc {a} {b} {c} {d}".encode(), (TELLO_IP, TELLO_PORT))

    # -- background command worker ---------------------------------------------

    def _cmd_worker(self):
        while not self._stop:
            try:
                cmd, timeout, callback = self._cmd_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            self.cmd_status = f"Sending: {cmd}..."
            resp = self._send(cmd, timeout)
            if callback:
                callback(resp)
            self._cmd_queue.task_done()

    # -- connect ---------------------------------------------------------------

    def connect(self) -> bool:
        resp = self._send("command")
        if resp == "ok":
            self.is_connected = True
            logger.info("Connected to Tello (command -> ok)")
            self._start_background()
            return True
        logger.warning("command timeout, checking status stream...")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(('', STATUS_PORT))
            s.settimeout(3)
            data, _ = s.recvfrom(1024)
            s.close()
            if data:
                self.is_connected = True
                logger.info("Tello already in SDK mode")
                self._start_background()
                return True
        except Exception:
            pass
        logger.error("Cannot connect to Tello")
        return False

    def _start_background(self):
        self._stop = False
        self._status_thread = threading.Thread(target=self._status_loop, daemon=True)
        self._status_thread.start()
        self._cmd_thread = threading.Thread(target=self._cmd_worker, daemon=True)
        self._cmd_thread.start()

    def _status_loop(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(('', STATUS_PORT))
            s.settimeout(2)
        except OSError:
            return
        while not self._stop:
            try:
                data, _ = s.recvfrom(1024)
                text = data.decode().strip()
                for pair in text.split(';'):
                    if ':' in pair:
                        k, v = pair.split(':', 1)
                        if k.strip() == 'bat':
                            self.battery = v.strip()
            except socket.timeout:
                continue
            except Exception:
                break
        s.close()

    # -- flight ----------------------------------------------------------------

    def _on_takeoff_resp(self, resp: str):
        logger.info(f"takeoff -> {resp}")
        if resp == "ok":
            self.is_flying = True
        self.cmd_status = f"takeoff: {resp or 'timeout'}"

    def _on_land_resp(self, resp: str):
        logger.info(f"land -> {resp}")
        self.is_flying = False
        self.cmd_status = f"land: {resp or 'timeout'}"

    def takeoff(self):
        if not self.is_flying:
            self.cmd_status = "TAKEOFF queued..."
            self._cmd_queue.put(("takeoff", 20, self._on_takeoff_resp))

    def land(self):
        if self.is_flying:
            self.cmd_status = "LAND queued..."
            self._cmd_queue.put(("land", 20, self._on_land_resp))

    # -- mode switching --------------------------------------------------------

    def cycle_mode(self):
        self.mode = (self.mode + 1) % 3
        self._reset_auto_state()
        logger.info(f"Mode -> {MODE_NAMES[self.mode]}")
        self.cmd_status = f"Mode: {MODE_NAMES[self.mode]}"

    def _reset_auto_state(self):
        self.tracker = None
        self.tracking = False
        self.initial_area = 0.0
        self._selecting = False
        self._sel_done = False
        self.yaw_pid.reset()
        self.thr_pid.reset()
        self.pit_pid.reset()

    # -- face detection --------------------------------------------------------

    def detect_face(self, frame: np.ndarray):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.15, 5, minSize=(50, 50))
        if len(faces) == 0:
            return None
        biggest = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = biggest
        return (x + w // 2, y + h // 2, w, h)

    # -- CSRT tracker ----------------------------------------------------------

    def init_tracker(self, frame: np.ndarray):
        x1, y1 = self._sel_start
        x2, y2 = self._sel_end
        x, y = max(0, min(x1, x2)), max(0, min(y1, y2))
        w, h = abs(x2 - x1), abs(y2 - y1)
        if w < 15 or h < 15:
            self.cmd_status = "Selection too small"
            return
        self.tracker = cv2.legacy.TrackerCSRT_create()
        self.tracker.init(frame, (x, y, w, h))
        self.initial_area = float(w * h)
        self.tracking = True
        self.yaw_pid.reset()
        self.thr_pid.reset()
        self.pit_pid.reset()
        logger.info(f"CSRT init: ({x},{y},{w},{h}), area={self.initial_area:.0f}")
        self.cmd_status = "Target locked!"

    # -- mouse callback --------------------------------------------------------

    def mouse_cb(self, event, x, y, flags, param):
        if self._selecting:
            if event == cv2.EVENT_MOUSEMOVE:
                self._sel_end = (min(x, FRAME_W - 1), min(y, FRAME_H - 1))
            elif event == cv2.EVENT_LBUTTONUP:
                self._sel_end = (min(x, FRAME_W - 1), min(y, FRAME_H - 1))
                self._sel_done = True
                self._selecting = False
            return

        if event == cv2.EVENT_LBUTTONDOWN:
            if y < FRAME_H and self.mode == MODE_CSRT:
                self._selecting = True
                self._sel_start = (x, y)
                self._sel_end = (x, y)
                self._sel_done = False
                return
            if self.btn_takeoff.hit_test(x, y):
                self.takeoff()
                return
            if self.btn_land.hit_test(x, y):
                self.land()
                return
            if self.btn_mode.hit_test(x, y):
                self.cycle_mode()
                return
            if self.btn_reset.hit_test(x, y):
                self._reset_auto_state()
                self.cmd_status = "Reset"
                return
            for joy in (self.joy_left, self.joy_right):
                if joy.hit_test(x, y):
                    joy.active = True
                    break

        elif event == cv2.EVENT_MOUSEMOVE:
            for joy in (self.joy_left, self.joy_right):
                if joy.active:
                    joy.drag(x, y)
                    break

        elif event == cv2.EVENT_LBUTTONUP:
            self.joy_left.release()
            self.joy_right.release()

    # -- main loop -------------------------------------------------------------

    def run(self):
        if not self.connect():
            return

        self._send("streamon")
        time.sleep(1)

        cap = cv2.VideoCapture(
            f'udp://@0.0.0.0:{VIDEO_PORT}?overrun_nonfatal=1&fifo_size=50000000',
            cv2.CAP_FFMPEG
        )

        win = "Tello Tracker"
        cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(win, self.mouse_cb)

        logger.info("MANUAL mode. 't'=switch mode, Space=takeoff, 'l'=land, 'r'=reset, 'q'=quit.")

        no_face_count = 0
        csrt_lost_count = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue

                frame = cv2.resize(frame, (FRAME_W, FRAME_H))

                joy_active = not self.joy_left.is_centered() or not self.joy_right.is_centered()
                rc_a, rc_b, rc_c, rc_d = 0, 0, 0, 0

                face = None
                track_box = None

                # ---- joystick always has priority ----
                if joy_active:
                    rc_d = self.joy_left.value_x()
                    rc_c = self.joy_left.value_y()
                    rc_a = self.joy_right.value_x()
                    rc_b = self.joy_right.value_y()

                # ---- FACE mode ----
                elif self.mode == MODE_FACE:
                    face = self.detect_face(frame)
                    if face and self.is_flying:
                        no_face_count = 0
                        fx, fy, fw, fh = face
                        err_x = (fx - FRAME_W // 2) / (FRAME_W / 2)
                        err_y = (FRAME_H // 2 - fy) / (FRAME_H / 2)
                        face_area = (fw * fh) / (FRAME_W * FRAME_H)
                        err_z = (TARGET_FACE_AREA - face_area) / TARGET_FACE_AREA
                        rc_d = int(self.yaw_pid.update(err_x * 100))
                        rc_c = int(self.thr_pid.update(err_y * 100))
                        rc_b = int(self.pit_pid.update(err_z * 100))
                    elif face is None:
                        no_face_count += 1
                        if no_face_count > 10:
                            self.yaw_pid.reset()
                            self.thr_pid.reset()
                            self.pit_pid.reset()

                # ---- CSRT mode ----
                elif self.mode == MODE_CSRT:
                    if self._sel_done:
                        self._sel_done = False
                        self.init_tracker(frame)

                    if self.tracking and self.tracker is not None:
                        ok, box = self.tracker.update(frame)
                        if ok:
                            csrt_lost_count = 0
                            track_box = tuple(int(v) for v in box)
                        else:
                            csrt_lost_count += 1
                            if csrt_lost_count > 30:
                                self._reset_auto_state()
                                self.cmd_status = "Target lost!"

                    if track_box is not None and self.is_flying:
                        bx, by, bw, bh = track_box
                        tcx, tcy = bx + bw // 2, by + bh // 2
                        current_area = float(bw * bh)
                        err_x = (tcx - FRAME_W // 2) / (FRAME_W / 2)
                        err_y = (FRAME_H // 2 - tcy) / (FRAME_H / 2)
                        rc_d = int(self.yaw_pid.update(err_x * 100))
                        rc_c = int(self.thr_pid.update(err_y * 100))
                        area_ratio = current_area / self.initial_area if self.initial_area > 0 else 1.0
                        if area_ratio > AREA_RETREAT_RATIO:
                            rc_b = RETREAT_SPEED
                        elif area_ratio > AREA_STOP_RATIO:
                            rc_b = 0
                        else:
                            rc_b = int(self.pit_pid.update((1.0 - area_ratio) * 100))

                if self.is_flying:
                    self._send_rc(rc_a, rc_b, rc_c, rc_d)

                # ---- draw ----
                canvas = np.zeros((WINDOW_H, FRAME_W, 3), dtype=np.uint8)
                canvas[:FRAME_H, :] = frame

                if face is not None:
                    fx, fy, fw, fh = face
                    cv2.rectangle(canvas, (fx - fw // 2, fy - fh // 2),
                                  (fx + fw // 2, fy + fh // 2), (0, 255, 0), 2)
                    cv2.circle(canvas, (fx, fy), 5, (0, 255, 0), -1)
                    cv2.line(canvas, (FRAME_W // 2, FRAME_H // 2), (fx, fy), (0, 255, 255), 1)

                if track_box is not None:
                    bx, by, bw, bh = track_box
                    area_ratio = (bw * bh) / self.initial_area if self.initial_area > 0 else 1.0
                    if area_ratio > AREA_RETREAT_RATIO:
                        box_color = (0, 0, 255)
                    elif area_ratio > AREA_STOP_RATIO:
                        box_color = (0, 200, 255)
                    else:
                        box_color = (0, 255, 0)
                    cv2.rectangle(canvas, (bx, by), (bx + bw, by + bh), box_color, 2)
                    tcx, tcy = bx + bw // 2, by + bh // 2
                    cv2.circle(canvas, (tcx, tcy), 5, box_color, -1)
                    cv2.line(canvas, (FRAME_W // 2, FRAME_H // 2), (tcx, tcy), (0, 255, 255), 1)
                    cv2.putText(canvas, f"x{area_ratio:.2f}", (bx, by - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)

                if self._selecting:
                    cv2.rectangle(canvas, self._sel_start, self._sel_end, (255, 255, 0), 2)

                cv2.drawMarker(canvas, (FRAME_W // 2, FRAME_H // 2),
                               (255, 255, 255), cv2.MARKER_CROSS, 20, 1)

                # ---- panel ----
                canvas[FRAME_H:, :] = (30, 30, 30)

                self.btn_takeoff.draw(canvas)
                self.btn_land.draw(canvas)
                mode_label = MODE_NAMES[self.mode]
                self.btn_mode.color = MODE_COLORS[self.mode]
                self.btn_mode.draw(canvas, text_override=mode_label)
                self.btn_reset.draw(canvas)
                self.joy_left.draw(canvas)
                self.joy_right.draw(canvas)

                if joy_active:
                    status_text = "JOYSTICK OVERRIDE"
                    status_color = (0, 180, 255)
                else:
                    status_text = MODE_NAMES[self.mode]
                    status_color = MODE_COLORS[self.mode]
                cv2.putText(canvas, status_text, (FRAME_W // 2 - 80, FRAME_H + 75),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 2)

                cv2.putText(canvas, f"Bat: {self.battery}%", (FRAME_W // 2 - 40, FRAME_H + 105),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                fly_text = "FLYING" if self.is_flying else "GROUNDED"
                fly_color = (0, 200, 255) if self.is_flying else (100, 100, 100)
                cv2.putText(canvas, fly_text, (FRAME_W // 2 - 40, FRAME_H + 130),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, fly_color, 1)

                if self.cmd_status:
                    cv2.putText(canvas, self.cmd_status, (FRAME_W // 2 - 80, FRAME_H + 155),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

                rc_text = f"RC: a={rc_a:+4d} b={rc_b:+4d} c={rc_c:+4d} d={rc_d:+4d}"
                cv2.putText(canvas, rc_text, (10, FRAME_H + 155),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

                cv2.imshow(win, canvas)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    break
                elif key == ord('t'):
                    self.cycle_mode()
                elif key == ord(' '):
                    self.takeoff()
                elif key == ord('l'):
                    self.land()
                elif key == ord('r'):
                    self._reset_auto_state()
                    self.cmd_status = "Reset"

        except KeyboardInterrupt:
            pass
        finally:
            self._stop = True
            if self.is_flying:
                self._send("land", timeout=10)
            self._send("streamoff", timeout=5)
            cap.release()
            cv2.destroyAllWindows()
            self.cmd_sock.close()
            self.rc_sock.close()
            logger.info("Shutdown complete.")


def main():
    tracker = TelloTracker()
    tracker.run()


if __name__ == "__main__":
    main()
