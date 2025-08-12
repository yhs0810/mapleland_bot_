from PyQt5.QtWidgets import QPushButton, QShortcut, QWidget, QAction, QApplication, QLineEdit, QCheckBox, QLabel
from PyQt5.QtCore import Qt, QObject, QEvent
from PyQt5.QtGui import QKeySequence
import threading, time, random
import ctypes
import pydirectinput as pdi
import os
try:
    import keyboard as _kb
except ImportError:
    _kb = None
from numba import njit, int32
import minimap
import current_f
import ladder
import jump_down
import training_fun  # 사냥구역 저장/불러오기

# ----- 전역 가드/참조 -----
F1_DISABLED = False
_TOP_WINDOW = None
_START_FN = None
_STOP_FN = None
_SET_CONTROLS_ENABLED = None
_RESET_ALL_FN = None
_START_BUTTON = None
_STOP_BUTTON = None


def disable_f1_toggle():
    """F1 토글을 완전히 비활성화한다 (가드 플래그만 사용)."""
    global F1_DISABLED
    F1_DISABLED = True


def enable_f1_toggle():
    """필요 시 F1 토글을 다시 허용한다."""
    global F1_DISABLED
    F1_DISABLED = False


def disable_all_and_stop():
    """모든 매크로/스레드를 정지시키고 F1 토글을 끈다. UI 컨트롤도 비활성화하고 가능한 한 초기화한다."""
    global _STOP_FN, _SET_CONTROLS_ENABLED, _RESET_ALL_FN, _START_BUTTON, _STOP_BUTTON
    try:
        # 메인 모듈 전역 가드도 켬
        import sys as _sys
        _m = _sys.modules.get('__main__')
        setattr(_m, 'F1_DISABLED', True)
    except Exception:
        pass
    try:
        disable_f1_toggle()
    except Exception:
        pass
    # 먼저 정지
    try:
        if _STOP_FN:
            _STOP_FN()
        else:
            from sys import modules as _mods
            _m = _mods.get(__name__)
            if hasattr(_m, '_run_flag') and getattr(_m, '_run_flag'):
                setattr(_m, '_run_flag', False)
            _release_all()
    except Exception:
        pass
    # 가능한 한 전체 초기화
    try:
        if _RESET_ALL_FN:
            _RESET_ALL_FN()
    except Exception:
        pass
    # 컨트롤 비활성화
    try:
        if _SET_CONTROLS_ENABLED:
            _SET_CONTROLS_ENABLED(False)
    except Exception:
        pass
    # 시작/정지 버튼까지 모두 비활성화
    try:
        if _START_BUTTON: _START_BUTTON.setEnabled(False)
        if _STOP_BUTTON: _STOP_BUTTON.setEnabled(False)
    except Exception:
        pass

# SendInput / keybd_event 설정
user32 = ctypes.windll.user32
KEYEVENTF_KEYUP = 0x0002
VK_LEFT = 0x25
VK_RIGHT = 0x27

# 경계 판정 시 여유 픽셀(진동 방지)
BOUND_MARGIN = 2  # px

# 정지 좌표 모니터 스레드 상태
_idle_thread = None
_idle_run = False


def _key_down(vk):
    user32.keybd_event(vk, 0, 0, 0)
    pressed_keys.add(vk)


def _key_up(vk):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    pressed_keys.discard(vk)
    # 반대 방향 자동 누름 제거: 방향 전환은 _press()에서 관리함


# alt tap helper
def _tap_alt():
    user32.keybd_event(0x12, 0x38, 0, 0)  # down
    user32.keybd_event(0x12, 0x38, KEYEVENTF_KEYUP, 0)  # up


def _idle_monitor_loop():
    """미니맵 좌표가 10초 동안 동일하면 alt 1회 누르기 (중복 방지)"""
    global _idle_run
    last = None
    last_change = time.time()
    alt_sent_at = 0.0
    while _idle_run:
        try:
            cx = getattr(minimap, 'current_x', None)
            cy = getattr(minimap, 'current_y', None)
            if cx is None or cy is None:
                time.sleep(0.2)
                continue
            cur = (int(cx), int(cy))
            if last is None:
                last = cur
                last_change = time.time()
            elif cur != last:
                last = cur
                last_change = time.time()
            else:
                # 좌표 유지 시간
                if time.time() - last_change >= 10.0:
                    # 최근 20초 내에 ALT 보낸 적 없을 때만 1회 전송
                    if time.time() - alt_sent_at >= 20.0:
                        _tap_alt()
                        alt_sent_at = time.time()
                        # 이후 다시 10초를 기다리도록 기준 갱신
                        last_change = time.time()
            time.sleep(0.2)
        except Exception:
            time.sleep(0.2)


# 전역 상태
_run_flag = False
_control_thread = None
current_key = None  # 현재 누르고 있는 방향키("left" 또는 "right")
# 모든 누르고 있는 가상키 코드를 저장
pressed_keys = set()
BOUND_LOCK_UNTIL = 0.0  # 경계 복귀 후 방향 고정 락(진동 방지)
# 공격 시 잠시 이동 중지 기능 (외부에서 타이머만 설정)
STOP_MOVE_UNTIL = 0.0      # 이 시간이 지날 때까지 이동키 Down 금지
STOP_SAVED_DIR = None      # 재개 시 복원할 방향('left'/'right')
STOP_REQUEST_RELEASE = False  # True 시 즉시 현재 방향키 Up 처리 후 False로 초기화
# 공격시멈추기(하드) 조건일 때 이동/텔레포트 전면 금지
STOP_HARD_ACTIVE = False
# 마지막 몬스터 공격범위 감지 유지 타이머 (stop_on_attack용)
STOP_DETECTED_UNTIL = 0.0
# 경계 복귀 시 텔레포트 스팸 간격 타이머
OOB_TP_NEXT = 0.0


# numba 가속 방향 판단 함수: 1 = 오른쪽, -1 = 왼쪽, 0 = 유지
@njit(int32(int32, int32, int32), cache=True)
def _determine_dir(cx, l_val, r_val):
    """경계 밖 방향 판정.
    l_val, r_val 은 실제 경계 좌표. 여유 마진(BOUND_MARGIN) 만큼 안쪽으로 들어와야 OOB 해제.
    """
    if l_val >= 0 and cx <= l_val - BOUND_MARGIN:
        return 1  # move right
    if r_val >= 0 and cx >= r_val + BOUND_MARGIN:
        return -1  # move left
    return 0  # keep


@njit(cache=True)
def _within3(a:int32,b:int32)->int32:
    diff=a-b
    if diff<0:
        diff = -diff
    return 1 if diff<=3 else 0

# 빠른 트리거 판정
@njit(int32(int32,int32,int32,int32), cache=True)
def _coord_match(cx, cy, x0, y0):
    # x 값은 정확히 일치, y 는 ±3 허용
    return 1 if (cx == x0 and _within3(cy, y0)) else 0

# diff<=2 helper
@njit(cache=True)
def _within2(a:int32,b:int32)->int32:
    diff=a-b
    if diff<0:
        diff=-diff
    return 1 if diff<=2 else 0


# pydirectinput 사용하여 키 입력 처리
def _press(dir_name):
    """현재 키 상태에 따라 눌림/뗌 관리 후 해당 키를 Down 상태로 유지"""
    global current_key
    if dir_name=="up":
        pdi.keyDown("up")
        return
    # 동일 방향이면 아무 동작 안 함 (재전송 제거)
    if current_key == dir_name:
        return
    # 기존 방향 키 해제 후 새 방향 키 다운
    if current_key:
        _key_up(VK_LEFT if current_key == "left" else VK_RIGHT)
    _key_down(VK_LEFT if dir_name == "left" else VK_RIGHT)
    current_key = dir_name


def _release_all():
    global current_key
    # 모든 저장된 키 업
    for vk in list(pressed_keys):
        _key_up(vk)
    current_key = None


