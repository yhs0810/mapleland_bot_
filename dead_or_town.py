from PyQt5.QtWidgets import QCheckBox, QLabel, QFrame, QWidget
import pyautogui
import time
import os
import threading
import cv2
import numpy as np
import pygame

# 템플릿 경로
_DEAD_PATH = os.path.join('imgs', 'dead', 'dead.png')
_TOWN_PATH = os.path.join('imgs', 'dead', 'town.png')
_ALARM_PATH = os.path.join('imgs', 'alarm', 'alarm.mp3')

# 임계값
THRESHOLD = 0.93
COOLDOWN_SEC = 1.5

# 전역 상태
_run = False
_thread = None
_last_alarm = 0.0
_enabled_on_start = False
# 텔레그램 쿨타임 전역(맵/마을)
_TG_MAP_LAST = 0.0

# UI 참조
chk_dead_town = None  # QCheckBox
lbl_status = None     # QLabel

# 템플릿 캐시
_dead_tmpl = None
_town_tmpl = None


def _load_templates():
    global _dead_tmpl, _town_tmpl
    if _dead_tmpl is None and os.path.exists(_DEAD_PATH):
        img = cv2.imread(_DEAD_PATH, cv2.IMREAD_COLOR)
        if img is not None and img.size > 0:
            _dead_tmpl = img
    if _town_tmpl is None and os.path.exists(_TOWN_PATH):
        img = cv2.imread(_TOWN_PATH, cv2.IMREAD_COLOR)
        if img is not None and img.size > 0:
            _town_tmpl = img


def create_ui(parent_frame: QFrame, anchor_checkbox: QCheckBox):
    """플레이어 알람 프레임 내부에 UI 추가 (체크박스+상태 레이블)"""
    global chk_dead_town, lbl_status
    chk_dead_town = QCheckBox("맵 변경 감지", parent_frame)
    chk_dead_town.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
    # anchor 바로 아래 배치 (추가로 2px 더 아래)
    try:
        ybase = anchor_checkbox.y() + anchor_checkbox.height() + 5
    except Exception:
        ybase = 28
    chk_dead_town.move(anchor_checkbox.x(), ybase)

    # __main__에 전역 노출 (저장/복원 용)
    try:
        import sys
        _m = sys.modules.get('__main__')
        setattr(_m, 'dead_town_check_box', chk_dead_town)
        setattr(_m, 'dead_town_status_label', lbl_status)
    except Exception:
        pass

    return chk_dead_town, lbl_status


def _maybe_alarm(tag: str):
    global _last_alarm
    now = time.time()
    if now - _last_alarm < COOLDOWN_SEC:
        return
    # 상태 레이블 갱신
    try:
        if lbl_status is not None:
            lbl_status.setText(f"맵 변경: {tag}")
    except Exception:
        pass
    # mp3 재생
    try:
        if os.path.exists(_ALARM_PATH):
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            sound = pygame.mixer.Sound(_ALARM_PATH)
            sound.play()
    except Exception:
        pass
    _last_alarm = now
    # 텔레그램 전송 (맵 또는 마을 감지!) - 5초 쿨타임
    try:
        # 텔레그램 5초 쿨타임
        global _TG_MAP_LAST
        if now - _TG_MAP_LAST >= 5.0:
            try:
                import telegram as _tg
                if _tg.is_configured():
                    _tg.send_message_async('맵 변경, 죽었거나 마을 감지 매크로 즉시 정지!')
            except Exception:
                pass
            _TG_MAP_LAST = now
    except Exception:
        pass
    # 전체 동작 정지 (정지 버튼 누른 효과)
    try:
        import sys
        _m = sys.modules.get('__main__')
        # main에서 생성한 정지 버튼 시뮬레이션
        stop_btn = getattr(_m, 'stop_button_instance', None)
        if stop_btn and hasattr(stop_btn, 'click'):
            stop_btn.click()
        else:
            # fallback: F1 토글 두 번(시작 상태일 수 있어 2회로 보장)
            try:
                import start_stop as _ss
                # 내부 토글 호출 경유 (키 이벤트 대신 직접)
                if getattr(_ss, '_run_flag', False):
                    try:
                        if _ss._kb:
                            _ss._kb.send('f1')
                            time.sleep(0.05)
                            _ss._kb.send('f1')
                        else:
                            setattr(_ss, '_run_flag', False)
                            try:
                                _ss._release_all()
                            except Exception:
                                pass
                    except Exception:
                        setattr(_ss, '_run_flag', False)
                        try:
                            _ss._release_all()
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass


def _detect_in_frame(frame_bgr):
    # OpenCL 가속 사용 (가능 시)
    try:
        if cv2.ocl.haveOpenCL():
            cv2.ocl.setUseOpenCL(True)
    except Exception:
        pass

    found = None
    try:
        if _dead_tmpl is not None:
            src = frame_bgr
            res = cv2.matchTemplate(src, _dead_tmpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if max_val >= THRESHOLD:
                found = 'DEAD'
        if found is None and _town_tmpl is not None:
            src = frame_bgr
            res = cv2.matchTemplate(src, _town_tmpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if max_val >= THRESHOLD:
                found = 'TOWN'
    except Exception:
        found = None
    return found


def _loop():
    global _run, _enabled_on_start
    _load_templates()
    while _run:
        try:
            # 체크박스 현재 상태를 매 주기마다 확인 (토글 즉시 반영)
            enabled = False
            try:
                enabled = bool(chk_dead_town and chk_dead_town.isChecked())
            except Exception:
                enabled = False
            if not enabled:
                time.sleep(0.3)
                continue
            # 스크린샷 (전체 화면)
            shot = pyautogui.screenshot()
            frame = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
            tag = _detect_in_frame(frame)
            if tag is not None:
                _maybe_alarm(tag)
        except Exception:
            pass
        time.sleep(0.2)


def start():
    global _run, _thread, _enabled_on_start
    if _run:
        return
    _enabled_on_start = False  # 더 이상 사용하지 않지만 하위 호환 보존
    _run = True
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop():
    global _run, _thread
    _run = False
    if _thread and _thread.is_alive():
        try:
            _thread.join(timeout=0.1)
        except Exception:
            pass
    _thread = None
