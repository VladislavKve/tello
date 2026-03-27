#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DJI Tello — Web Interface (zero external JS dependencies)
Flask server + MJPEG video + REST API for controls
"""

import socket
import threading
import time
import queue
import cv2
import numpy as np
import logging
import json

from flask import Flask, Response, render_template, request, jsonify

from libs.pid import PIDController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELLO_IP = "192.168.10.1"
TELLO_PORT = 8889
STATUS_PORT = 8890
VIDEO_PORT = 11111

FRAME_W, FRAME_H = 960, 720

TARGET_FACE_AREA = 0.08
AREA_STOP_RATIO = 1.5
AREA_RETREAT_RATIO = 2.0
RETREAT_SPEED = -40

MODE_MANUAL = 0
MODE_FACE = 1
MODE_CSRT = 2
MODE_NAMES = ["MANUAL", "FACE", "CSRT"]


class TelloController:
    def __init__(self):
        self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.cmd_sock.settimeout(10)
        self.rc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._cmd_lock = threading.Lock()

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

        self.tracker = None
        self.tracking = False
        self.initial_area = 0.0

        self.joy_a = 0
        self.joy_b = 0
        self.joy_c = 0
        self.joy_d = 0
        self.joy_active = False
        self._joy_ts = 0.0

        self.auto_rc = [0, 0, 0, 0]

        self.area_ratio = 0.0
        self.collision_state = "none"

        self._frame = None
        self._frame_lock = threading.Lock()
        self._stop = True
        self._bg_running = False
        self._pending_roi = None
        self._reconnecting = False

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

    def _ping_tello(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.sendto(b"command", (TELLO_IP, TELLO_PORT))
            data, _ = s.recvfrom(1024)
            s.close()
            return bool(data)
        except Exception:
            try:
                s.close()
            except Exception:
                pass
            return False

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
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('', STATUS_PORT))
            s.settimeout(3)
            data, _ = s.recvfrom(1024)
            s.close()
            if data:
                self.is_connected = True
                logger.info("Tello already in SDK mode")
                self._start_background()
                return True
        except Exception as e:
            logger.warning(f"Status check failed: {e}")
        logger.error("Cannot connect to Tello")
        return False

    def reconnect(self) -> bool:
        if self._reconnecting:
            self.cmd_status = "Already reconnecting..."
            return False
        self._reconnecting = True
        self.cmd_status = "Reconnecting..."
        logger.info("Reconnect requested, stopping background threads...")
        try:
            self._stop = True
            time.sleep(1.5)
            self._bg_running = False

            self.is_connected = False
            self.is_flying = False
            self.battery = "?"
            self._reset_auto_state()
            self.auto_rc = [0, 0, 0, 0]
            self.area_ratio = 0.0
            self.collision_state = "none"
            self.mode = MODE_MANUAL

            try:
                self.cmd_sock.close()
            except Exception:
                pass
            try:
                self.rc_sock.close()
            except Exception:
                pass

            self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.cmd_sock.settimeout(10)
            self.rc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            max_attempts = 6
            for attempt in range(max_attempts):
                n = attempt + 1
                logger.info(f"Reconnect attempt {n}/{max_attempts}...")
                self.cmd_status = f"Attempt {n}/{max_attempts}..."

                if not self._ping_tello():
                    logger.info(f"Tello not reachable (attempt {n}), waiting...")
                    self.cmd_status = f"Waiting for drone ({n}/{max_attempts})..."
                    time.sleep(3)
                    continue

                if self.connect():
                    self.cmd_status = "Reconnected!"
                    logger.info("Reconnect successful")
                    return True
                time.sleep(2)

            self.cmd_status = "Reconnect failed — try again"
            logger.error("All reconnect attempts failed")
            return False
        finally:
            self._reconnecting = False

    def _start_background(self):
        if self._bg_running:
            return
        self._stop = False
        self._bg_running = True
        threading.Thread(target=self._status_loop, daemon=True).start()
        threading.Thread(target=self._video_loop, daemon=True).start()
        threading.Thread(target=self._rc_loop, daemon=True).start()

    def _rc_loop(self):
        try:
            while not self._stop:
                if time.time() - self._joy_ts > 1.0:
                    self.joy_active = False
                    self.joy_a = self.joy_b = self.joy_c = self.joy_d = 0

                if self.joy_active:
                    self._send_rc(self.joy_a, self.joy_b, self.joy_c, self.joy_d)
                else:
                    a, b, c, d = self.auto_rc
                    self._send_rc(a, b, c, d)
                time.sleep(0.05)
        except Exception:
            pass

    def _status_loop(self):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('', STATUS_PORT))
            s.settimeout(2)
        except OSError:
            logger.warning("Cannot bind status port")
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

    def _open_video(self):
        self._send("streamon")
        time.sleep(0.5)
        self._send("streamon")
        time.sleep(0.5)
        cap = cv2.VideoCapture(
            f'udp://@0.0.0.0:{VIDEO_PORT}?overrun_nonfatal=1&fflags=nobuffer',
            cv2.CAP_FFMPEG
        )
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _video_loop(self):
        cap = self._open_video()

        no_face_count = 0
        csrt_lost_count = 0
        fail_count = 0

        while not self._stop:
            ret, frame = cap.read()
            if not ret or frame is None:
                fail_count += 1
                if fail_count > 150:
                    logger.warning("Video stream lost, re-sending streamon...")
                    cap.release()
                    cap = self._open_video()
                    fail_count = 0
                time.sleep(0.01)
                continue
            fail_count = 0

            frame = cv2.resize(frame, (FRAME_W, FRAME_H))

            rc_a, rc_b, rc_c, rc_d = 0, 0, 0, 0
            face = None
            track_box = None
            col_state = "none"

            if self.mode == MODE_FACE:
                face = self._detect_face(frame)
                if face:
                    no_face_count = 0
                    fx, fy, fw, fh = face
                    err_x = (fx - FRAME_W // 2) / (FRAME_W / 2)
                    err_y = (FRAME_H // 2 - fy) / (FRAME_H / 2)
                    face_area = (fw * fh) / (FRAME_W * FRAME_H)
                    err_z = (TARGET_FACE_AREA - face_area) / TARGET_FACE_AREA
                    rc_d = int(self.yaw_pid.update(err_x * 100))
                    rc_c = int(self.thr_pid.update(err_y * 100))
                    rc_b = int(self.pit_pid.update(err_z * 100))
                    self.area_ratio = face_area / TARGET_FACE_AREA
                else:
                    no_face_count += 1
                    if no_face_count > 10:
                        self.yaw_pid.reset()
                        self.thr_pid.reset()
                        self.pit_pid.reset()
                        self.area_ratio = 0.0

            elif self.mode == MODE_CSRT:
                if self._pending_roi is not None:
                    roi = self._pending_roi
                    self._pending_roi = None
                    self._init_tracker(frame, roi)

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

                if track_box is not None:
                    bx, by, bw, bh = track_box
                    tcx, tcy = bx + bw // 2, by + bh // 2
                    current_area = float(bw * bh)
                    err_x = (tcx - FRAME_W // 2) / (FRAME_W / 2)
                    err_y = (FRAME_H // 2 - tcy) / (FRAME_H / 2)
                    rc_d = int(self.yaw_pid.update(err_x * 100))
                    rc_c = int(self.thr_pid.update(err_y * 100))
                    ar = current_area / self.initial_area if self.initial_area > 0 else 1.0
                    self.area_ratio = ar
                    if ar > AREA_RETREAT_RATIO:
                        rc_b = RETREAT_SPEED
                        col_state = "retreat"
                    elif ar > AREA_STOP_RATIO:
                        rc_b = 0
                        col_state = "stop"
                    else:
                        rc_b = int(self.pit_pid.update((1.0 - ar) * 100))
                        col_state = "approach"
            else:
                self.area_ratio = 0.0

            self.collision_state = col_state
            self.auto_rc = [rc_a, rc_b, rc_c, rc_d]

            display = frame.copy()
            cx_frame, cy_frame = FRAME_W // 2, FRAME_H // 2

            if face is not None:
                fx, fy, fw, fh = face
                cv2.rectangle(display, (fx - fw // 2, fy - fh // 2),
                              (fx + fw // 2, fy + fh // 2), (0, 255, 0), 2)
                cv2.circle(display, (fx, fy), 5, (0, 255, 0), -1)
                cv2.line(display, (cx_frame, cy_frame), (fx, fy), (0, 255, 255), 1)

            if track_box is not None:
                bx, by, bw, bh = track_box
                ar = (bw * bh) / self.initial_area if self.initial_area > 0 else 1.0
                if ar > AREA_RETREAT_RATIO:
                    clr = (0, 0, 255)
                elif ar > AREA_STOP_RATIO:
                    clr = (0, 200, 255)
                else:
                    clr = (0, 255, 0)
                cv2.rectangle(display, (bx, by), (bx + bw, by + bh), clr, 2)
                tcx, tcy = bx + bw // 2, by + bh // 2
                cv2.circle(display, (tcx, tcy), 5, clr, -1)
                cv2.line(display, (cx_frame, cy_frame), (tcx, tcy), (0, 255, 255), 1)
                cv2.putText(display, f"x{ar:.2f}", (bx, by - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, clr, 2)
                state_txt = {"retreat": "RETREAT!", "stop": "HOLD", "approach": "APPROACH"}
                if col_state in state_txt:
                    cv2.putText(display, state_txt[col_state],
                                (bx + bw + 5, by + bh // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, clr, 2)

            if self.mode == MODE_CSRT and not self.tracking:
                cv2.putText(display, "SELECT TARGET", (cx_frame - 100, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            mode_clr = [(0, 180, 255), (0, 255, 0), (255, 200, 0)][self.mode]
            cv2.putText(display, MODE_NAMES[self.mode], (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, mode_clr, 2)

            cv2.drawMarker(display, (cx_frame, cy_frame),
                           (255, 255, 255), cv2.MARKER_CROSS, 20, 1)

            with self._frame_lock:
                self._frame = display

        cap.release()
        self._bg_running = False

    def get_jpeg(self) -> bytes | None:
        with self._frame_lock:
            if self._frame is None:
                return None
            _, buf = cv2.imencode('.jpg', self._frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return buf.tobytes()

    def _detect_face(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.15, 5, minSize=(50, 50))
        if len(faces) == 0:
            return None
        biggest = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = biggest
        return (x + w // 2, y + h // 2, w, h)

    def _init_tracker(self, frame, roi):
        x, y, w, h = roi
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
        logger.info(f"CSRT init: ({x},{y},{w},{h})")
        self.cmd_status = "Target locked!"

    def _reset_auto_state(self):
        self.tracker = None
        self.tracking = False
        self.initial_area = 0.0
        self.yaw_pid.reset()
        self.thr_pid.reset()
        self.pit_pid.reset()

    def takeoff(self):
        self.cmd_status = "TAKEOFF sent"
        self.is_flying = True
        self.cmd_sock.sendto(b"takeoff", (TELLO_IP, TELLO_PORT))
        logger.info("takeoff sent")

    def land(self):
        self.cmd_status = "LAND sent"
        self.is_flying = False
        self.cmd_sock.sendto(b"land", (TELLO_IP, TELLO_PORT))
        logger.info("land sent")

    def cycle_mode(self):
        self.mode = (self.mode + 1) % 3
        self._reset_auto_state()
        logger.info(f"Mode -> {MODE_NAMES[self.mode]}")
        self.cmd_status = f"Mode: {MODE_NAMES[self.mode]}"

    def set_joystick(self, left_x, left_y, right_x, right_y):
        self.joy_d = int(left_x)
        self.joy_c = int(left_y)
        self.joy_a = int(right_x)
        self.joy_b = int(right_y)
        self.joy_active = any(v != 0 for v in (self.joy_a, self.joy_b, self.joy_c, self.joy_d))
        self._joy_ts = time.time()

    def select_roi(self, x, y, w, h):
        if self.mode == MODE_CSRT:
            self._pending_roi = (int(x), int(y), int(w), int(h))

    def get_status(self):
        return {
            "battery": self.battery,
            "mode": MODE_NAMES[self.mode],
            "mode_id": self.mode,
            "flying": self.is_flying,
            "tracking": self.tracking,
            "area_ratio": round(self.area_ratio, 2),
            "collision": self.collision_state,
            "cmd_status": self.cmd_status,
            "connected": self.is_connected,
        }

    def shutdown(self):
        self._stop = True
        self.cmd_sock.sendto(b"land", (TELLO_IP, TELLO_PORT))
        time.sleep(0.5)
        self.cmd_sock.sendto(b"streamoff", (TELLO_IP, TELLO_PORT))
        self.cmd_sock.close()
        self.rc_sock.close()
        logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
app = Flask(__name__)
tello = TelloController()


@app.route('/')
def index():
    return render_template('index.html')


def mjpeg_generator():
    while True:
        jpeg = tello.get_jpeg()
        if jpeg is None:
            time.sleep(0.03)
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
        time.sleep(0.03)


@app.route('/video_feed')
def video_feed():
    return Response(mjpeg_generator(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/status')
def api_status():
    return jsonify(tello.get_status())


@app.route('/api/j')
def api_joystick():
    tello.set_joystick(
        request.args.get('a', 0, type=int),
        request.args.get('b', 0, type=int),
        request.args.get('c', 0, type=int),
        request.args.get('d', 0, type=int),
    )
    return '', 204


@app.route('/api/takeoff', methods=['POST'])
def api_takeoff():
    tello.takeoff()
    return '', 204


@app.route('/api/land', methods=['POST'])
def api_land():
    tello.land()
    return '', 204


@app.route('/api/mode', methods=['POST'])
def api_mode():
    tello.cycle_mode()
    return '', 204


@app.route('/api/reset', methods=['POST'])
def api_reset():
    tello._reset_auto_state()
    tello.cmd_status = "Reset"
    return '', 204


@app.route('/api/roi', methods=['POST'])
def api_roi():
    d = request.json
    tello.select_roi(d.get('x', 0), d.get('y', 0), d.get('w', 0), d.get('h', 0))
    return '', 204


@app.route('/api/reconnect', methods=['POST'])
def api_reconnect():
    def do_reconnect():
        tello.reconnect()
    threading.Thread(target=do_reconnect, daemon=True).start()
    return jsonify({"status": "reconnecting"}), 202


def main():
    connected = tello.connect()
    if not connected:
        logger.warning("Tello not available. Server starting anyway — use Reconnect button.")
    logger.info("Starting web server on http://0.0.0.0:5000")
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        if tello.is_connected:
            tello.shutdown()


if __name__ == "__main__":
    main()
