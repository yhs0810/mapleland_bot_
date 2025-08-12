from PyQt5.QtWidgets import QFrame, QLabel, QLineEdit, QComboBox, QWidget, QCheckBox
from typing import List, Tuple
import threading, time
import pydirectinput as pdi
import tele_port
import auto_loot

# 공격 차단 공유 변수 (attack_key 에서 참조)
BUFF_BLOCK_ATTACK_UNTIL: float = 0.0

# 지원 키 리스트 (확장)
AVAILABLE_KEYS: List[str] = [
    # 알파벳/숫자
    *[chr(c) for c in range(ord('a'), ord('z')+1)],
    *[str(d) for d in range(0,10)],
    # 기능키
    *[f"f{i}" for i in range(1,13)],
    'escape','tab','enter','space','backspace','delete','insert','home','end','pageup','pagedown',
    # 수정키/조합키
    'shift','ctrl','alt','lshift','rshift','lctrl','rctrl','lalt','ralt',
    # 방향키
    'left','right','up','down'
]

_run_flag = False
_thread = None


def create_buffs_ui(parent: QWidget, anchor_widget: QFrame) -> QFrame:
    """공격 프레임 근처에 2x3 버프 슬롯 UI 생성"""
    panel = QFrame(parent)
    panel.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    panel.setFixedSize(max(220, anchor_widget.width()), 120)
    # 위치: 공격 프레임 아래 여백 6px
    panel.move(anchor_widget.x(), anchor_widget.y() + anchor_widget.height() + 6)

    title = QLabel("버프", panel)
    title.setStyleSheet("color:#f1c40f; font-size:12px; font-weight:bold;")
    title.move(6, 2)
    try:
        title.adjustSize()
    except Exception:
        pass

    # 마스터 체크박스 (버프 전체 사용)
    master_chk = QCheckBox("버프 사용", panel)
    master_chk.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
    def _place_master():
        try:
            tw = title.sizeHint().width() if hasattr(title, 'sizeHint') else title.width()
            master_chk.move(title.x() + tw + 8, title.y())
        except Exception:
            pass
    _place_master()
    panel.master_chk = master_chk
    panel.place_master = _place_master

    slots: List[Tuple[QComboBox, QLineEdit]] = []

    # 2열 x 3행 배치
    col_w = (panel.width() - 12) // 2
    x0 = 6
    x1 = 6 + col_w
    y_base = 18
    row_h = 32

    def add_slot(col_x: int, row_y: int) -> Tuple[QComboBox, QLineEdit]:
        lbl_k = QLabel("키:", panel); lbl_k.setStyleSheet("color:#dcdcdc; font-size:9px;")
        lbl_k.move(col_x, row_y)
        combo = QComboBox(panel); combo.addItem(""); combo.addItems(AVAILABLE_KEYS); combo.setFixedSize(70,14)
        combo.move(col_x + 20, row_y)
        lbl_d = QLabel("딜레이(초):", panel); lbl_d.setStyleSheet("color:#dcdcdc; font-size:9px;")
        lbl_d.move(col_x, row_y+16)
        edit = QLineEdit(panel); edit.setFixedSize(30,12); edit.setText("15")
        edit.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:8px;}")
        edit.move(col_x + 60, row_y+16)
        return combo, edit

    for r in range(3):
        c0 = add_slot(x0, y_base + r*row_h)
        c1 = add_slot(x1, y_base + r*row_h)
        slots.extend([c0, c1])

    panel.slots = slots  # [(combo, edit), ...]

    # ----- 펫먹이 프레임 -----
    pet = QFrame(parent)
    pet.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    pet.setFixedSize(panel.width(), 36)
    pet.move(panel.x(), panel.y() + panel.height() + 6)
    pet_chk = QCheckBox("펫먹이:", pet)
    pet_chk.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
    pet_chk.move(6, 10)
    pet_combo = QComboBox(pet); pet_combo.addItems(AVAILABLE_KEYS); pet_combo.setFixedSize(70,14)
    pet_combo.move(60, 10)
    pet_lbl = QLabel("딜레이(초):", pet); pet_lbl.setStyleSheet("color:#dcdcdc; font-size:9px;")
    pet_lbl.move(140, 12)
    pet_edit = QLineEdit(pet); pet_edit.setFixedSize(40,12); pet_edit.setText("300")
    pet_edit.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:8px;}")
    pet_edit.move(200, 12)
    # 참조 보관
    panel.pet_frame = pet
    panel.pet_chk = pet_chk
    panel.pet_combo = pet_combo
    panel.pet_delay = pet_edit

    # ----- 자동줍기 프레임 (펫먹이 아래) -----
    loot = auto_loot.create_auto_loot_ui(parent, panel.pet_frame)
    panel.loot_frame = loot

    # ----- 고정키 프레임 (자동줍기 아래) -----
    try:
        import auto_key
        fixed = auto_key.create_auto_key_ui(parent, panel.loot_frame)
        panel.fixed_key_frame = fixed
    except Exception:
        panel.fixed_key_frame = None

    # ----- 텔레포트 프레임 (고정키 아래) -----
    tele = tele_port.create_teleport_ui(parent, panel.fixed_key_frame if panel.fixed_key_frame else panel.loot_frame)
    panel.tele_frame = tele

    # ----- 점프 시스템 프레임 (텔레포트 아래) -----
    try:
        import jump_system
        jumpf = jump_system.create_jump_system_ui(parent, panel.tele_frame)
        panel.jump_sys_frame = jumpf
    except Exception:
        panel.jump_sys_frame = None

    # ----- 매크로방지 몹 핸들러 프레임 (점프 시스템 바로 아래, 동일 크기) -----
    try:
        if panel.jump_sys_frame:
            import handle_macro_prevent_mobs as mh
            mhf = mh.create_macro_prevent_mobs_ui(parent, panel.jump_sys_frame)
            panel.macro_handler_frame = mhf
            try:
                mhf.show()
            except Exception:
                pass
        else:
            panel.macro_handler_frame = None
    except Exception:
        panel.macro_handler_frame = None

    # ----- 몬스터 미감지 프레임 (점프 시스템 왼쪽에 동일 크기) -----
    try:
        import ignore_mob
        if panel.jump_sys_frame:
            igf = ignore_mob.create_ignore_mob_ui(parent, panel.jump_sys_frame)
            panel.ignore_mob_frame = igf
        else:
            panel.ignore_mob_frame = None
    except Exception:
        panel.ignore_mob_frame = None

    # ----- 로그인 프레임 (몬스터 미감지 바로 아래, 동일 크기) -----
    try:
        import login_frame as user_state
        if panel.ignore_mob_frame:
            logf = user_state.create_user_state_ui(parent, panel.ignore_mob_frame)
            panel.login_frame = logf
        else:
            panel.login_frame = None
    except Exception:
        panel.login_frame = None

    # 리사이즈 시 너비 따라 재배치
    orig = parent.resizeEvent if hasattr(parent,'resizeEvent') else None
    def on_resize(e):
        if orig: orig(e)
        panel.setFixedWidth(max(220, anchor_widget.width()))
        nonlocal col_w, x0, x1
        col_w = (panel.width() - 12) // 2
        x0 = 6
        x1 = 6 + col_w
        # 마스터 체크박스 제목 오른쪽 유지
        try:
            if hasattr(panel, 'place_master'):
                panel.place_master()
        except Exception:
            pass
        for i, (combo, edit) in enumerate(panel.slots):
            col = 0 if (i%2==0) else 1
            row = i//2
            cx = x0 if col==0 else x1
            cy = y_base + row*row_h
            for w in panel.children():
                if isinstance(w, QLabel) and w.text()=="키:":
                    if abs(w.y()-cy)<=1 and (w.x()==cx or abs(w.x()-cx)<=1):
                        w.move(cx, cy)
                        break
            combo.move(cx+20, cy)
            for w in panel.children():
                if isinstance(w, QLabel) and w.text()=="딜레이(초):":
                    if abs(w.y()-(cy+16))<=1 and (w.x()==cx or abs(w.x()-cx)<=1):
                        w.move(cx, cy+16)
                        break
            edit.move(cx+60, cy+16)
        # 펫 프레임 재배치/폭 동기화
        if hasattr(panel, 'pet_frame'):
            panel.pet_frame.setFixedWidth(panel.width())
            panel.pet_frame.move(panel.x(), panel.y() + panel.height() + 6)
        # 자동줍기 프레임 재배치/폭 동기화 (펫먹이 아래)
        if hasattr(panel, 'loot_frame') and hasattr(panel, 'pet_frame'):
            panel.loot_frame.setFixedWidth(panel.width())
            panel.loot_frame.move(panel.x(), panel.pet_frame.y() + panel.pet_frame.height() + 6)
        # 고정키 프레임 재배치/폭 동기화 (자동줍기 아래)
        try:
            if hasattr(panel, 'fixed_key_frame') and panel.fixed_key_frame:
                panel.fixed_key_frame.setFixedWidth(panel.width())
                panel.fixed_key_frame.move(panel.x(), panel.loot_frame.y() + panel.loot_frame.height() + 6)
        except Exception:
            pass
        # 텔레포트 프레임 재배치/폭 동기화 (고정키 아래)
        if hasattr(panel, 'tele_frame'):
            anchor = panel.fixed_key_frame if hasattr(panel, 'fixed_key_frame') and panel.fixed_key_frame else panel.loot_frame
            panel.tele_frame.setFixedWidth(panel.width())
            panel.tele_frame.move(panel.x(), anchor.y() + anchor.height() + 6)
        # 점프 시스템 프레임 재배치/폭 동기화 (텔레포트 아래)
        try:
            if hasattr(panel, 'jump_sys_frame') and panel.jump_sys_frame:
                panel.jump_sys_frame.setFixedWidth(panel.width())
                panel.jump_sys_frame.move(panel.x(), panel.tele_frame.y() + panel.tele_frame.height() + 7)
        except Exception:
            pass
        # 매크로방지 몹 핸들러 프레임 재배치/폭 동기화 (점프 시스템 아래 동일 크기)
        try:
            if hasattr(panel, 'macro_handler_frame') and panel.macro_handler_frame and hasattr(panel, 'jump_sys_frame') and panel.jump_sys_frame:
                jf = panel.jump_sys_frame
                mhf = panel.macro_handler_frame
                mhf.setFixedSize(jf.width(), jf.height())
                mhf.move(jf.x(), jf.y() + jf.height() + 6)
        except Exception:
            pass
        # 몬스터 미감지 프레임 재배치/폭/위치 동기화 (점프 왼쪽, 오른쪽만 2px 축소, y +1)
        try:
            if hasattr(panel, 'ignore_mob_frame') and panel.ignore_mob_frame and hasattr(panel, 'jump_sys_frame') and panel.jump_sys_frame:
                jf = panel.jump_sys_frame
                # 기존 왼쪽 가장자리(폭 jump-2, 간격 12 기준)
                left_old = jf.x() - max(0, jf.width() - 2) - 12
                # 새 폭: jump-4 (오른쪽만 2 줄임)
                w = max(0, jf.width() - 4)
                h = jf.height()
                panel.ignore_mob_frame.setFixedSize(w, h)
                panel.ignore_mob_frame.move(left_old, jf.y() + 1)
        except Exception:
            pass
        # 로그인 프레임 재배치/폭/위치 동기화 (미감지 바로 아래)
        try:
            if hasattr(panel, 'login_frame') and panel.login_frame and hasattr(panel, 'ignore_mob_frame') and panel.ignore_mob_frame:
                ig = panel.ignore_mob_frame
                panel.login_frame.setFixedSize(ig.width(), ig.height())
                panel.login_frame.move(ig.x(), ig.y() + ig.height() + 6)
        except Exception:
            pass
    parent.resizeEvent = on_resize

    return panel


