import os
import re
import pyautogui
import cv2
import numpy as np
from PyQt5.QtWidgets import QPushButton, QWidget
from PyQt5.QtGui import QPainter, QPen, QColor, QImage
from PyQt5.QtCore import Qt, QTimer
import minimap
import training_fun

MON_DIR = os.path.join('imgs', 'monster')

# 오버레이 상태 플래그
_overlay_active = False
# F5 폴링 타이머 상태
_f5_timer = None
_f5_pressed = False
_f5_last_t = 0.0


def _ensure_dir():
    os.makedirs(MON_DIR, exist_ok=True)


def _next_path():
    _ensure_dir()
    existing = [f for f in os.listdir(MON_DIR) if re.match(r'^monster(\d+)\.png$', f)]
    nums = [int(re.findall(r'\d+', f)[0]) for f in existing]
    n = max(nums) + 1 if nums else 1
    return os.path.join(MON_DIR, f'monster{n}.png')


def _start_freeze_overlay():
    """전체 화면 스냅샷을 배경으로 하는 오버레이에서 영역 선택 후, 해당 영역의 BGR 이미지를 반환"""
    global _overlay_active
    if _overlay_active:
        return None
    _overlay_active = True
    try:
        # 전체 스냅샷
        ss = pyautogui.screenshot()
        frame = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2BGR)
        h, w, _ = frame.shape
        # QImage로 변환
        img = QImage(frame.data, w, h, 3 * w, QImage.Format_BGR888)

        overlay = QWidget()
        overlay.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        overlay.setAttribute(Qt.WA_TranslucentBackground, False)  # 투명 X (정지 화면 느낌)
        overlay.setAttribute(Qt.WA_DeleteOnClose, True)
        overlay.setGeometry(0, 0, w, h)
        overlay.start_pos = None
        overlay.end_pos = None
        overlay.is_dragging = False

        def paint_event(_):
            p = QPainter(overlay)
            # 정지 화면 배경만 그리기 (검정 마스크 제거)
            p.drawImage(0, 0, img)
            if overlay.start_pos and overlay.end_pos:
                x = min(overlay.start_pos.x(), overlay.end_pos.x())
                y = min(overlay.start_pos.y(), overlay.end_pos.y())
                rw = abs(overlay.end_pos.x() - overlay.start_pos.x())
                rh = abs(overlay.end_pos.y() - overlay.start_pos.y())
                # 빨간 테두리만 그리기
                p.setPen(QPen(QColor(255, 0, 0), 2))
                p.drawRect(x, y, rw, rh)

        def mouse_press(ev):
            if ev.button() == Qt.LeftButton:
                overlay.start_pos = ev.pos()
                overlay.end_pos = ev.pos()
                overlay.is_dragging = True
                overlay.update()

        def mouse_move(ev):
            if overlay.is_dragging:
                overlay.end_pos = ev.pos()
                overlay.update()

        def mouse_release(ev):
            if ev.button() == Qt.LeftButton and overlay.is_dragging:
                overlay.end_pos = ev.pos()
                overlay.is_dragging = False
                overlay.hide()

        overlay.paintEvent = paint_event
        overlay.mousePressEvent = mouse_press
        overlay.mouseMoveEvent = mouse_move
        overlay.mouseReleaseEvent = mouse_release

        overlay.show(); overlay.raise_(); overlay.activateWindow(); overlay.setFocus()
        # 메인 루프를 막지 않도록 처리
        from PyQt5.QtWidgets import QApplication
        while overlay.isVisible():
            QApplication.processEvents()

        if overlay.start_pos and overlay.end_pos:
            x = min(overlay.start_pos.x(), overlay.end_pos.x())
            y = min(overlay.start_pos.y(), overlay.end_pos.y())
            rw = abs(overlay.end_pos.x() - overlay.start_pos.x())
            rh = abs(overlay.end_pos.y() - overlay.start_pos.y())
            # 경계 보정 및 ROI 추출 (BGR)
            x0 = max(0, min(w-1, x))
            y0 = max(0, min(h-1, y))
            x1 = max(0, min(w, x + rw))
            y1 = max(0, min(h, y + rh))
            if x1 > x0 and y1 > y0:
                roi = frame[y0:y1, x0:x1].copy()
                return roi
        return None
    finally:
        _overlay_active = False