def _control_loop(l_input, r_input, floor_inputs):
    global _run_flag, current_key, BOUND_LOCK_UNTIL, STOP_MOVE_UNTIL, STOP_SAVED_DIR, STOP_REQUEST_RELEASE
    # 초기 방향: 왼쪽/오른쪽 랜덤
    direction = random.choice(["left", "right"])
    _press(direction)
    next_keepalive = time.time() + 0.1
    prev_floor = current_f.current_floor
    # 경계 밖 상태 캐시 (0=안쪽, 1=왼쪽 밖->오른쪽 필요, -1=오른쪽 밖->왼쪽 필요)
    next_oob_check = 0.0
    cached_oob_dir = 0

    ignore_until = {b:0.0 for b in ladder.ladder_blocks}
    jd_ignore_until = {b:0.0 for b in jump_down.jump_blocks}
    # 몬스터 감지 일시중지 타이머 (층 전환 안정화용)
    MON_DETECT_RESUME_AT = 0.0
    last_floor_seen = current_f.current_floor
    # 점프다운 재시도 상태
    JD_RETRY_ACTIVE = False
    JD_RETRY_DEADLINE = 0.0  # deprecated: 무제한 재시도로 전환
    JD_RETRY_FROM_FLOOR = None
    JD_RETRY_NEXT = 0.0
    JD_STEPS_TOTAL = 0   # 목표 층 변경 횟수 (2/3/4)
    JD_STEPS_DONE = 0    # 현재까지 감지된 층 변경 횟수
    JD_ACTIVE_BLOCK = None
    while _run_flag:
        try:
            cx = minimap.current_x
            cy = minimap.current_y
            now_global = time.time()

            # 몬스터 감지 일시중지 처리 제거
            MON_DETECT_RESUME_AT = 0.0

            # JD HOLD 모드: ALT 스팸 + DOWN 유지, 목표 변경 횟수 달성 시 해제
            try:
                if JD_RETRY_ACTIVE:
                    curf = current_f.current_floor
                    # 1층 감지 시 즉시 중단
                    if curf == 1:
                        try: _key_up(0x28)
                        except Exception: pass
                        JD_RETRY_ACTIVE = False
                        JD_RETRY_FROM_FLOOR = None
                        JD_STEPS_TOTAL = 0
                        JD_STEPS_DONE = 0
                        JD_RETRY_NEXT = 0.0
                    else:
                        # 층 변경 감지 → 카운트 증가
                        if curf is not None and JD_RETRY_FROM_FLOOR is not None and curf != JD_RETRY_FROM_FLOOR:
                            JD_STEPS_DONE += 1
                            JD_RETRY_FROM_FLOOR = curf
                        # 목표 도달 여부
                        if JD_STEPS_TOTAL > 0 and JD_STEPS_DONE >= JD_STEPS_TOTAL:
                            try: _key_up(0x28)
                            except Exception: pass
                            JD_RETRY_ACTIVE = False
                            JD_RETRY_FROM_FLOOR = None
                            JD_STEPS_TOTAL = 0
                            JD_STEPS_DONE = 0
                            JD_RETRY_NEXT = 0.0
                        else:
                            # ALT 스팸 + DOWN 유지
                            if time.time() >= JD_RETRY_NEXT:
                                _tap_alt()
                                JD_RETRY_NEXT = time.time() + 0.2
                            _key_down(0x28)
                else:
                    JD_RETRY_NEXT = 0.0
            except Exception:
                pass

            # 외부 요청 시 즉시 현재 이동키 해제
            if STOP_REQUEST_RELEASE:
                if current_key == "left":
                    _key_up(VK_LEFT); current_key=None
                elif current_key == "right":
                    _key_up(VK_RIGHT); current_key=None
                STOP_REQUEST_RELEASE = False

            # 하드 차단 중이면 방향키 Down 전면 차단 (유지/전환 모두 금지)
            if STOP_HARD_ACTIVE:
                if current_key == "left":
                    _key_up(VK_LEFT); current_key=None
                elif current_key == "right":
                    _key_up(VK_RIGHT); current_key=None
                time.sleep(0.05)
                continue

            # 현재 층 기준 경계 입력 선택
            cur_floor_num = current_f.current_floor if current_f.current_floor else 1
            cur_inputs = floor_inputs.get(cur_floor_num, (l_input, r_input))
            cur_l_input, cur_r_input = cur_inputs
            # 층 변경 감지
            if current_f.current_floor != prev_floor and current_f.current_floor is not None:
                prev_floor = current_f.current_floor
                # 방향키 유지, keepalive 리셋
                if current_key == "left":
                    _key_down(VK_LEFT)
                elif current_key == "right":
                    _key_down(VK_RIGHT)
                else:
                    _press(direction)
                next_keepalive = time.time() + 0.8
                last_floor_seen = current_f.current_floor

            # 경계 판정 대상 좌표 확보
            if cx is None or cy is None:
                time.sleep(0.01)
                continue

            try:
                l_val = int(cur_l_input.text()) if cur_l_input.text() else None
                r_val = int(cur_r_input.text()) if cur_r_input.text() else None
            except ValueError:
                l_val = r_val = None

            now_chk = time.time()
            # numba 경계 밖 판정(0.1초마다)
            if now_chk >= next_oob_check:
                cached_oob_dir = _determine_dir(
                    cx,
                    l_val if l_val is not None else -1,
                    r_val if r_val is not None else -1
                )
                next_oob_check = now_chk + 0.1

            # 경계 밖 강제 구동: 경계 안으로 들어갈 때까지 지속 신호
            movement_paused = (now_global < STOP_MOVE_UNTIL) or STOP_HARD_ACTIVE
            if cached_oob_dir != 0 and not movement_paused:
                required = "right" if cached_oob_dir == 1 else "left"
                # 방향 전환 필요 시: 전환 전에 반드시 현재 눌린 방향키 Up
                if current_key != required:
                    if current_key == "right":
                        _key_up(VK_RIGHT)
                    elif current_key == "left":
                        _key_up(VK_LEFT)
                    # 반대쪽도 보강 해제
                    if required == "right":
                        _key_up(VK_LEFT)
                    else:
                        _key_up(VK_RIGHT)
                    # 방향 전환 직후 텔레포트 즉발 1회 (금지 규칙 무시)
                    try:
                        import sys
                        import pydirectinput as _pdi
                        _m = sys.modules.get('__main__')
                        bf = getattr(_m, 'buffs_frame', None)
                        tf = getattr(bf, 'tele_frame', None) if bf else None
                        tp_key = tf.tp_combo.currentText() if tf and hasattr(tf, 'tp_combo') else ''
                        if tp_key:
                            _pdi.press(tp_key)
                    except Exception:
                        pass
                    _press(required)
                    direction = required
                    next_keepalive = time.time() + 0.1
                    # 경계 복귀 락: 2.2초간 반대 전환 금지
                    BOUND_LOCK_UNTIL = time.time() + 2.2
                # Down 유지 (0.1초 간격)
                if time.time() >= next_keepalive:
                    if required == "right":
                        _key_down(VK_RIGHT)
                    else:
                        _key_down(VK_LEFT)
                    next_keepalive = time.time() + 0.1
                # 경계 복귀 중 텔레포트 스팸 (주기 0.25초)
                try:
                    import sys as __sys, pydirectinput as __pdi
                    _m = __sys.modules.get('__main__')
                    bf = getattr(_m, 'buffs_frame', None)
                    tf = getattr(bf, 'tele_frame', None) if bf else None
                    tp_key = tf.tp_combo.currentText() if tf and hasattr(tf, 'tp_combo') else ''
                    if tp_key and time.time() >= OOB_TP_NEXT:
                        __pdi.press(tp_key)
                        OOB_TP_NEXT = time.time() + 0.25
                except Exception:
                    pass
            else:
                # 경계 안으로 복귀: 텔레포트 스팸 타이머 리셋
                try:
                    OOB_TP_NEXT = 0.0
                except Exception:
                    pass
                # 경계 안: 기본 유지, 단 공격 스레드가 반대 방향키 작업 시 현재 키 해제
                try:
                    import sys
                    ak = sys.modules.get('attack_key')
                    ak_dir = getattr(ak, '_current_dir', None) if ak else None
                except Exception:
                    ak_dir = None
                if not movement_paused and ak_dir and current_key and ak_dir != current_key and time.time() >= BOUND_LOCK_UNTIL:
                    # 공격 스레드가 반대 방향 작업 → 현재 키 해제 후 반대(=공격 스레드 방향) 즉시 누르기
                    if current_key == "right":
                        _key_up(VK_RIGHT)
                    elif current_key == "left":
                        _key_up(VK_LEFT)
                    current_key = None
                    # 반대 방향(ak_dir) 즉시 유지 시작
                    if ak_dir == 'left':
                        _press('left'); direction = 'left'
                    elif ak_dir == 'right':
                        _press('right'); direction = 'right'
                    next_keepalive = time.time() + 0.1
                elif not movement_paused:
                    # 유지 Down (0.1초 간격)
                    if current_key is None:
                        _press(direction)
                        next_keepalive = time.time() + 0.1
                    else:
                        if time.time() >= next_keepalive:
                            if current_key == "right":
                                _key_down(VK_RIGHT)
                            elif current_key == "left":
                                _key_down(VK_LEFT)
                            next_keepalive = time.time() + 0.1

            # 이동 정지 해제 시 복원 처리
            if not movement_paused and STOP_SAVED_DIR:
                # 재개: 저장된 방향으로 복원
                if current_key != STOP_SAVED_DIR:
                    _press(STOP_SAVED_DIR)
                    direction = STOP_SAVED_DIR
                STOP_SAVED_DIR = None
        except Exception:
            pass
        time.sleep(0.05)  # 50ms 주기로 신호 재전송 (반응성 향상)

        # ----- 사다리 블록 처리 -----
        for blk in ladder.ladder_blocks:
            try:
                if not blk.main_chk.isChecked():
                    continue

                # 방향 체크 (현재 눌린 방향키 기준)
                if current_key == "left" and not blk.chk_left.isChecked():
                    continue
                if current_key == "right" and not blk.chk_right.isChecked():
                    continue

                # 좌표 및 무시 로직
                if blk.coord is None:
                    continue
                cx0, cy0 = blk.coord
                ignore_val = int(blk.ign_edit.text()) if blk.ign_edit.text().isdigit() else 0

                # 조건 true?
                if _coord_match(cx,cy,cx0,cy0):
                    now=time.time()
                    if ignore_val>0:
                        # 처음 트리거되면 4초간 무시
                        if now < ignore_until[blk]:
                            continue
                        if ignore_until[blk]==0:
                            ignore_until[blk]=now+4.0
                            continue
                        # 4초 지난 후 실행하고 타이머 리셋
                        ignore_until[blk]=0.0

                    _tap_alt()
                    _tap_alt()  # 두 번 연속 시도
                    pdi.keyDown("up")
                    blk.up_active = True
                    blk.start_t = now
                    blk.pre_y = cy

                if blk.up_active and blk.goal_y is not None:
                    # 유지: ensure UP still pressed
                    pdi.keyDown("up")
                    if (blk.floor_edit.text().isdigit() and
                        current_f.current_floor is not None and
                        int(blk.floor_edit.text()) == current_f.current_floor and
                        cy <= blk.goal_y):
                        pdi.keyUp("up")  # VK_UP
                        blk.up_active = False
                    else:
                        now=time.time()
                        # 3.5s check with pre_y diff<=2
                        if now - blk.start_t >= 2.8 and cy == blk.pre_y:
                            pdi.keyUp("up")
                            blk.up_active = False
            except Exception:
                pass

        # ----- 점프다운 블록 처리 -----
        for blk in jump_down.jump_blocks:
            try:
                if not blk.main_chk.isChecked():
                    continue

                if blk.coord is None:
                    continue

                # 좌표 판정
                if _coord_match(cx, cy, blk.coord[0], blk.coord[1]):
                    now = time.time()
                    skip_val = int(blk.skip_edit.text()) if blk.skip_edit.text().isdigit() else 0
                    if skip_val>0:
                        if now < jd_ignore_until[blk]:
                            continue
                        if jd_ignore_until[blk]==0:
                            jd_ignore_until[blk]=now+4.0
                            continue
                        jd_ignore_until[blk]=0.0

                    # 선택층 계산
                    sel_steps = 1
                    try:
                        for i, fc in enumerate(blk.floor_checks):
                            if fc.isChecked():
                                sel_steps = i + 1
                                break
                    except Exception:
                        sel_steps = 1

                    # HOLD 모드: 선택층 수만큼(1층 포함) 층 변경 감지 후 해제
                    JD_RETRY_ACTIVE = True
                    JD_RETRY_FROM_FLOOR = current_f.current_floor
                    JD_STEPS_TOTAL = sel_steps
                    JD_STEPS_DONE = 0
                    JD_RETRY_NEXT = time.time() + 0.2
                    _key_down(0x28)
                    _tap_alt()
                    blk.prev_floor = current_f.current_floor

                # 층 변화 시에도 1층 감지 가드
                if blk.prev_floor is not None and current_f.current_floor is not None and blk.prev_floor != current_f.current_floor:
                    if current_f.current_floor == 1:
                        try: _key_up(0x28)
                        except Exception: pass
                        JD_RETRY_ACTIVE = False
                        JD_RETRY_FROM_FLOOR = None
                        JD_STEPS_TOTAL = 0
                        JD_STEPS_DONE = 0
                        JD_RETRY_NEXT = 0.0
                    blk.prev_floor = current_f.current_floor
            except Exception:
                pass
    # 루프 종료
    _release_all()


