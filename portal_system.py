from PyQt5.QtWidgets import QFrame, QPushButton, QLabel, QWidget
import threading, time
import pydirectinput as pdi

# 런타임
_run_flag = False
_thread = None


def create_portal_ui(parent: QWidget, anchor_widget: QWidget) -> QFrame:
    frame = QFrame(parent)
    frame.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")

    title = QLabel("포탈", frame)
    title.setStyleSheet("color:#dcdcdc; font-size:10px; font-weight:bold;")
    title.move(6, 4)

    buttons = []
    coords = [None] * 5  # 5개로 확장

    def _capture(i: int):
        try:
            import minimap
            cx = getattr(minimap, 'current_x', None)
            cy = getattr(minimap, 'current_y', None)
            if (cx is None or cy is None) and hasattr(minimap, 'canvas_widget'):
                cw = getattr(minimap, 'canvas_widget', None)
                if cw is not None and hasattr(cw, 'last_cx'): cx = cw.last_cx
                if cw is not None and hasattr(cw, 'last_cy'): cy = cw.last_cy
            if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
                ix, iy = int(cx), int(cy)
                coords[i] = (ix, iy)
                try:
                    buttons[i].setText(f"P ({ix},{iy})")
                except Exception:
                    pass
        except Exception:
            pass

    # 가변 배치/크기
    def _place():
        try:
            fw = max(120, anchor_widget.width() + 126)
            frame.setFixedSize(fw, 72)
            frame.move(anchor_widget.x(), anchor_widget.y() + anchor_widget.height() + 9)
            margin = 6
            gap = 6
            usable = fw - margin*2
            n = max(1, len(buttons))
            bw = max(28, int((usable - gap*(n-1)) // n))
            bh = 16
            y_btn = 24
            x0 = margin
            for i, btn in enumerate(buttons):
                btn.setFixedSize(bw, bh)
                btn.move(x0 + i*(bw+gap), y_btn)
            # 초기화 버튼 폭/위치 동기화
            reset_btn.setFixedSize(fw - margin*2, 18)
            reset_btn.move(margin, y_btn + bh + 4)
        except Exception:
            pass

    for i in range(5):
        btn = QPushButton("P", frame)
        btn.setStyleSheet("QPushButton {background:#7d7d7d; color:white; border:none; font-size:9px;} QPushButton:hover{background:#9e9e9e;} QPushButton:pressed{background:#5d5d5d;}")
        btn.clicked.connect(lambda _, idx=i: _capture(idx))
        buttons.append(btn)

    # 초기화 버튼
    reset_btn = QPushButton("초기화", frame)
    reset_btn.setStyleSheet("QPushButton {background:#e74c3c; color:white; border:none; font-size:10px;} QPushButton:hover{background:#ec7063;} QPushButton:pressed{background:#c0392b;}")

    def _reset():
        for i in range(len(coords)):
            coords[i] = None
            try:
                buttons[i].setText("P")
            except Exception:
                pass
    reset_btn.clicked.connect(_reset)

    frame.portal_buttons = buttons
    frame.portal_coords = coords
    frame.place_portal = _place

    _place()
    return frame


def _match(cx:int, cy:int, pt):
    if pt is None:
        return False
    x0, y0 = pt
    return (cx == x0) and (abs(cy - y0) <= 3)


def _loop(get_frame):
    global _run_flag
    next_ok = []
    last_match = []
    while _run_flag:
        try:
            frame = get_frame()
            if not frame:
                time.sleep(0.1); continue
            # 시작 상태에서만 동작
            try:
                import start_stop as ss
                if not getattr(ss, '_run_flag', False):
                    time.sleep(0.1); continue
            except Exception:
                time.sleep(0.1); continue
            # 좌표 읽기
            try:
                import minimap
                cx = getattr(minimap, 'current_x', None)
                cy = getattr(minimap, 'current_y', None)
                if cx is None or cy is None:
                    time.sleep(0.02); continue
                cx = int(cx); cy = int(cy)
            except Exception:
                time.sleep(0.05); continue
            now = time.time()
            n = len(getattr(frame, 'portal_coords', []) or [])
            # 배열 크기 동기화
            if len(next_ok) != n:
                next_ok = [0.0] * n
                last_match = [False] * n
            for i in range(n):
                pt = frame.portal_coords[i] if hasattr(frame,'portal_coords') else None
                if pt is None:
                    last_match[i] = False
                    continue
                m = _match(cx, cy, pt)
                if m and not last_match[i] and now >= next_ok[i]:
                    try:
                        pdi.keyDown('up'); time.sleep(0.02)
                    except Exception:
                        pass
                    finally:
                        try: pdi.keyUp('up')
                        except Exception: pass
                    next_ok[i] = now + 3.5
                last_match[i] = m
        except Exception:
            pass
        time.sleep(0.02)


def start():
    global _run_flag, _thread
    if _run_flag:
        return
    def _get_frame():
        try:
            import sys
            _m = sys.modules.get('__main__')
            return getattr(_m, 'portal_frame', None)
        except Exception:
            return None
    _run_flag = True
    _thread = threading.Thread(target=_loop, args=(_get_frame,), daemon=True)
    _thread.start()


def stop():
    global _run_flag, _thread
    _run_flag = False
    try:
        if _thread and _thread.is_alive():
            _thread.join(timeout=0.1)
    except Exception:
        pass
    _thread = None 