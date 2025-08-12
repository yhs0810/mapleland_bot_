from PyQt5.QtWidgets import QFrame, QLabel, QLineEdit, QComboBox, QWidget
import threading, time
import pydirectinput as pdi
import minimap, current_f, boundary
import ladder

AVAILABLE_KEYS = [
    *[chr(c) for c in range(ord('a'), ord('z')+1)],
    *[str(d) for d in range(0,10)],
    *[f"f{i}" for i in range(1,13)],
    'escape','tab','enter','space','backspace','delete','insert','home','end','pageup','pagedown',
    'shift','ctrl','alt','lshift','rshift','lctrl','rctrl','lalt','ralt',
    'left','right','up','down'
]

_run_flag = False
_thread = None


def create_teleport_ui(parent: QWidget, anchor_frame: QFrame) -> QFrame:
    """펫먹이 프레임 바로 아래에 텔레포트 프레임 생성"""
    frame = QFrame(parent)
    frame.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    frame.setFixedHeight(36)
    # 초기 배치: anchor 바로 아래
    def _place():
        try:
            frame.setFixedWidth(anchor_frame.width())
            frame.move(anchor_frame.x(), anchor_frame.y() + anchor_frame.height() + 6)
        except Exception:
            pass
    _place()

    lbl = QLabel("텔레포트:", frame)
    lbl.setStyleSheet("color:#dcdcdc; font-size:9px;")
    lbl.move(6, 10)

    combo = QComboBox(frame); combo.addItem(""); combo.addItems(AVAILABLE_KEYS); combo.setFixedSize(70,14)
    combo.move(60, 10)

    lbl_d = QLabel("딜레이(초):", frame); lbl_d.setStyleSheet("color:#dcdcdc; font-size:9px;")
    lbl_d.move(140, 12)

    edit = QLineEdit(frame); edit.setFixedSize(40,12); edit.setText("30")
    edit.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:8px;}")
    edit.move(200, 12)

    frame.tp_combo = combo
    frame.tp_delay = edit
    frame.place_tele = _place

    return frame


def _is_blocked_by_bounds(cx: int) -> bool:
    """경계 근처(±20) 및 경계 밖 전체에서 텔레포트 금지"""
    try:
        fl = current_f.current_floor if current_f.current_floor else 1
        fi = getattr(boundary, 'FLOOR_INPUTS', {})
        if fl in fi:
            li, ri = fi[fl]
            l_val = int(li.text()) if li.text().isdigit() else None
            r_val = int(ri.text()) if ri.text().isdigit() else None
            # 경계 밖 전체 차단
            if l_val is not None and cx <= l_val:
                return True
            if r_val is not None and cx >= r_val:
                return True
            # 경계 ±20 차단
            if l_val is not None and (l_val + 1) <= cx <= (l_val + 20):
                return True
            if r_val is not None and (r_val - 20) <= cx <= (r_val - 1):
                return True
    except Exception:
        pass
    return False


def _is_blocked_by_ladder_zone(cx: int) -> bool:
    """사다리 목표층 기준으로 (목표층-1)의 해당 사다리 좌표 ±20 구간에서 텔레포트 금지"""
    try:
        cur_fl = current_f.current_floor if current_f.current_floor else 1
        for blk in getattr(ladder, 'ladder_blocks', []):
            try:
                target_str = blk.floor_edit.text() if hasattr(blk, 'floor_edit') else ''
                if not target_str or not target_str.isdigit():
                    continue
                target_fl = int(target_str)
                # 목표값/좌표가 있어야만 유효한 사다리로 간주
                if getattr(blk, 'goal_y', None) is None:
                    continue
                if getattr(blk, 'coord', None) is None:
                    continue
                bx = blk.coord[0]
                if cur_fl == (target_fl - 1) and abs(int(cx) - int(bx)) <= 20:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _loop(get_frame):
    global _run_flag
    next_t = 0.0
    while _run_flag:
        try:
            frame = get_frame()
            if frame is None:
                time.sleep(0.1); continue
            # 감지유지 타이머가 살아있으면 스킵 (텔레포트 금지)
            try:
                import start_stop as _ss
                if time.time() < getattr(_ss, 'STOP_DETECTED_UNTIL', 0.0):
                    time.sleep(0.05); continue
            except Exception:
                pass
            # 읽기
            key = frame.tp_combo.currentText() if hasattr(frame,'tp_combo') else ''
            try:
                d = float(frame.tp_delay.text()) if hasattr(frame,'tp_delay') and frame.tp_delay.text() else 0.0
            except Exception:
                d = 0.0
            # 빈 키 또는 0 이하 딜레이면 동작하지 않음
            if not key or d <= 0:
                time.sleep(0.1); continue
            # 경계/사다리 차단: 현재 x 가 금지 구간이면 스킵
            cx = getattr(minimap, 'current_x', None)
            if isinstance(cx, (int, float)):
                try:
                    cx_int = int(cx)
                    if _is_blocked_by_bounds(cx_int) or _is_blocked_by_ladder_zone(cx_int):
                        time.sleep(0.05); continue
                except Exception:
                    pass
            # 공격시멈추기 하드 차단: 바라보는 방향에만 몬스터가 있을 때만 유지되도록 추가 검증
            try:
                import start_stop as _ss
                if getattr(_ss, 'STOP_HARD_ACTIVE', False):
                    # 공격 루프가 바라보는 방향(ak._current_dir)과 반대쪽 몹이 동시에 있으면 해제
                    import sys
                    ak = sys.modules.get('attack_key')
                    ak_dir = getattr(ak, '_current_dir', None) if ak else None
                    mons = getattr(minimap, 'MON_POS', None)
                    # 안전하게 training_fun에서 가져오기
                    try:
                        import training_fun as _tf
                        mons = getattr(_tf, 'MON_POS', mons)
                        ign = getattr(_tf, 'CURRENT_IGN', None)
                    except Exception:
                        ign = None
                    has_left = has_right = False
                    if isinstance(mons, list) and ign:
                        ix, iy = ign
                        for mx, my in mons:
                            dx = mx - ix
                            if dx < 0:
                                has_left = True
                            elif dx > 0:
                                has_right = True
                    if ak_dir == 'left' and has_right:
                        _ss.STOP_HARD_ACTIVE = False
                    elif ak_dir == 'right' and has_left:
                        _ss.STOP_HARD_ACTIVE = False
                    # 하드가 유지중이면 텔레포트 금지
                    if getattr(_ss, 'STOP_HARD_ACTIVE', False):
                        time.sleep(0.05); continue
            except Exception:
                pass
            now = time.time()
            if now >= next_t:
                # 감지유지 타이머가 살아있으면 텔레포트 금지
                try:
                    import start_stop as _ss
                    if time.time() < getattr(_ss, 'STOP_DETECTED_UNTIL', 0.0):
                        time.sleep(0.02)
                        continue
                except Exception:
                    pass
                try:
                    pdi.press(key)
                except Exception:
                    pass
                next_t = now + max(0.1, d)
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
            bf = getattr(_m, 'buffs_frame', None)
            return getattr(bf, 'tele_frame', None)
        except Exception:
            return None
    _run_flag = True
    _thread = threading.Thread(target=_loop, args=(_get_frame,), daemon=True)
    _thread.start()


def stop():
    global _run_flag, _thread
    _run_flag = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=0.1)
    _thread = None
