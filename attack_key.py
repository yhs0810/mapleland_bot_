from PyQt5.QtWidgets import QFrame, QLabel, QLineEdit, QWidget, QComboBox
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtCore import Qt
import threading, time, random, sys
import pydirectinput as pdi
import attack_range, training_fun
import ctypes
import chasing_mob
import keep_go
import check_mob_both_side as both
import stop_no_mob

# low-level key handling
user32 = ctypes.windll.user32
VK_LEFT = 0x25; VK_RIGHT = 0x27
KEYEVENTF_KEYUP = 0x0002
DETECT_MARGIN = 2  # 경계 근처 몹 감지 비활성 마진(px)

def _key_down(vk):
    user32.keybd_event(vk,0,0,0)

def _key_up(vk):
    user32.keybd_event(vk,0,KEYEVENTF_KEYUP,0)

_run_flag = False
_attack_thread = None
_current_dir = None  # 'left' or 'right' or None
_dir_cooldown_until = 0.0
_chase_enabled = False  # 시작 시 체크박스 상태 고정
_chase_cooldown_until = 0.0  # 몹추적 방향 전환 쿨타임
_no_turn_enabled = False  # 시작 시 방향전환X 상태 고정
_both_detect_enabled = False  # 시작 시 양방향 감지 상태 고정

AVAILABLE_KEYS = [
    'a','b','c','d','e','f','g','h','i','j','k','l','m',
    'n','o','p','q','r','s','t','u','v','w','x','y','z',
    '0','1','2','3','4','5','6','7','8','9',
    'space','ctrl','shift','alt','tab','enter',
    'left','right','up','down'
]


def create_attack_ctrl_ui(parent: QWidget, left_frame: QFrame, nearest_label: QLabel):
    """Create UI frame for attack key/delay settings."""
    margin = 6
    x = left_frame.x() + left_frame.width() + margin
    y = left_frame.y()
    right_end = nearest_label.x() + nearest_label.width()
    width = max(140, right_end - x)
    height = left_frame.height()

    frame = QFrame(parent)
    frame.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    frame.setFixedSize(width, height)
    frame.move(x, y)

    # --- Widgets ---
    lbl_title = QLabel("공격 설정", frame)
    lbl_title.setStyleSheet("color:#f1c40f; font-size:12px; font-weight:bold;")
    lbl_title.move(6,2)

    lbl_key = QLabel("공격키:", frame)
    lbl_key.setStyleSheet("color:#dcdcdc; font-size:9px;")
    lbl_key.move(6, 25)

    combo_key = QComboBox(frame)
    combo_key.addItems(AVAILABLE_KEYS)
    combo_key.setFixedSize(60, 14)
    combo_key.move(frame.width()-71, 23)

    lbl_delay = QLabel("딜레이(초):", frame)
    lbl_delay.setStyleSheet("color:#dcdcdc; font-size:9px;")
    lbl_delay.move(6, 45)

    edit_delay_min = QLineEdit(frame); edit_delay_min.setFixedSize(28,12)
    edit_delay_min.setText("0.3")
    edit_delay_min.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:8px;}")
    edit_delay_min.move(frame.width()-70, 45)


    edit_delay_max = QLineEdit(frame); edit_delay_max.setFixedSize(28,12)
    edit_delay_max.setText("0.6")
    edit_delay_max.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:8px;}")
    edit_delay_max.move(frame.width()-40,45)

    # ----- 몹추적 체크박스 -----
    chk_chase = chasing_mob.create_chase_checkbox(frame)

    # 위치 기본
    chk_chase.move(6, 60)

    frame.chk_chase = chk_chase

    # ----- 공격시멈추기 체크박스 -----
    chk_stop_on_attack = QCheckBox("공격시멈추기", frame)
    chk_stop_on_attack.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
    chk_stop_on_attack.setChecked(False)
    # 몹추적 바로 아래 배치
    chk_stop_on_attack.move(6, 77)

    frame.chk_stop_on_attack = chk_stop_on_attack

    # ----- 방향전환X 체크박스 -----
    chk_no_turn = keep_go.create_no_turn_checkbox(frame)
    chk_no_turn.move(6, 94)
    frame.chk_no_turn = chk_no_turn

    # ----- 양방향감지 체크박스 -----
    chk_both = QCheckBox("양방향감지", frame)
    chk_both.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
    chk_both.setChecked(False)
    chk_both.move(6, 111)
    frame.chk_both_detect = chk_both

    # ----- 몹 미감지시 방향키 해제 -----
    chk_stop_no_mob = stop_no_mob.create_checkbox(frame)
    chk_stop_no_mob.move(6, 128)
    frame.chk_stop_no_mob = chk_stop_no_mob

    # Expose
    frame.combo_key = combo_key
    frame.edit_delay_min = edit_delay_min
    frame.edit_delay_max = edit_delay_max

    # Resize handler keeping right alignment
    def _resize():
        right_end = nearest_label.x() + nearest_label.width()
        new_w = max(140, right_end - frame.x())
        frame.setFixedWidth(new_w)
        combo_key.move(frame.width()-84,23)
        edit_delay_min.move(frame.width()-70,45)
        edit_delay_max.move(frame.width()-40,45)
        # 공격범위 프레임 하단 y와 동일하게 공격설정 프레임 하단 y를 맞춤
        try:
            import sys
            _m = sys.modules.get('__main__')
            atk_range_frame = getattr(_m, 'attack_range_frame', None)
            if atk_range_frame is not None:
                bottom = atk_range_frame.y() + atk_range_frame.height()
                # 현재 top은 동일, 높이를 bottom-top으로 재조정
                new_h = max(120, bottom - frame.y())
                frame.setFixedHeight(new_h)
        except Exception:
            pass
    orig = parent.resizeEvent if hasattr(parent,'resizeEvent') else None
    def new_resize(e):
        if orig: orig(e)
        _resize()
    parent.resizeEvent = new_resize

    return frame