def create_start_stop_ui(parent_widget, boundary_inputs):
    """시작 / 정지 버튼 + F1 토글 + 제어 스레드"""
    l_input, r_input, y_button, *extra_inputs = boundary_inputs

    # 층별 L/R 입력 매핑
    floor_inputs = {1: (l_input, r_input)}
    total_extra = len(extra_inputs)//2
    for i in range(total_extra):
        f = i + 2
        floor_inputs[f] = (extra_inputs[i*2], extra_inputs[i*2+1])

    start_btn = QPushButton("시작", parent_widget)
    start_btn.setStyleSheet("QPushButton {background:#27ae60; color:white; border:none; font-size:10px;} QPushButton:hover{background:#2ecc71;} QPushButton:pressed{background:#229954;}")
    start_btn.setFixedSize(60, 28)
    
    stop_btn = QPushButton("정지", parent_widget)
    stop_btn.setStyleSheet("QPushButton {background:#e74c3c; color:white; border:none; font-size:10px;} QPushButton:hover{background:#ec7063;} QPushButton:pressed{background:#c0392b;}")
    stop_btn.setFixedSize(60, 28)

    # 상태 레이블 (정지 버튼 바로 위, 동일 크기)
    status_label = QLabel("상태: OFF", parent_widget)
    status_label.setAlignment(Qt.AlignCenter)
    status_label.setFixedSize(stop_btn.width(), stop_btn.height())
    status_label.setStyleSheet("QLabel {background:#e74c3c; color:white; border:none; border-radius:6px; font-size:10px; font-weight:bold;}")

    def update_status_label(is_on: bool):
        if is_on:
            status_label.setText("상태: ON")
            status_label.setStyleSheet("QLabel {background:#27ae60; color:white; border:none; border-radius:6px; font-size:10px; font-weight:bold;}")
        else:
            status_label.setText("상태: OFF")
            status_label.setStyleSheet("QLabel {background:#e74c3c; color:white; border:none; border-radius:6px; font-size:10px; font-weight:bold;}")
    
    
    save_btn = QPushButton("저장", parent_widget)
    save_btn.setStyleSheet("QPushButton {background:#3498db; color:white; border:none; font-size:10px;} QPushButton:hover{background:#5dade2;} QPushButton:pressed{background:#2980b9;}")
    save_btn.setFixedSize(60, 28)
    
    load_btn = QPushButton("불러오기", parent_widget)
    load_btn.setStyleSheet("QPushButton {background:#9b59b6; color:white; border:none; font-size:10px;} QPushButton:hover{background:#bb8fce;} QPushButton:pressed{background:#8e44ad;}")
    load_btn.setFixedSize(80, 28)
    delete_btn = QPushButton("셋팅값 삭제", parent_widget)
    delete_btn.setStyleSheet("QPushButton {background:#e67e22; color:white; border:none; font-size:10px;} QPushButton:hover{background:#f0b27a;} QPushButton:pressed{background:#ca6f1e;}")
    delete_btn.setFixedSize(80, 28)
    reset_btn = QPushButton("초기화", parent_widget)
    reset_btn.setStyleSheet("QPushButton {background:#7f8c8d; color:white; border:none; font-size:10px;} QPushButton:hover{background:#95a5a6;} QPushButton:pressed{background:#566573;}")
    reset_btn.setFixedSize(60, 28)

    # 전체 UI 토글
    all_widgets = parent_widget.findChildren((QPushButton, QLineEdit, QCheckBox))

    def _toggle_all(disable:bool):
        for w in all_widgets:
            if w is stop_btn:
                w.setEnabled(True)  # 정지 버튼은 항상 활성화
            else:
                w.setEnabled(not disable)

    def set_controls_enabled(enabled):
        # 기존 특정 위젯들
        l_input.setEnabled(enabled)
        r_input.setEnabled(enabled)
        y_button.setEnabled(enabled)
        start_btn.setEnabled(enabled)
        stop_btn.setEnabled(not enabled)
        # 전체 토글
        _toggle_all(disable=not enabled)

    def start():
        global _run_flag, _control_thread, _idle_thread, _idle_run
        if _run_flag:
            return
        _run_flag = True
        set_controls_enabled(False)
        update_status_label(True)
        # 공격 스레드 시작
        try:
            import attack_key
            attack_key.start_attack()
        except Exception:
            pass
        try:
            import buffs
            buffs.start_buffs()
        except Exception:
            pass
        try:
            import tele_port
            tele_port.start()
        except Exception:
            pass
        try:
            import auto_loot
            auto_loot.start()
        except Exception:
            pass
        try:
            import auto_key
            auto_key.start()
        except Exception:
            pass
        try:
            import dead_or_town
            dead_or_town.start()
        except Exception:
            pass
        try:
            import jump_system
            jump_system.start()
        except Exception:
            pass
        try:
            import portal_system
            portal_system.start()
        except Exception:
            pass
        # 루루모 핸들러 시작
        try:
            import handle_macro_prevent_mobs as _hm
            _hm.start()
        except Exception:
            pass
        # lie_detector는 체크박스로만 온오프
        # (start 버튼과 연결 제거)
        # try:
        #     import lie_detector
        #     lie_detector.start()
        # except Exception:
        #     pass
        # 좌표 정지 모니터 시작
        try:
            _idle_run = True
            _idle_thread = threading.Thread(target=_idle_monitor_loop, daemon=True)
            _idle_thread.start()
        except Exception:
            _idle_run = False
        _control_thread = threading.Thread(target=_control_loop, args=(l_input, r_input, floor_inputs), daemon=True)
        _control_thread.start()

    def stop():
        global _run_flag, _control_thread, _idle_thread, _idle_run
        if not _run_flag:
            return
        _run_flag = False
        # 모든 키 해제
        _release_all()
        try:
            import attack_key
            attack_key.stop_attack()
        except Exception:
            pass
        try:
            import buffs
            buffs.stop_buffs()
        except Exception:
            pass
        try:
            import tele_port
            tele_port.stop()
        except Exception:
            pass
        try:
            import auto_loot
            auto_loot.stop()
        except Exception:
            pass
        try:
            import auto_key
            auto_key.stop()
        except Exception:
            pass
        try:
            import dead_or_town
            dead_or_town.stop()
        except Exception:
            pass
        try:
            import jump_system
            jump_system.stop()
        except Exception:
            pass
        try:
            import portal_system
            portal_system.stop()
        except Exception:
            pass
        # 루루모 핸들러 정지
        try:
            import handle_macro_prevent_mobs as _hm
            _hm.stop()
        except Exception:
            pass
        # lie_detector는 체크박스로만 온오프
        # (stop 버튼과 연결 제거)
        # try:
        #     import lie_detector
        #     lie_detector.stop()
        # except Exception:
        #     pass
        # 좌표 정지 모니터 종료
        try:
            _idle_run = False
            if _idle_thread and _idle_thread.is_alive():
                _idle_thread.join(timeout=0.1)
            _idle_thread = None
        except Exception:
            pass
        set_controls_enabled(True)
        update_status_label(False)
        # 스레드가 완전히 종료될 때까지 최대 0.1초 기다림 후 포인터 해제
        if _control_thread and _control_thread.is_alive():
            _control_thread.join(timeout=0.1)
        _control_thread = None

    # ----- 저장 / 불러오기 -----
    def _save():
        from PyQt5.QtWidgets import QInputDialog
        import os, configparser
        cfg_root = "config"
        try:
            names = sorted([
                d for d in os.listdir(cfg_root)
                if os.path.isdir(os.path.join(cfg_root, d))
                and os.path.isfile(os.path.join(cfg_root, d, "settings.ini"))
            ])
        except Exception:
            names = []
        name, ok = QInputDialog.getItem(
            parent_widget,
            "설정 저장",
            "셋팅 이름 (기존 선택 시 덮어쓰기):",
            names,
            0,
            True,
        )
        if not ok or not name:
            return
        cfg_dir = os.path.join(cfg_root, name)
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_path = os.path.join(cfg_dir, "settings.ini")
        cfg = configparser.ConfigParser()

        # General
        cfg["General"] = {}
        if current_f.first_floor_y is not None:
            cfg["General"]["first_floor_y"] = str(current_f.first_floor_y)
        if minimap.capture_region:
            cfg["General"]["capture_region"] = ",".join(map(str, minimap.capture_region))
        if training_fun.hunting_region:
            cfg["General"]["hunting_region"] = ",".join(map(str, training_fun.hunting_region))
        # 1층 Y 버튼 텍스트 저장
        cfg["General"]["first_floor_btn"] = y_button.text()
        # 몬스터 정확도 슬라이더 값 및 위치 저장
        try:
            import sys, training_fun as _tf
            _main = sys.modules.get('__main__')
            acc_val = None
            if hasattr(_main, 'monster_acc_slider'):
                s = _main.monster_acc_slider
                acc_val = s.value()
                cfg["General"]["monster_acc_pos"] = f"{s.x()},{s.y()}"
            if acc_val is None:
                acc_val = int(getattr(_tf, 'MON_THRESH', 100))
            cfg["General"]["monster_acc_value"] = str(acc_val)

            # 레이블 위치 저장 (있을 때만)
            if hasattr(_main, 'monster_acc_label'):
                l = _main.monster_acc_label
                cfg["General"]["monster_acc_label_pos"] = f"{l.x()},{l.y()}"
        except Exception:
            pass

        # Boundary
        cfg["Boundary"] = {}
        for fnum, (li, ri) in floor_inputs.items():
            cfg["Boundary"][f"{fnum}_L"] = li.text()
            cfg["Boundary"][f"{fnum}_R"] = ri.text()

        # Ladder blocks
        for idx, blk in enumerate(ladder.ladder_blocks, 1):
            sec = f"Ladder{idx}"
            cfg[sec] = {
                "main_chk": str(int(blk.main_chk.isChecked())),
                "chk_left": str(int(blk.chk_left.isChecked())),
                "chk_right": str(int(blk.chk_right.isChecked())),
                "coord": "" if blk.coord is None else ",".join(map(str, blk.coord)),
                "goal_y": "" if blk.goal_y is None else str(blk.goal_y),
                "ign": blk.ign_edit.text(),
                "floor": blk.floor_edit.text()
            }

        # JumpDown blocks 저장
        if hasattr(jump_down, 'jump_blocks'):
            for idx, blk in enumerate(jump_down.jump_blocks,1):
                sec=f"Jump{idx}"
                floors = {
                    'f1':str(int(blk.floor_checks[0].isChecked())) if len(blk.floor_checks)>0 else '0',
                    'f2':str(int(blk.floor_checks[1].isChecked())) if len(blk.floor_checks)>1 else '0',
                    'f3':str(int(blk.floor_checks[2].isChecked())) if len(blk.floor_checks)>2 else '0',
                    'f4':str(int(blk.floor_checks[3].isChecked())) if len(blk.floor_checks)>3 else '0',
                }
                cfg[sec]={
                    'main_chk':str(int(blk.main_chk.isChecked())),
                    'coord':'' if blk.coord is None else ','.join(map(str,blk.coord)),
                    'skip':blk.skip_edit.text(),
                    **floors
                }
        
        # 점프 시스템 저장
        try:
            import sys
            _m = sys.modules.get('__main__')
            jf = getattr(_m, 'buffs_frame', None)
            js = getattr(jf, 'jump_sys_frame', None) if jf else None
            if js:
                cfg['JumpSystem'] = {}
                cfg['JumpSystem']['enabled'] = '1' if js.jump_enable_chk.isChecked() else '0'
                for i in range(9):
                    c = js.jump_coords[i]
                    cfg['JumpSystem'][f's{i+1}_coord'] = '' if not c else f"{c[0]},{c[1]}"
                    cfg['JumpSystem'][f's{i+1}_left'] = '1' if js.jump_left_checks[i].isChecked() else '0'
                    cfg['JumpSystem'][f's{i+1}_right'] = '1' if js.jump_right_checks[i].isChecked() else '0'
        except Exception:
            pass

        # IgnoreMob 저장
        try:
            import ignore_mob as _ig
            if 'IgnoreMob' not in cfg:
                cfg['IgnoreMob'] = {}
            for i in range(9):
                l = _ig._LEFT_COORDS[i] if i < len(_ig._LEFT_COORDS) else None
                r = _ig._RIGHT_COORDS[i] if i < len(_ig._RIGHT_COORDS) else None
                cfg['IgnoreMob'][f's{i+1}_L'] = '' if not l else f"{int(l[0])},{int(l[1])}"
                cfg['IgnoreMob'][f's{i+1}_R'] = '' if not r else f"{int(r[0])},{int(r[1])}"
        except Exception:
            pass

        # 포탈 저장
        try:
            import sys
            _m = sys.modules.get('__main__')
            pf = getattr(_m, 'portal_frame', None)
            if pf:
                cfg['Portal'] = {}
                n = len(getattr(pf, 'portal_coords', []) or [])
                for i in range(n):
                    c = pf.portal_coords[i] if hasattr(pf,'portal_coords') else None
                    cfg['Portal'][f'p{i+1}'] = '' if not c else f"{c[0]},{c[1]}"
        except Exception:
            pass

        # 공격키/딜레이 저장
        try:
            import sys
            _m = sys.modules.get('__main__')
            atkf = getattr(_m,'attack_key_frame',None)
            if atkf:
                if 'General' not in cfg:
                    cfg['General'] = {}
                cfg['General']['atk_key'] = atkf.combo_key.currentText()
                cfg['General']['atk_dmin'] = atkf.edit_delay_min.text()
                cfg['General']['atk_dmax'] = atkf.edit_delay_max.text()
                # 몹추적 체크박스 저장
                try:
                    cfg['General']['chase_enabled'] = str(int(atkf.chk_chase.isChecked()))
                except Exception:
                    cfg['General']['chase_enabled'] = '0'
                # 공격시멈추기 체크박스 저장
                try:
                    cfg['General']['stop_on_attack'] = str(int(getattr(atkf,'chk_stop_on_attack',None).isChecked()))
                except Exception:
                    cfg['General']['stop_on_attack'] = '0'
                # 방향전환X 체크박스 저장
                try:
                    cfg['General']['no_turn'] = str(int(getattr(atkf,'chk_no_turn',None).isChecked()))
                except Exception:
                    cfg['General']['no_turn'] = '0'
                # 양방향감지 체크박스 저장
                try:
                    cfg['General']['both_detect'] = str(int(getattr(atkf,'chk_both_detect',None).isChecked()))
                except Exception:
                    cfg['General']['both_detect'] = '0'
                # 몹 미감지시 방향키 해제 저장
                try:
                    cfg['General']['stop_no_mob'] = str(int(getattr(atkf,'chk_stop_no_mob',None).isChecked()))
                except Exception:
                    cfg['General']['stop_no_mob'] = '0'
                # 플레이어 알람 체크박스 저장
                try:
                    import sys
                    _m = sys.modules.get('__main__')
                    pal = getattr(_m, 'player_alarm_check_box', None)
                    cfg['General']['player_alarm'] = '1' if (pal and pal.isChecked()) else '0'
                except Exception:
                    cfg['General']['player_alarm'] = '0'
                # 죽음/마을 감지 체크 저장
                try:
                    import sys
                    _m = sys.modules.get('__main__')
                    dt = getattr(_m, 'dead_town_check_box', None)
                    cfg['General']['dead_town'] = '1' if (dt and dt.isChecked()) else '0'
                except Exception:
                    cfg['General']['dead_town'] = '0'
        except Exception:
            pass

        # 공격 범위 입력값 저장 (atk_range_frame.edits)
        try:
            import sys
            _m=sys.modules.get('__main__')
            ar_frame=getattr(_m,'attack_range_frame',None)
            if ar_frame and hasattr(ar_frame,'edits'):
                vals=[e.text() for e in ar_frame.edits]
                cfg['General']['atk_range']=','.join(vals)
        except Exception:
            pass

        # Buffs 저장
        try:
            import sys
            _m = sys.modules.get('__main__')
            bframe = getattr(_m, 'buffs_frame', None)
            if bframe and hasattr(bframe, 'slots'):
                cfg['Buffs'] = {}
                # 마스터 체크 저장
                try:
                    cfg['Buffs']['enabled'] = '1' if (hasattr(bframe,'master_chk') and bframe.master_chk.isChecked()) else '0'
                except Exception:
                    cfg['Buffs']['enabled'] = '0'
                for idx, slot in enumerate(bframe.slots, start=1):
                    try:
                        if len(slot) == 3:
                            chk, combo, edit = slot
                        else:
                            combo, edit = slot  # type: ignore
                            chk = None
                        cfg['Buffs'][f'key_{idx}'] = combo.currentText()
                        cfg['Buffs'][f'delay_{idx}'] = edit.text()
                        if chk is not None:
                            cfg['Buffs'][f'enable_{idx}'] = '1' if chk.isChecked() else '0'
                    except Exception:
                        pass
                # 텔레포트 설정 저장
                try:
                    if hasattr(bframe, 'tele_frame'):
                        tf = bframe.tele_frame
                        cfg['Buffs']['tele_key'] = tf.tp_combo.currentText() if hasattr(tf,'tp_combo') else ''
                        cfg['Buffs']['tele_delay'] = tf.tp_delay.text() if hasattr(tf,'tp_delay') else ''
                except Exception:
                    pass
                # 펫먹이 설정 저장
                try:
                    cfg['Buffs']['pet_enabled'] = '1' if (hasattr(bframe,'pet_chk') and bframe.pet_chk.isChecked()) else '0'
                    cfg['Buffs']['pet_key'] = bframe.pet_combo.currentText() if hasattr(bframe,'pet_combo') else ''
                    cfg['Buffs']['pet_delay'] = bframe.pet_delay.text() if hasattr(bframe,'pet_delay') else ''
                except Exception:
                    pass
                # 플레이어 알람 저장
                try:
                    import sys
                    _m2 = sys.modules.get('__main__')
                    pal = getattr(_m2, 'player_alarm_check_box', None)
                    cfg['Buffs']['player_alarm'] = '1' if (pal and pal.isChecked()) else '0'
                except Exception:
                    cfg['Buffs']['player_alarm'] = '0'
                # 자동줍기 저장
                try:
                    if hasattr(bframe,'loot_frame'):
                        lf = bframe.loot_frame
                        cfg['Buffs']['loot_key'] = lf.loot_combo.currentText() if hasattr(lf,'loot_combo') else ''
                        cfg['Buffs']['loot_delay'] = lf.loot_delay.text() if hasattr(lf,'loot_delay') else ''
                except Exception:
                    pass
        except Exception:
            pass

        # FixedKey(고정키) 저장
        try:
            import sys
            _m = sys.modules.get('__main__')
            bframe = getattr(_m, 'buffs_frame', None)
            fk = getattr(bframe, 'fixed_key_frame', None) if bframe else None
            if fk:
                cfg['FixedKey'] = {
                    'key': fk.fixed_combo.currentText() if hasattr(fk,'fixed_combo') else '',
                    'delay': fk.fixed_delay.text() if hasattr(fk,'fixed_delay') else ''
                }
        except Exception:
            pass

        # lie_detector 체크박스 저장
        try:
            import sys
            _m = sys.modules.get('__main__')
            ld = getattr(_m, 'lie_detector_check_box', None)
            if 'General' not in cfg:
                cfg['General'] = {}
            cfg['General']['lie_detector'] = '1' if (ld and ld.isChecked()) else '0'
        except Exception:
            pass

        # Minimap 차단영역 저장
        try:
            import minimap as _mm
            if 'MinimapBlocks' not in cfg:
                cfg['MinimapBlocks'] = {}
            blocks = getattr(_mm, 'RED_BLOCKS', []) or []
            cfg['MinimapBlocks']['count'] = str(len(blocks))
            for i, (bx, by, bw, bh) in enumerate(blocks):
                cfg['MinimapBlocks'][f'b{i}'] = f"{int(bx)},{int(by)},{int(bw)},{int(bh)}"
        except Exception:
            pass

        with open(cfg_path, "w", encoding="utf-8") as fp:
            cfg.write(fp)

        # imgs/monster 이미지 저장 복사 (덮어쓰기)
        try:
            import shutil
            mon_src = os.path.join('imgs','monster')
            mon_dst = os.path.join(cfg_dir, 'monster')
            os.makedirs(mon_dst, exist_ok=True)
            # 기존 저장 폴더의 monster 이미지 제거
            for f in os.listdir(mon_dst):
                if f.lower().endswith('.png'):
                    try: os.remove(os.path.join(mon_dst,f))
                    except Exception: pass
            # 현재 imgs/monster 복사
            if os.path.isdir(mon_src):
                for f in os.listdir(mon_src):
                    if f.lower().endswith('.png'):
                        shutil.copy2(os.path.join(mon_src,f), os.path.join(mon_dst,f))
        except Exception:
            pass

    def _reset_all():
        """모든 입력과 캡처 상태 초기화"""
        # 정지
        try:
            stop()
        except Exception:
            pass

        # 입력값 초기화 (Boundary)
        for w in boundary_inputs:
            from PyQt5.QtWidgets import QLineEdit, QPushButton
            if isinstance(w, QLineEdit):
                w.clear()
        y_button.setText("1층Y")

        for li, ri in floor_inputs.values():
            li.clear(); ri.clear()

        # ladder blocks 초기화
        for blk in ladder.ladder_blocks:
            try:
                blk.btn_reset.click()
            except:
                pass

        # jumpdown blocks 초기화
        try:
            import jump_down
            for blk in jump_down.jump_blocks:
                blk.main_chk.setChecked(False)
                blk.coord = None
                blk.coord_btn.setText("(0,0)")
                blk.skip_edit.clear()
                for fc in blk.floor_checks:
                    fc.setChecked(False)
        except Exception:
            pass

        # 미니맵 캡처 중지 및 리셋
        if minimap.capture_timer:
            try:
                minimap.capture_timer.stop(); minimap.capture_timer.deleteLater()
            except: pass
            minimap.capture_timer=None
        minimap.reset_character_coordinates()
        minimap.capture_region=None
        if hasattr(minimap,'canvas_widget'):
            cw=minimap.canvas_widget
            # 파란 테두리(노란점 bbox) 제거
            try:
                cw.last_bbox = None
                if hasattr(cw, '_redbox_drawn'):
                    cw._redbox_drawn = False
            except Exception:
                pass
            if hasattr(cw,'texture_id'):
                try:
                    from OpenGL.GL import glDeleteTextures
                    glDeleteTextures(int(cw.texture_id))
                except:
                    pass
                delattr(cw,'texture_id')
            cw.update()

        # 사냥구역 캡처 중지 및 리셋
        if hasattr(minimap,'canvas_widget'):
            training_fun.reset_hunting(minimap.canvas_widget)
        # 미니맵 보라색 차단영역 초기화
        try:
            minimap.RED_BLOCKS = []
            if hasattr(minimap, 'canvas_widget') and minimap.canvas_widget:
                minimap.canvas_widget.update()
        except Exception:
            pass

        # 레이블 초기화
        if hasattr(minimap.canvas_widget,'coord_label') and minimap.canvas_widget.coord_label:
            minimap.canvas_widget.coord_label.setText("캐릭터좌표: 0,0")
        if hasattr(minimap.canvas_widget,'floor_label') and minimap.canvas_widget.floor_label:
            minimap.canvas_widget.floor_label.setText("현재층:")

        # 몬스터 이미지 초기화 (imgs/monster 비우고 리로드)
        try:
            import shutil
            mon_dir = os.path.join('imgs','monster')
            if os.path.isdir(mon_dir):
                for f in os.listdir(mon_dir):
                    if f.lower().endswith('.png'):
                        try: os.remove(os.path.join(mon_dir,f))
                        except Exception: pass
            training_fun.reload_monster_templates()
        except Exception:
            pass

        # 슬라이더 초기화
        try:
            import sys
            _main = sys.modules.get('__main__')
            if hasattr(_main,'monster_acc_slider'):
                s=_main.monster_acc_slider
                s.setValue(100)
                if hasattr(_main,'monster_acc_label'):
                    _main.monster_acc_label.setText("몬스터 정확도: 100")
        except Exception:
            pass

        # 버프/펫/텔레포트/자동줍기/고정키 초기화 + 체크박스류 초기화
        try:
            import sys
            _main = sys.modules.get('__main__')
            bframe = getattr(_main, 'buffs_frame', None)
            if bframe:
                # 버프 슬롯
                if hasattr(bframe, 'slots'):
                    for slot in bframe.slots:
                        if len(slot) == 3:
                            chk, combo, edit = slot
                        else:
                            combo, edit = slot  # type: ignore
                            chk = None
                        combo.setCurrentIndex(0)
                        edit.setText("15")
                        if chk is not None:
                            chk.setChecked(False)
                # 펫
                if hasattr(bframe, 'pet_chk'):
                    bframe.pet_chk.setChecked(False)
                if hasattr(bframe, 'pet_combo'):
                    bframe.pet_combo.setCurrentIndex(0)
                if hasattr(bframe, 'pet_delay'):
                    bframe.pet_delay.setText("300")
                # 텔레포트
                if hasattr(bframe, 'tele_frame'):
                    tf = bframe.tele_frame
                    if hasattr(tf,'tp_combo'):
                        tf.tp_combo.setCurrentIndex(0)
                    if hasattr(tf,'tp_delay'):
                        tf.tp_delay.setText("30")
                # 자동줍기
                if hasattr(bframe, 'loot_frame'):
                    lf = bframe.loot_frame
                    if hasattr(lf,'loot_combo'):
                        lf.loot_combo.setCurrentIndex(0)
                    if hasattr(lf,'loot_delay'):
                        lf.loot_delay.setText("0.5")
                # 고정키
                if hasattr(bframe, 'fixed_key_frame'):
                    fk = bframe.fixed_key_frame
                    if hasattr(fk,'fixed_combo'):
                        fk.fixed_combo.setCurrentIndex(0)
                    if hasattr(fk,'fixed_delay'):
                        fk.fixed_delay.setText("1.0")
                # 점프 시스템
                if hasattr(bframe, 'jump_sys_frame'):
                    js = bframe.jump_sys_frame
                    js.jump_enable_chk.setChecked(False)
                    for i in range(9):
                        js.jump_coords[i] = None
                        js.jump_coord_labels[i].setText("(0,0)")
                        try: js.jump_coord_labels[i].adjustSize()
                        except Exception: pass
                        js.jump_buttons[i].setText(f"점프{i+1}")
                        js.jump_left_checks[i].setChecked(False)
                        js.jump_right_checks[i].setChecked(False)
        except Exception:
            pass

        # 포탈 프레임 초기화
        try:
            import sys
            _m = sys.modules.get('__main__')
            pf = getattr(_m, 'portal_frame', None)
            if pf:
                for i in range(len(getattr(pf, 'portal_coords', []) or [])):
                    pf.portal_coords[i] = None
                    pf.portal_buttons[i].setText("P")
        except Exception:
            pass

        # 플레이어 알람 / 맵 변경감지 / 거탐 체크박스 초기화
        try:
            import sys
            _m = sys.modules.get('__main__')
            pal = getattr(_m, 'player_alarm_check_box', None)
            if pal: pal.setChecked(False)
            dt = getattr(_m, 'dead_town_check_box', None)
            if dt: dt.setChecked(False)
            ld = getattr(_m, 'lie_detector_check_box', None)
            if ld: ld.setChecked(False)
        except Exception:
            pass

        # 공격설정 프레임 체크박스 초기화
        try:
            import sys
            _m = sys.modules.get('__main__')
            atkf = getattr(_m,'attack_key_frame', None)
            if atkf:
                for name in ('chk_chase','chk_stop_on_attack','chk_no_turn','chk_both_detect','chk_stop_no_mob'):
                    if hasattr(atkf, name):
                        getattr(atkf, name).setChecked(False)
        except Exception:
            pass

        # 몬스터 미감지 좌표 설정 초기화
        try:
            import sys
            import ignore_mob as _ig
            _ig._LEFT_COORDS = [None]*9
            _ig._RIGHT_COORDS = [None]*9
            _m = sys.modules.get('__main__')
            bf = getattr(_m, 'buffs_frame', None)
            igf = getattr(bf, 'ignore_mob_frame', None) if bf else None
            if igf:
                for i in range(9):
                    igf.ignore_left_buttons[i].setChecked(False)
                    igf.ignore_right_buttons[i].setChecked(False)
                    igf.ignore_left_buttons[i].setToolTip('')
                    igf.ignore_right_buttons[i].setToolTip('')
        except Exception:
            pass

    def _load():
        from PyQt5.QtWidgets import QInputDialog
        import os, configparser
        cfg_root = "config"
        if not os.path.isdir(cfg_root):
            return
        names = [d for d in os.listdir(cfg_root) if os.path.isdir(os.path.join(cfg_root, d))]
        if not names:
            return
        name, ok = QInputDialog.getItem(parent_widget, "설정 불러오기", "셋팅 선택:", names, 0, False)
        if not ok or not name:
            return
        path = os.path.join(cfg_root, name, "settings.ini")
        if not os.path.isfile(path):
            return
        cfg = configparser.ConfigParser()
        cfg.read(path, encoding="utf-8")

        # 실행 중이면 정지
        if _run_flag:
            stop()

        # General
        if cfg.has_option("General", "first_floor_y"):
            current_f.set_first_floor_y(int(cfg["General"]["first_floor_y"]))

        # Y 버튼 텍스트 복원
        if cfg.has_option("General", "first_floor_btn"):
            y_button.setText(cfg["General"]["first_floor_btn"])

        # 슬라이더 값/위치 복원 + 레이블 위치 복원
        try:
            import sys
            _main = sys.modules.get('__main__')
            if hasattr(_main,'monster_acc_slider'):
                s=_main.monster_acc_slider
                val = int(cfg['General'].get('monster_acc_value','100'))
                s.setValue(val)
                _x_y = cfg['General'].get('monster_acc_pos', '')
                if _x_y and ',' in _x_y:
                    xs,ys=_x_y.split(','); s.move(int(xs), int(ys))
                # 레이블 동기화
                if hasattr(_main,'monster_acc_label'):
                    _main.monster_acc_label.setText(f"몬스터 정확도: {val}")
                    _lbl_xy = cfg['General'].get('monster_acc_label_pos','')
                    if _lbl_xy and ',' in _lbl_xy:
                        lxs,lys=_lbl_xy.split(','); _main.monster_acc_label.move(int(lxs), int(lys))
                # 값 강제 반영 (시그널 실패 대비)
                try:
                    import training_fun as _tf
                    _tf.MON_THRESH = float(val)
                except Exception:
                    pass
        except Exception:
            pass

        # 공격키/딜레이 복원
        try:
            import sys
            _m = sys.modules.get('__main__')
            atkf = getattr(_m,'attack_key_frame',None)
            if atkf and cfg.has_section('General'):
                atkf.combo_key.setCurrentText(cfg['General'].get('atk_key','a'))
                # ms -> 초 자동 변환 (이전 설정 호환)
                def _norm_delay(val_str: str, default_str: str) -> str:
                    try:
                        v = float(val_str) if val_str else float(default_str)
                        if v >= 10.0:  # 10 이상이면 ms 로 간주하여 초로 변환
                            v = v / 1000.0
                        return f"{v:g}"
                    except Exception:
                        return default_str
                atkf.edit_delay_min.setText(_norm_delay(cfg['General'].get('atk_dmin','0.3'), '0.3'))
                atkf.edit_delay_max.setText(_norm_delay(cfg['General'].get('atk_dmax','0.6'), '0.6'))
                # 몹추적 체크박스 복원
                try:
                    atkf.chk_chase.setChecked(cfg['General'].getint('chase_enabled', fallback=0)==1)
                except Exception:
                    pass
                # 공격시멈추기 체크박스 복원
                try:
                    atkf.chk_stop_on_attack.setChecked(cfg['General'].getint('stop_on_attack', fallback=0)==1)
                except Exception:
                    pass
                # 방향전환X 체크박스 복원
                try:
                    atkf.chk_no_turn.setChecked(cfg['General'].getint('no_turn', fallback=0)==1)
                except Exception:
                    pass
                # 양방향감지 체크박스 복원
                try:
                    atkf.chk_both_detect.setChecked(cfg['General'].getint('both_detect', fallback=0)==1)
                except Exception:
                    pass
                # 몹 미감지시 방향키 해제 복원
                try:
                    atkf.chk_stop_no_mob.setChecked(cfg['General'].getint('stop_no_mob', fallback=0)==1)
                except Exception:
                    pass
                # 플레이어 알람 체크박스 복원
                try:
                    import sys
                    _m = sys.modules.get('__main__')
                    pal = getattr(_m, 'player_alarm_check_box', None)
                    if pal:
                        pal.setChecked(cfg['General'].getint('player_alarm', fallback=0)==1)
                except Exception:
                    pass
                # 죽음/마을 감지 체크 복원
                try:
                    import sys
                    _m = sys.modules.get('__main__')
                    dt = getattr(_m, 'dead_town_check_box', None)
                    if dt:
                        dt.setChecked(cfg['General'].getint('dead_town', fallback=0)==1)
                except Exception:
                    pass
        except Exception:
            pass

        # 공격 범위 입력값 복원
        try:
            import sys
            _m=sys.modules.get('__main__')
            ar_frame=getattr(_m,'attack_range_frame',None)
            rng_str=cfg['General'].get('atk_range','') if cfg.has_option('General','atk_range') else ''
            if ar_frame and rng_str and hasattr(ar_frame,'edits'):
                parts=rng_str.split(',')
                for e,val in zip(ar_frame.edits, parts):
                    e.setText(val)
        except Exception:
            pass

        # Buffs 복원
        try:
            import sys
            _m = sys.modules.get('__main__')
            bframe = getattr(_m, 'buffs_frame', None)
            if bframe and cfg.has_section('Buffs') and hasattr(bframe, 'slots'):
                # 마스터 체크 복원
                try:
                    if hasattr(bframe,'master_chk'):
                        bframe.master_chk.setChecked(cfg['Buffs'].getint('enabled', fallback=0)==1)
                except Exception:
                    pass
                for idx, slot in enumerate(bframe.slots, start=1):
                    try:
                        if len(slot) == 3:
                            chk, combo, edit = slot
                        else:
                            combo, edit = slot  # type: ignore
                            chk = None
                        combo.setCurrentText(cfg['Buffs'].get(f'key_{idx}', combo.currentText()))
                        dval = cfg['Buffs'].get(f'delay_{idx}', '')
                        if dval:
                            edit.setText(dval)
                        if chk is not None:
                            chk.setChecked(cfg['Buffs'].getint(f'enable_{idx}', fallback=0) == 1)
                    except Exception:
                        pass
                # 텔레포트 복원
                try:
                    if hasattr(bframe,'tele_frame'):
                        tf = bframe.tele_frame
                        if hasattr(tf,'tp_combo'):
                            tf.tp_combo.setCurrentText(cfg['Buffs'].get('tele_key', tf.tp_combo.currentText()))
                        if hasattr(tf,'tp_delay'):
                            val = cfg['Buffs'].get('tele_delay','')
                            if val:
                                tf.tp_delay.setText(val)
                except Exception:
                    pass
                # 펫먹이 복원
                try:
                    if hasattr(bframe,'pet_chk'):
                        bframe.pet_chk.setChecked(cfg['Buffs'].getint('pet_enabled', fallback=0)==1)
                    if hasattr(bframe,'pet_combo'):
                        bframe.pet_combo.setCurrentText(cfg['Buffs'].get('pet_key', bframe.pet_combo.currentText()))
                    if hasattr(bframe,'pet_delay'):
                        pv = cfg['Buffs'].get('pet_delay','')
                        if pv:
                            bframe.pet_delay.setText(pv)
                except Exception:
                    pass
                # 플레이어 알람 복원
                try:
                    import sys
                    _m2 = sys.modules.get('__main__')
                    pal = getattr(_m2, 'player_alarm_check_box', None)
                    if pal:
                        pal.setChecked(cfg['Buffs'].getint('player_alarm', fallback=0)==1)
                except Exception:
                    pass
                # 자동줍기 복원
                try:
                    if hasattr(bframe,'loot_frame'):
                        lf = bframe.loot_frame
                        if hasattr(lf,'loot_combo'):
                            lf.loot_combo.setCurrentText(cfg['Buffs'].get('loot_key', lf.loot_combo.currentText()))
                        if hasattr(lf,'loot_delay'):
                            lv = cfg['Buffs'].get('loot_delay','')
                            if lv:
                                lf.loot_delay.setText(lv)
                except Exception:
                    pass
        except Exception:
            pass

        # FixedKey(고정키) 복원
        try:
            import sys
            _m = sys.modules.get('__main__')
            bframe = getattr(_m, 'buffs_frame', None)
            fk = getattr(bframe, 'fixed_key_frame', None) if bframe else None
            if fk and cfg.has_section('FixedKey'):
                if hasattr(fk,'fixed_combo'):
                    fk.fixed_combo.setCurrentText(cfg['FixedKey'].get('key', fk.fixed_combo.currentText()))
                if hasattr(fk,'fixed_delay'):
                    val = cfg['FixedKey'].get('delay','')
                    if val:
                        fk.fixed_delay.setText(val)
        except Exception:
            pass

        # General 내 lie_detector 복원
        try:
            import sys
            _m = sys.modules.get('__main__')
            ld = getattr(_m, 'lie_detector_check_box', None)
            if ld:
                ld.setChecked(cfg['General'].getint('lie_detector', fallback=0)==1)
        except Exception:
            pass

        # Boundary
        if cfg.has_section("Boundary"):
            for fnum, (li, ri) in floor_inputs.items():
                li.setText(cfg["Boundary"].get(f"{fnum}_L", ""))
                ri.setText(cfg["Boundary"].get(f"{fnum}_R", ""))

        # Ladder
        for idx, blk in enumerate(ladder.ladder_blocks, 1):
            sec = f"Ladder{idx}"
            if not cfg.has_section(sec):
                continue
            section = cfg[sec]
            blk.main_chk.setChecked(section.getint("main_chk", fallback=0) == 1)
            blk.chk_left.setChecked(section.getint("chk_left", fallback=0) == 1)
            blk.chk_right.setChecked(section.getint("chk_right", fallback=0) == 1)
            coord_str = section.get("coord", "")
            blk.coord = tuple(map(int, coord_str.split(","))) if coord_str else None
            blk.goal_y = section.getint("goal_y", fallback=None) if section.get("goal_y") else None
            blk.ign_edit.setText(section.get("ign", ""))
            blk.floor_edit.setText(section.get("floor", ""))
            blk.btn_coord.setText(f"{blk.coord[0]},{blk.coord[1]}") if blk.coord else blk.btn_coord.setText("좌표")
            blk.btn_goal.setText(f"목표({blk.goal_y})") if blk.goal_y else blk.btn_goal.setText("목표(0)")

        # JumpDown 불러오기
        for idx, blk in enumerate(jump_down.jump_blocks,1):
            sec=f"Jump{idx}"
            if not cfg.has_section(sec):
                continue
            section=cfg[sec]
            blk.main_chk.setChecked(section.getint('main_chk',fallback=0)==1)
            coord_str=section.get('coord','')
            blk.coord = tuple(map(int,coord_str.split(','))) if coord_str else None
            blk.coord_btn.setText(f"{blk.coord[0]},{blk.coord[1]}") if blk.coord else blk.coord_btn.setText("(0,0)")
            blk.skip_edit.setText(section.get('skip',''))
            floors_vals=[section.getint('f1',0),section.getint('f2',0),section.getint('f3',0),section.getint('f4',0)]
            for i, val in enumerate(floors_vals):
                if i < len(blk.floor_checks):
                    blk.floor_checks[i].setChecked(val==1)
        
        # 점프 시스템 불러오기
        try:
            import sys
            _m = sys.modules.get('__main__')
            jf = getattr(_m, 'buffs_frame', None)
            js = getattr(jf, 'jump_sys_frame', None) if jf else None
            if js and cfg.has_section('JumpSystem'):
                js.jump_enable_chk.setChecked(cfg['JumpSystem'].getint('enabled', fallback=0)==1)
                for i in range(9):
                    cs = cfg['JumpSystem'].get(f's{i+1}_coord','')
                    if cs and ',' in cs:
                        try:
                            xs, ys = map(int, cs.split(','))
                            js.jump_coords[i] = (xs, ys)
                            js.jump_coord_labels[i].setText(f"({xs},{ys})")
                        except Exception:
                            pass
                    js.jump_left_checks[i].setChecked(cfg['JumpSystem'].getint(f's{i+1}_left', fallback=0)==1)
                    js.jump_right_checks[i].setChecked(cfg['JumpSystem'].getint(f's{i+1}_right', fallback=0)==1)
                # 버튼/레이블 일괄 갱신
                try:
                    if hasattr(js, 'refresh_all'):
                        js.refresh_all()
                except Exception:
                    pass
        except Exception:
            pass

        # IgnoreMob 불러오기
        try:
            import ignore_mob as _ig
            if cfg.has_section('IgnoreMob'):
                for i in range(9):
                    ls = cfg['IgnoreMob'].get(f's{i+1}_L','')
                    rs = cfg['IgnoreMob'].get(f's{i+1}_R','')
                    if ls and ',' in ls:
                        try:
                            x,y = map(int, ls.split(','))
                            if i < len(_ig._LEFT_COORDS):
                                _ig._LEFT_COORDS[i] = (x,y)
                        except Exception:
                            pass
                    else:
                        if i < len(_ig._LEFT_COORDS):
                            _ig._LEFT_COORDS[i] = None
                    if rs and ',' in rs:
                        try:
                            x,y = map(int, rs.split(','))
                            if i < len(_ig._RIGHT_COORDS):
                                _ig._RIGHT_COORDS[i] = (x,y)
                        except Exception:
                            pass
                    else:
                        if i < len(_ig._RIGHT_COORDS):
                            _ig._RIGHT_COORDS[i] = None
                # UI가 존재하면 체크/툴팁 업데이트
                try:
                    _m2 = sys.modules.get('__main__')
                    bf = getattr(_m2, 'buffs_frame', None)
                    igf = getattr(bf, 'ignore_mob_frame', None) if bf else None
                    if igf:
                        for i in range(9):
                            l = _ig._LEFT_COORDS[i]
                            r = _ig._RIGHT_COORDS[i]
                            igf.ignore_left_buttons[i].setChecked(bool(l))
                            igf.ignore_right_buttons[i].setChecked(bool(r))
                            igf.ignore_left_buttons[i].setToolTip('' if not l else f"L: {l[0]},{l[1]}")
                            igf.ignore_right_buttons[i].setToolTip('' if not r else f"R: {r[0]},{r[1]}")
                except Exception:
                    pass
        except Exception:
            pass

        # 포탈 불러오기
        try:
            import sys
            _m = sys.modules.get('__main__')
            pf = getattr(_m, 'portal_frame', None)
            if pf and cfg.has_section('Portal'):
                n = len(getattr(pf, 'portal_coords', []) or [])
                for i in range(n):
                    cs = cfg['Portal'].get(f'p{i+1}', '')
                    if cs and ',' in cs:
                        try:
                            xs, ys = map(int, cs.split(','))
                            pf.portal_coords[i] = (xs, ys)
                            pf.portal_buttons[i].setText(f"P ({xs},{ys})")
                        except Exception:
                            pass
        except Exception:
            pass

        # imgs/monster 폴더를 저장된 이미지로 교체 후 템플릿 리로드
        try:
            import shutil
            mon_src = os.path.join('config', name, 'monster')
            mon_dst = os.path.join('imgs','monster')
            os.makedirs(mon_dst, exist_ok=True)
            # 현재 imgs/monster 정리
            for f in os.listdir(mon_dst):
                if f.lower().endswith('.png'):
                    try: os.remove(os.path.join(mon_dst,f))
                    except Exception: pass
            # 저장본 복사
            if os.path.isdir(mon_src):
                for f in os.listdir(mon_src):
                    if f.lower().endswith('.png'):
                        shutil.copy2(os.path.join(mon_src,f), os.path.join(mon_dst,f))
            # 템플릿 즉시 리로드
            training_fun.reload_monster_templates()
        except Exception:
            pass

        # Capture region 재시작
        new_region = None
        if cfg.has_option("General", "capture_region"):
            parts = cfg["General"]["capture_region"].split(",")
            if len(parts) == 4:
                try:
                    new_region = tuple(int(p) for p in parts)
                    # exe 환경에서 경로 문제 해결
                    if hasattr(sys, "frozen"):
                        # exe 실행 시 현재 작업 디렉토리 확인
                        print(f"EXE 실행 경로: {os.getcwd()}")
                        print(f"설정 파일 경로: {path}")
                        print(f"미니맵 레지온: {new_region}")
                except ValueError:
                    new_region = None

        # Minimap 차단영역 불러오기
        try:
            import minimap as _mm
            if cfg.has_section('MinimapBlocks'):
                cnt = cfg['MinimapBlocks'].getint('count', fallback=0)
                blocks = []
                for i in range(cnt):
                    s = cfg['MinimapBlocks'].get(f'b{i}', '')
                    if s and s.count(',')==3:
                        try:
                            bx,by,bw,bh = map(int, s.split(','))
                            blocks.append((bx,by,bw,bh))
                        except Exception:
                            pass
                _mm.RED_BLOCKS = blocks
        except Exception:
            pass

        # Hunting region 재시작
        new_hunting_region = None
        if cfg.has_option("General", "hunting_region"):
            parts_h = cfg["General"]["hunting_region"].split(",")
            if len(parts_h) == 4:
                try:
                    new_hunting_region = tuple(int(p) for p in parts_h)
                    # exe 환경에서 경로 문제 해결
                    if hasattr(sys, "frozen"):
                        print(f"사냥구역 레지온: {new_hunting_region}")
                except ValueError:
                    new_hunting_region = None

        # 모든 이전 상태 리셋 및 캡처 재시작 (해당 값이 있을 때만)
        # 항상 기존 미니맵 캡처 중지 및 리셋
        if minimap.capture_timer:
            try:
                minimap.capture_timer.stop(); minimap.capture_timer.deleteLater()
            except Exception:
                pass
            minimap.capture_timer = None

        minimap.reset_character_coordinates()
        minimap.capture_region = None

        # 사냥구역 캡처/텍스처도 먼저 완전히 정지/초기화 (혼선 방지)
        try:
            training_fun.reset_hunting(minimap.canvas_widget)
        except Exception:
            pass
        # 미니맵 차단영역 적용(불러온 값 반영)
        try:
            if hasattr(minimap, 'canvas_widget') and minimap.canvas_widget:
                minimap.canvas_widget.update()
        except Exception:
            pass

        if hasattr(minimap, "canvas_widget"):
            minimap.canvas_widget.last_bbox = None
            if hasattr(minimap.canvas_widget,'last_bbox'):
                minimap.canvas_widget.last_bbox=None
            minimap.canvas_widget.update()

        # 새로운 미니맵 영역이 설정된 경우에만 다시 시작
        if new_region is not None and hasattr(minimap, "canvas_widget"):
            minimap.capture_region = new_region
            # exe 환경에서 디버그 정보 출력
            if hasattr(sys, "frozen"):
                print(f"미니맵 캡처 시작: {new_region}")
            minimap.start_capture(new_region, minimap.canvas_widget)

        training_fun.hunting_region = new_hunting_region
        # 사냥구역 재시작 (값이 있을 때만). 미니맵 캔버스 위젯의 hunting_canvas에만 연결됨
        if new_hunting_region is not None and hasattr(minimap, "canvas_widget"):
            training_fun.start_hunting_canvas_capture(new_hunting_region, minimap.canvas_widget)

    # 버튼 연결
    start_btn.clicked.connect(start)
    stop_btn.clicked.connect(stop)
    save_btn.clicked.connect(_save)
    load_btn.clicked.connect(_load)
    reset_btn.clicked.connect(_reset_all)

    def _delete_setting():
        from PyQt5.QtWidgets import QInputDialog, QMessageBox
        import shutil, os
        cfg_root = "config"
        if not os.path.isdir(cfg_root):
            return
        names = [d for d in os.listdir(cfg_root) if os.path.isdir(os.path.join(cfg_root, d))]
        if not names:
            return
        name, ok = QInputDialog.getItem(parent_widget, "셋팅값 삭제", "삭제할 셋팅 선택:", names, 0, False)
        if not ok or not name:
            return
        reply = QMessageBox.question(parent_widget, "삭제 확인", f"'{name}' 셋팅을 삭제하시겠습니까?", QMessageBox.Yes|QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                shutil.rmtree(os.path.join(cfg_root, name))
            except Exception:
                pass

    delete_btn.clicked.connect(_delete_setting)

    # 텔레그램 연동 버튼 (초기화 버튼 오른쪽)
    try:
        import telegram as _tg
        telegram_btn = _tg.create_telegram_button(parent_widget, reset_btn)
        try:
            import fix_msw as _msw
            fix_msw_btn = _msw.create_fix_msw_button(parent_widget, telegram_btn)
            try:
                import draw_minimap as _dm
                _dm_btn = _dm.create_minimap_edit_button(parent_widget, fix_msw_btn)
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        telegram_btn = None

    # F1 토글
    top_win = parent_widget.window()
    _TOP_WINDOW = top_win # 전역 참조 저장
    _START_FN = start
    _STOP_FN = stop
    _SET_CONTROLS_ENABLED = set_controls_enabled
    _RESET_ALL_FN = _reset_all
    _START_BUTTON = start_btn
    _STOP_BUTTON = stop_btn

    # 토글 가드 (중복/연타 방지)
    _last_toggle_ts = 0.0

    def _on_f1():
        nonlocal _last_toggle_ts
        now = time.time()
        # 전역 비활성화 또는 비로그인 시 차단
        try:
            import sys as _sys
            _m = _sys.modules.get('__main__')
            is_disabled = bool(getattr(_m, 'F1_DISABLED', False))
            is_logged = bool(getattr(_m, 'IS_LOGGED_IN', False))
            if is_disabled or not is_logged:
                return
        except Exception:
            pass
        if now - _last_toggle_ts < 0.25:
            return
        _last_toggle_ts = now
        # 단순 토글: 시작 → 정지 → 시작 → ...
        if _run_flag:
            stop()
        else:
            start()

    # keyboard 라이브러리 글로벌 핫키 (윈도우 전역) 추가
    if _kb:
        # 기존 등록 제거
        try:
            _kb.unhook_all_hotkeys()
        except Exception:
            pass

        _kb.on_press_key('f1', lambda e: _on_f1())
        top_win._f1_kb = True

    # keyPressEvent 패치 (마지막 보험)
    orig_key_press = getattr(top_win, 'keyPressEvent', None)

    def _patched_key_press(event):
        # keyboard 훅이 없는 경우에만 Qt 키 이벤트로 처리
        if event.key() == Qt.Key_F1 and not getattr(top_win, '_f1_kb', False):
            _on_f1()
        if orig_key_press:
            orig_key_press(event)

    top_win.keyPressEvent = _patched_key_press

    # 정지 버튼 초기에는 비활성화
    stop_btn.setEnabled(False)

    # 배치 함수
    def reposition():
        base_x = 10
        start_y = parent_widget.height() - 60  # 하단에서 60px 위
        spacing = 5
        x = base_x
        start_btn.move(x, start_y)
        x += start_btn.width() + spacing
        stop_btn.move(x, start_y)
        # 상태 레이블: 정지 버튼 바로 위, 동일 크기 유지
        status_label.setFixedSize(stop_btn.width(), stop_btn.height())
        status_label.move(stop_btn.x(), start_y - status_label.height() - 2)
        x += stop_btn.width() + spacing
        save_btn.move(x, start_y)
        x += save_btn.width() + spacing
        load_btn.move(x, start_y)
        x += load_btn.width() + spacing
        delete_btn.move(x, start_y)
        x += delete_btn.width() + spacing
        reset_btn.move(x, start_y)
        # 텔레그램 버튼: 초기화 버튼 바로 오른쪽, 동일 크기
        try:
            if 'telegram_btn' in locals() and telegram_btn:
                telegram_btn.setFixedSize(reset_btn.width(), reset_btn.height())
                telegram_btn.move(reset_btn.x() + reset_btn.width() + spacing, start_y)
        except Exception:
            pass

    reposition()

    original_resize = getattr(parent_widget, "resizeEvent", None)

    def new_resize(event):
        if original_resize:
            original_resize(event)
        reposition()
    parent_widget.resizeEvent = new_resize

    return start_btn, stop_btn 