def _buff_loop(panel: QFrame):
    global _run_flag, BUFF_BLOCK_ATTACK_UNTIL
    schedule: List[float] = []
    keys: List[str] = []
    delays: List[float] = []
    now = time.time()
    for combo, edit in getattr(panel,'slots',[]):
        try:
            k = combo.currentText()
            d_s = float(edit.text()) if edit.text() else 0.0
            keys.append(k)
            delays.append(d_s)
            if k and d_s>0 and getattr(panel,'master_chk',None) and panel.master_chk.isChecked():
                schedule.append(now + d_s)
            else:
                schedule.append(1e18)
        except Exception:
            keys.append(""); delays.append(0.0); schedule.append(1e18)
    # 펫먹이 스케줄
    pet_next = 1e18
    pet_enabled_prev = False
    pet_last_delay = 0.0

    while _run_flag:
        try:
            now = time.time()
            enabled_master = bool(getattr(panel,'master_chk',None) and panel.master_chk.isChecked())
            for i in range(len(keys)):
                try:
                    combo, edit = panel.slots[i]
                    k = combo.currentText()
                    d_s = float(edit.text()) if edit.text() else 0.0
                    keys[i] = k
                    delays[i] = d_s
                    if (not enabled_master) or (not k) or d_s <= 0:
                        schedule[i] = 1e18
                        continue
                    # 딜레이/토글 변경 시 즉시 재스케줄
                    if schedule[i] == 1e18 or now + 10 < schedule[i] or now >= schedule[i]:
                        pass
                    t_left = schedule[i]-now
                    if 0.0 <= t_left <= 2.4:
                        BUFF_BLOCK_ATTACK_UNTIL = max(BUFF_BLOCK_ATTACK_UNTIL, now + 2.4)
                    if now >= schedule[i]:
                        try:
                            pdi.press(k)
                        except Exception:
                            pass
                        schedule[i] = now + max(0.1, d_s)
                except Exception:
                    pass
            # 펫먹이 처리
            try:
                if hasattr(panel,'pet_chk') and panel.pet_chk.isChecked():
                    dval = float(panel.pet_delay.text()) if panel.pet_delay.text() else 0.0
                    if dval > 0:
                        if (not pet_enabled_prev) or (abs(dval - pet_last_delay) > 1e-6) or pet_next == 1e18:
                            pet_next = now + dval
                        if now >= pet_next:
                            pdi.press(panel.pet_combo.currentText())
                            pet_next = now + max(0.1, dval)
                    pet_last_delay = dval
                    pet_enabled_prev = True
                else:
                    pet_next = 1e18
                    pet_enabled_prev = False
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(0.05)


def start_buffs():
    """버프 스레드 시작(이미 실행 중이면 무시)"""
    global _run_flag, _thread
    if _run_flag:
        return
    try:
        import sys
        main_mod = sys.modules.get('__main__')
        panel = getattr(main_mod, 'buffs_frame', None)
        if panel is None:
            return
    except Exception:
        return
    _run_flag = True
    _thread = threading.Thread(target=_buff_loop, args=(panel,), daemon=True)
    _thread.start()


def stop_buffs():
    """버프 스레드 정지"""
    global _run_flag, _thread
    _run_flag = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=0.1)
    _thread = None