# ---------------------------------------------------
# Attack thread logic
# ---------------------------------------------------

def _attack_loop():
    global _run_flag, _current_dir, _dir_cooldown_until, _chase_cooldown_until, _no_turn_enabled, _both_detect_enabled
    main_mod = sys.modules.get('__main__')
    atk_frame = getattr(main_mod, 'attack_key_frame', None)
    if atk_frame is None:
        _run_flag = False
        return
    global _current_dir, _dir_cooldown_until
    last_time = 0.0
    chase_keepalive_next = 0.0
    while _run_flag:
        zero_delay = False
        # --- Boundary check ---
        in_floor_bounds=True
        suppress_detect=False
        # stop_no_mob 체크 여부
        snm_enabled = bool(getattr(atk_frame, 'chk_stop_no_mob', None) and atk_frame.chk_stop_no_mob.isChecked())
        try:
            import minimap, current_f, boundary, buffs
            cx=minimap.current_x
            if cx is not None:
                fl=current_f.current_floor if current_f.current_floor else 1
                fi=getattr(boundary,'FLOOR_INPUTS',{})
                if fl in fi:
                    li,ri=fi[fl]
                    lval=int(li.text()) if li.text().isdigit() else None
                    rval=int(ri.text()) if ri.text().isdigit() else None
                    if (lval is not None and cx<=lval) or (rval is not None and cx>=rval):
                        in_floor_bounds=False
                    # 경계 근처 감지 억제: 왼쪽(l)에서는 l..l+10, 오른쪽(r)에서는 r-10..r 구간 포함
                    if (lval is not None and cx <= lval + DETECT_MARGIN) or (rval is not None and cx >= rval - DETECT_MARGIN):
                        suppress_detect = True
            # 몬스터 미감지 존 억제
            try:
                if not suppress_detect:
                    import ignore_mob as _ig
                    cy = getattr(minimap, 'current_y', None)
                    if isinstance(cx, (int,float)) and isinstance(cy, (int,float)):
                        if _ig.is_blocked(int(cx), int(cy)):
                            suppress_detect = True
            except Exception:
                pass
        except Exception:
            pass

        rng = attack_range.get_ranges(getattr(main_mod,'attack_range_frame',None))
        if rng is None:
            time.sleep(0.05); continue
        dy_min, dy_max, dx_lmin, dx_lmax, dx_rmin, dx_rmax, opp_detect = rng if len(rng)==7 else (*rng,0)
        ign = getattr(training_fun, 'CURRENT_IGN', None)
        mons = getattr(training_fun, 'MON_POS', [])
        # 경계/억제/IGN 없음 → 해제 우선 후 continue
        if ign is None or not in_floor_bounds or suppress_detect:
            try:
                stop_no_mob.update_pause_state(snm_enabled, None)
            except Exception:
                pass
            # 공격 범위 밖: 하드 차단 해제
            try:
                import start_stop as _ss
                _ss.STOP_HARD_ACTIVE = False
            except Exception:
                pass
            time.sleep(0.02); continue
        # 몬스터 리스트 없음 → 이동 정지 유지 후 continue
        if not mons:
            try:
                stop_no_mob.update_pause_state(snm_enabled, False)
            except Exception:
                pass
            # 공격 범위 밖: 하드 차단 해제
            try:
                import start_stop as _ss
                _ss.STOP_HARD_ACTIVE = False
            except Exception:
                pass
            time.sleep(0.02); continue
        ix, iy = ign
        in_box = False; has_left=False; has_right=False
        nearest_dx=None; nearest_dy=None
        # 현재 이동 방향(우선 start_stop.current_key)
        move_dir = None
        try:
            import start_stop as _ss
            move_dir = getattr(_ss, 'current_key', None)
        except Exception:
            move_dir = None
        if move_dir not in ('left','right'):
            move_dir = _current_dir
        # 반대몹 감지 적용: 진행 방향 반대쪽 범위를 opp_detect 로 제한
        adj_lmin = dx_lmin
        adj_rmax = dx_rmax
        if opp_detect and isinstance(opp_detect, int):
            if move_dir == 'right':
                adj_lmin = max(dx_lmin, -opp_detect)
            elif move_dir == 'left':
                adj_rmax = min(dx_rmax, opp_detect)
        # 방향전환X 활성 시, 현재 진행 방향 쪽 범위만 유효
        if _no_turn_enabled and move_dir in ('left','right'):
            if move_dir == 'right':
                # 오른쪽 측만: dx >= 0, 오른쪽 최소/최대만 반영
                adj_lmin = max(adj_lmin, max(0, dx_rmin))
                adj_rmax = max(dx_rmax, 0)
            else:
                # 왼쪽 측만: dx <= 0, 왼쪽 최소/최대만 반영
                adj_lmin = min(dx_lmin, 0)
                adj_rmax = min(adj_rmax, min(0, dx_lmax))
            # 단, 양방향감지 활성 시 좌우 모두 허용
            if both.is_both_active(_no_turn_enabled, _both_detect_enabled):
                adj_lmin, adj_rmax = both.adjust_detection_window(dx_lmin, dx_rmax)
        for mx,my in mons:
            dx = mx - ix; dy = my - iy
            if dy_min <= dy <= dy_max and adj_lmin <= dx <= adj_rmax:
                in_box = True
                if dx<0:
                    has_left=True
                elif dx>0:
                    has_right=True
            # chase 후보 추적 (가장 가까운 x 거리)
            if nearest_dx is None or abs(dx)<abs(nearest_dx):
                nearest_dx=dx; nearest_dy=dy

        # in_box 기준 하드 차단 토글: 공격범위 안이면 활성화, 밖이면 해제
        try:
            import start_stop as _ss
            # 기본 해제부터
            _ss.STOP_HARD_ACTIVE = False
            if in_box and hasattr(atk_frame,'chk_stop_on_attack') and atk_frame.chk_stop_on_attack.isChecked():
                # 현재 바라보는 방향(facing) 계산
                try:
                    import start_stop as __ss
                    facing = getattr(__ss, 'current_key', None)
                except Exception:
                    facing = None
                if facing not in ('left','right'):
                    facing = _current_dir
                # 바라보는 쪽에만 몬스터가 있을 때만 하드 차단
                if facing == 'left' and has_left and not has_right:
                    _ss.STOP_HARD_ACTIVE = True
                elif facing == 'right' and has_right and not has_left:
                    _ss.STOP_HARD_ACTIVE = True
        except Exception:
            pass

        # 몹 유무에 따른 이동정지/해제 처리 + 감지 유지 타이머 갱신
        try:
            stop_no_mob.update_pause_state(snm_enabled, in_box)
        except Exception:
            pass
        # 공격시멈추기 체크된 경우: in_box면 0.8초 타이머 갱신
        try:
            if hasattr(atk_frame,'chk_stop_on_attack') and atk_frame.chk_stop_on_attack.isChecked():
                import start_stop as _ss
                if in_box:
                    _ss.STOP_DETECTED_UNTIL = time.time() + 0.8
                else:
                    # in_box가 아닐 땐 타이머만 유지: 별도 해제 없음 (시간으로 만료)
                    pass
        except Exception:
            pass

        # STOP_MOVE 활성 중: 반대쪽에만 몬스터가 있고 공격범위에 든 경우 즉시 해제
        try:
            import start_stop as _ss
            if time.time() < getattr(_ss,'STOP_MOVE_UNTIL',0.0) and in_box:
                if move_dir == 'right' and has_left and not has_right:
                    _ss.STOP_MOVE_UNTIL = 0.0
                    _ss.STOP_SAVED_DIR = None
                    _ss.STOP_REQUEST_RELEASE = False
                elif move_dir == 'left' and has_right and not has_left:
                    _ss.STOP_MOVE_UNTIL = 0.0
                    _ss.STOP_SAVED_DIR = None
                    _ss.STOP_REQUEST_RELEASE = False
        except Exception:
            pass
        # 락 중에는 현재 진행 방향 쪽 몬스터만 허용
        try:
            import start_stop as _ss
            _lock_until = getattr(_ss, 'BOUND_LOCK_UNTIL', 0.0)
            _cur_move = getattr(_ss, 'current_key', None)
            if time.time() < _lock_until and _cur_move in ('left','right'):
                if _cur_move == 'left':
                    in_box = in_box and has_left
                elif _cur_move == 'right':
                    in_box = in_box and has_right
        except Exception:
            pass
        # ---------------------------------------------
        # chasing logic (옵션)
        chasing_active = False
        # 현재 이동 방향 결정 (start_stop 우선, 없으면 _current_dir)
        move_dir = None
        try:
            import start_stop as _ss
            move_dir = getattr(_ss, 'current_key', None)
        except Exception:
            move_dir = None
        if move_dir not in ('left','right'):
            move_dir = _current_dir

        # 반대몹 감지 창문 체크
        opp_ok = False
        if nearest_dx is not None and opp_detect and dy_min <= nearest_dy <= dy_max:
            if move_dir == 'right':
                # 왼쪽 창문: [-opp, 0)
                opp_ok = (-opp_detect <= nearest_dx < 0)
            elif move_dir == 'left':
                # 오른쪽 창문: (0, +opp]
                opp_ok = (0 < nearest_dx <= opp_detect)

        if not in_box and _chase_enabled and opp_ok and not _no_turn_enabled:
            now = time.time()
            # 쿨타임 확인 후 방향 전환 신호만 갱신
            if now >= _chase_cooldown_until:
                # 이동 정지 중에는 전환 신호 갱신 보류
                try:
                    import start_stop as _ss
                    if now < getattr(_ss,'STOP_MOVE_UNTIL',0.0):
                        pass
                    else:
                        if move_dir == 'right' and nearest_dx < 0 and _current_dir != 'left':
                            _current_dir='left'; _dir_cooldown_until = now+0.2; _chase_cooldown_until = now + 3.0
                        elif move_dir == 'left' and nearest_dx > 0 and _current_dir != 'right':
                            _current_dir='right'; _dir_cooldown_until = now+0.2; _chase_cooldown_until = now + 3.0
                except Exception:
                    if move_dir == 'right' and nearest_dx < 0 and _current_dir != 'left':
                        _current_dir='left'; _dir_cooldown_until = now+0.2; _chase_cooldown_until = now + 3.0
                    elif move_dir == 'left' and nearest_dx > 0 and _current_dir != 'right':
                        _current_dir='right'; _dir_cooldown_until = now+0.2; _chase_cooldown_until = now + 3.0
            chasing_active = True
        now=time.time()

        # --- direction control (signal only; 실제 키 입력은 start_stop이 수행) ---
        if in_box and in_floor_bounds and not _no_turn_enabled:
            desired = None
            if has_left and not has_right:
                desired = 'left'
            elif has_right and not has_left:
                desired = 'right'
            # 둘 다 있으면 전환하지 않음

            now = time.time()
            if desired and desired != _current_dir and now >= _dir_cooldown_until:
                _current_dir = desired; _dir_cooldown_until = now + 0.2
            elif _current_dir is None:
                # 초기 방향 선택 (가능한 쪽)
                if has_left:
                    _current_dir='left'; _dir_cooldown_until = time.time()+0.2
                elif has_right:
                    _current_dir='right'; _dir_cooldown_until = time.time()+0.2
        else:
            # 박스 밖: chasing 중이면 유지, 아니면 초기화
            if not chasing_active:
                _current_dir=None
                # 공격 범위 밖: 하드 차단 해제
                try:
                    import start_stop as _ss
                    _ss.STOP_HARD_ACTIVE = False
                except Exception:
                    pass

        if in_box and in_floor_bounds and now - last_time >= 0 and time.time() >= getattr(buffs,'BUFF_BLOCK_ATTACK_UNTIL',0.0):
            try:
                key = atk_frame.combo_key.currentText()
                # pydirectinput uses 'left','right' etc for arrows OK
                try:
                    dmin = float(atk_frame.edit_delay_min.text()) if atk_frame.edit_delay_min.text() else 0.3
                except Exception:
                    dmin = 0.3
                try:
                    dmax = float(atk_frame.edit_delay_max.text()) if atk_frame.edit_delay_max.text() else 0.6
                except Exception:
                    dmax = 0.6
                zero_delay = (dmin == 0.0 and dmax == 0.0)
                # 공격시멈추기: 체크 시 이동 정지 요청 + 하드 차단 트리거
                try:
                    if hasattr(atk_frame,'chk_stop_on_attack') and atk_frame.chk_stop_on_attack.isChecked():
                        import start_stop as _ss
                        # 첫 만족 시 현재 방향 저장 및 즉시 업 요청
                        if _ss.STOP_MOVE_UNTIL <= time.time():
                            _ss.STOP_SAVED_DIR = _ss.current_key if _ss.current_key in ('left','right') else None
                            _ss.STOP_REQUEST_RELEASE = True
                        # 0.8초 연장
                        _ss.STOP_MOVE_UNTIL = time.time() + 0.23
                except Exception:
                    pass
                pdi.press(key)
                last_time = now + max(0.0, random.uniform(dmin, dmax))
            except Exception:
                pass
        time.sleep(0 if zero_delay else 0.01)

    # thread end: 방향 신호만 초기화 (실제 키 업은 start_stop 에서 처리)
    _current_dir=None