def capture_monster_region():
    """오버레이로 영역 선택 후 imgs/monster/monsterN.png 저장 (정지 화면에서 잘라 저장)"""
    roi_bgr = _start_freeze_overlay()
    if roi_bgr is None or roi_bgr.size == 0:
        return
    _ensure_dir()
    path = _next_path()
    cv2.imwrite(path, roi_bgr)
    training_fun.reload_monster_templates()


def clear_monsters():
    """imgs/monster 폴더 비우기"""
    if not os.path.isdir(MON_DIR):
        return
    for f in os.listdir(MON_DIR):
        if f.lower().endswith('.png'):
            try:
                os.remove(os.path.join(MON_DIR, f))
            except Exception:
                pass
    training_fun.reload_monster_templates()


def open_monster_folder():
    _ensure_dir()
    try:
        import sys, subprocess
        if os.name == 'nt':
            os.startfile(MON_DIR)  # Windows
        elif sys.platform == 'darwin':
            subprocess.call(['open', MON_DIR])
        else:
            subprocess.call(['xdg-open', MON_DIR])
    except Exception:
        pass


def _ensure_f5_poll_timer(parent_widget: QWidget):
    """GUI 스레드에서 keyboard.is_pressed('f5')를 폴링하여 캡처 실행"""
    global _f5_timer, _f5_pressed, _f5_last_t
    if _f5_timer is not None:
        try:
            if _f5_timer.isActive():
                return
        except Exception:
            pass
    try:
        import keyboard as _kb
    except Exception:
        return
    import time as _t
    _f5_pressed = False
    _f5_last_t = 0.0
    _f5_timer = QTimer(parent_widget)
    _f5_timer.setTimerType(Qt.PreciseTimer)
    _f5_timer.setInterval(30)

    def _on_tick():
        nonlocal _kb
        global _f5_pressed, _f5_last_t
        try:
            if _kb.is_pressed('f5'):
                now = _t.time()
                if (not _f5_pressed) and (not _overlay_active) and (now - _f5_last_t > 0.3):
                    capture_monster_region()
                    _f5_last_t = now
                    _f5_pressed = True
            else:
                _f5_pressed = False
        except Exception:
            pass

    _f5_timer.timeout.connect(_on_tick)
    _f5_timer.start()


def _stop_f5_timer():
    global _f5_timer
    try:
        if _f5_timer is not None:
            try:
                _f5_timer.stop()
            except Exception:
                pass
            try:
                _f5_timer.deleteLater()
            except Exception:
                pass
            _f5_timer = None
    except Exception:
        pass


def create_monster_buttons(parent_widget, anchor_widget):
    """IGN 캡처 버튼 아래에 몬스터 캡처/초기화 버튼 생성"""
    _ensure_dir()
    cap_btn = QPushButton('몬스터 캡처', parent_widget)
    cap_btn.setFixedSize(120, 30)
    cap_btn.setStyleSheet("QPushButton {background:#7d7d7d; color:white; border:none;} QPushButton:hover{background:#9e9e9e;} QPushButton:pressed{background:#5d5d5d;}")
    cap_btn.move(anchor_widget.x(), anchor_widget.y() + anchor_widget.height() + 5)
    cap_btn.clicked.connect(capture_monster_region)

    # F5 폴링 타이머 시작 (GUI 스레드에서 keyboard.is_pressed 방식)
    _ensure_f5_poll_timer(parent_widget)

    clr_btn = QPushButton('몬스터 초기화', parent_widget)
    clr_btn.setFixedSize(120, 30)
    clr_btn.setStyleSheet("QPushButton {background:#7f8c8d; color:white; border:none;} QPushButton:hover{background:#95a5a6;} QPushButton:pressed{background:#566573;}")
    clr_btn.move(cap_btn.x(), cap_btn.y() + cap_btn.height() + 5)
    clr_btn.clicked.connect(clear_monsters)

    open_btn = QPushButton('몬스터 폴더', parent_widget)
    open_btn.setFixedSize(120, 30)
    open_btn.setStyleSheet("QPushButton {background:#7f8c8d; color:white; border:none;} QPushButton:hover{background:#95a5a6;} QPushButton:pressed{background:#566573;}")
    open_btn.move(clr_btn.x(), clr_btn.y() + clr_btn.height() + 5)
    open_btn.clicked.connect(open_monster_folder)

    return cap_btn, clr_btn, open_btn
