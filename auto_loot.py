from PyQt5.QtWidgets import QFrame, QLabel, QLineEdit, QComboBox, QWidget, QCheckBox
import threading, time
import pydirectinput as pdi

AVAILABLE_KEYS = [
    '',  # 비선택 허용
    *[chr(c) for c in range(ord('a'), ord('z')+1)],
    *[str(d) for d in range(0,10)],
    *[f"f{i}" for i in range(1,13)],
    'escape','tab','enter','space','backspace','delete','insert','home','end','pageup','pagedown',
    'shift','ctrl','alt','lshift','rshift','lctrl','rctrl','lalt','ralt',
    'left','right','up','down'
]

_run_flag = False
_thread = None
_started = False  # start_stop.start()에 연동해 시작 중일 때만 동작


def create_auto_loot_ui(parent: QWidget, anchor_frame: QFrame) -> QFrame:
    frame = QFrame(parent)
    frame.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    frame.setFixedHeight(36)

    def _place():
        try:
            frame.setFixedWidth(anchor_frame.width())
            frame.move(anchor_frame.x(), anchor_frame.y() + anchor_frame.height() + 6)
        except Exception:
            pass
    _place()

    lbl = QLabel("자동줍기:", frame)
    lbl.setStyleSheet("color:#dcdcdc; font-size:9px;")
    lbl.move(6, 10)

    combo = QComboBox(frame); combo.addItems(AVAILABLE_KEYS); combo.setFixedSize(70,14)
    combo.move(60, 10)

    lbl_d = QLabel("딜레이(초):", frame); lbl_d.setStyleSheet("color:#dcdcdc; font-size:9px;")
    lbl_d.move(140, 12)

    edit = QLineEdit(frame); edit.setFixedSize(40,12); edit.setText("0.5")
    edit.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:8px;}")
    edit.move(200, 12)

    frame.loot_combo = combo
    frame.loot_delay = edit
    frame.place_loot = _place
    return frame


def _loop(get_frame):
    global _run_flag
    next_t = 0.0
    while _run_flag:
        try:
            frame = get_frame()
            if frame is None:
                time.sleep(0.1); continue
            # 시작 상태가 아니면 비활성
            if not _started:
                time.sleep(0.1); continue
            key = frame.loot_combo.currentText() if hasattr(frame,'loot_combo') else ''
            try:
                d = float(frame.loot_delay.text()) if hasattr(frame,'loot_delay') and frame.loot_delay.text() else 0.0
            except Exception:
                d = 0.0
            # 키가 비어있거나 딜레이가 0 이하이면 동작 안 함
            if not key or d <= 0:
                time.sleep(0.1); continue
            now = time.time()
            if now >= next_t:
                # keyDown/Up 방식으로 짧게 누르기 (딜레이의 10%를 홀드, 10~50ms 범위)
                hold = max(0.01, min(0.05, d * 0.1))
                try:
                    pdi.keyDown(key)
                    time.sleep(hold)
                except Exception:
                    pass
                finally:
                    try:
                        pdi.keyUp(key)
                    except Exception:
                        pass
                next_t = now + max(0.05, d)
        except Exception:
            pass
        time.sleep(0.02)


def start():
    global _run_flag, _thread, _started
    _started = True
    if _run_flag:
        return
    def _get_frame():
        try:
            import sys
            _m = sys.modules.get('__main__')
            bf = getattr(_m, 'buffs_frame', None)
            return getattr(bf, 'loot_frame', None)
        except Exception:
            return None
    _run_flag = True
    _thread = threading.Thread(target=_loop, args=(_get_frame,), daemon=True)
    _thread.start()


def stop():
    global _run_flag, _thread, _started
    _started = False
    _run_flag = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=0.1)
    _thread = None 