def start_attack():
    global _run_flag, _attack_thread, _chase_enabled, _chase_cooldown_until, _no_turn_enabled, _both_detect_enabled
    if _run_flag:
        return
    _run_flag = True
    # 시작 시 체크박스 상태 캡처(런타임 토글 무시)
    try:
        main_mod = sys.modules.get('__main__')
        atk_frame = getattr(main_mod, 'attack_key_frame', None)
        _chase_enabled = bool(getattr(atk_frame, 'chk_chase', None) and atk_frame.chk_chase.isChecked())
        _no_turn_enabled = bool(getattr(atk_frame, 'chk_no_turn', None) and atk_frame.chk_no_turn.isChecked())
        _both_detect_enabled = bool(getattr(atk_frame, 'chk_both_detect', None) and atk_frame.chk_both_detect.isChecked())
    except Exception:
        _chase_enabled = False; _no_turn_enabled = False; _both_detect_enabled = False
    _chase_cooldown_until = 0.0
    _attack_thread = threading.Thread(target=_attack_loop, daemon=True)
    _attack_thread.start()


def stop_attack():
    global _run_flag, _attack_thread
    _run_flag = False
    if _attack_thread and _attack_thread.is_alive():
        _attack_thread.join(timeout=0.1)
    _attack_thread = None 