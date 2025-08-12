from PyQt5.QtWidgets import QFrame, QLabel, QCheckBox, QPushButton, QWidget
import threading, time
import pydirectinput as pdi


def create_jump_system_ui(parent: QWidget, anchor_frame: QFrame) -> QFrame:
    frame = QFrame(parent)
    frame.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")

    # 제목
    title = QLabel("점프 시스템", frame)
    title.setStyleSheet("color:#f1c40f; font-size:12px; font-weight:bold;")
    title.move(6, 2)
    try:
        title.adjustSize()
    except Exception:
        pass

    # 점프 활성화 체크박스 (일반 스타일)
    chk = QCheckBox("점프 활성화", frame)
    chk.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
    chk.move(6, 20)

    # 버튼들 (점프1~점프9) - 3x3 그리드 + 각 버튼 아래 좌/우 체크박스 + 좌표 레이블(버튼 오른쪽)
    buttons = []
    left_checks = []
    right_checks = []
    coord_labels = []
    coords = [None]*9  # type: ignore[list-item]
    btn_w, btn_h = 76, 16
    chk_h = 14
    gap_x, gap_y_row = 6, 8  # 열 간격, 행 간격(체크박스 아래 여유 포함)
    cols = 3
    rows = 3
    x0, y0 = 6, 44  # 그리드 시작 위치
    row_h = btn_h + 2 + chk_h + gap_y_row

    def _capture_and_update(idx: int, label: QLabel):
        try:
            import minimap
            cx = getattr(minimap, 'current_x', None)
            cy = getattr(minimap, 'current_y', None)
            if (cx is None or cy is None) and hasattr(minimap, 'canvas_widget'):
                cw = getattr(minimap, 'canvas_widget', None)
                if cw is not None and hasattr(cw, 'last_cx') and hasattr(cw, 'last_cy'):
                    cx = getattr(cw, 'last_cx', None)
                    cy = getattr(cw, 'last_cy', None)
            if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
                ix, iy = int(cx), int(cy)
                coords[idx] = (ix, iy)
                label.setText(f"({ix},{iy})")
                try: label.adjustSize()
                except Exception: pass
                try: buttons[idx].setText(f"점프{idx+1} ({ix},{iy})")
                except Exception: pass
        except Exception:
            pass

    for i in range(1, 10):
        r = (i-1) // cols
        c = (i-1) % cols
        b = QPushButton(f"점프{i}", frame)
        b.setFixedSize(btn_w, btn_h)
        b.setStyleSheet(
            "QPushButton {background:#5a5a5a; color:#dcdcdc; border:1px solid #777; border-radius:4px; font-size:10px;} "
            "QPushButton:hover{background:#6a6a6a;} "
            "QPushButton:pressed{background:#4a4a4a;}"
        )
        bx = x0 + c * (btn_w + gap_x)
        by = y0 + r * row_h
        b.move(bx, by)
        buttons.append(b)

        # 좌표 레이블 (버튼 우측)
        lbl = QLabel("(0,0)", frame)
        lbl.setStyleSheet("color:#dcdcdc; font-size:9px;")
        lbl.move(bx + btn_w + 6, by + 1)
        try: lbl.adjustSize()
        except Exception: pass
        coord_labels.append(lbl)

        # 클릭 시 해당 슬롯에 현재 좌표 저장 + 레이블/버튼 직접 업데이트
        b.clicked.connect(lambda checked=False, idx=i-1, lab=lbl: _capture_and_update(idx, lab))

        # 체크박스 (좌/우)
        lchk = QCheckBox("좌", frame)
        lchk.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
        rchk = QCheckBox("우", frame)
        rchk.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
        cy = by + btn_h + 2
        lchk.move(bx + 6, cy)
        rchk.move(bx + 40, cy)
        left_checks.append(lchk)
        right_checks.append(rchk)

    # 초기화 버튼 (그리드 아래 중앙 정렬)
    reset_btn = QPushButton("초기화", frame)
    reset_btn.setFixedSize(btn_w, btn_h)
    reset_btn.setStyleSheet(
        "QPushButton {background:#e74c3c; color:white; border:none; border-radius:4px; font-size:10px;} "
        "QPushButton:hover{background:#ec7063;} "
        "QPushButton:pressed{background:#c0392b;}"
    )
    grid_w = cols * btn_w + (cols-1) * gap_x
    reset_x = x0 + (grid_w - btn_w) // 2
    reset_y = y0 + rows * row_h + 8
    reset_btn.move(reset_x, reset_y)

    def _reset_all():
        for j in range(9):
            coords[j] = None
            coord_labels[j].setText("(0,0)")
            try: coord_labels[j].adjustSize()
            except Exception: pass
            buttons[j].setText(f"점프{j+1}")
            left_checks[j].setChecked(False)
            right_checks[j].setChecked(False)
    reset_btn.clicked.connect(_reset_all)

    # 프레임 크기 계산 (앵커 폭 사용, 최소 그리드 폭 보장)
    min_w = max(200, grid_w + x0 + 90)  # 좌표 레이블 폭 고려
    total_h = reset_y + btn_h + 8
    frame.setFixedSize(max(min_w, anchor_frame.width()), total_h)

    # 배치 함수: 앵커 바로 아래
    def _place():
        try:
            frame.setFixedWidth(max(min_w, anchor_frame.width()))
            frame.move(anchor_frame.x(), anchor_frame.y() + anchor_frame.height() + 6)
        except Exception:
            pass
    _place()

    # 보조 함수: 저장된 좌표에 맞춰 버튼/레이블 일괄 갱신
    def _refresh_all():
        try:
            for k in range(9):
                c = coords[k]
                if c:
                    coord_labels[k].setText(f"({c[0]},{c[1]})")
                    try: coord_labels[k].adjustSize()
                    except Exception: pass
                    buttons[k].setText(f"점프{k+1} ({c[0]},{c[1]})")
                else:
                    coord_labels[k].setText("(0,0)")
                    try: coord_labels[k].adjustSize()
                    except Exception: pass
                    buttons[k].setText(f"점프{k+1}")
        except Exception:
            pass

    # 참조 보관
    frame.jump_title = title
    frame.jump_enable_chk = chk
    frame.jump_buttons = buttons
    frame.jump_left_checks = left_checks
    frame.jump_right_checks = right_checks
    frame.jump_coord_labels = coord_labels
    frame.jump_coords = coords
    frame.jump_reset_btn = reset_btn
    frame.place_jump = _place
    frame.refresh_all = _refresh_all

    return frame


# --------- 런타임 로직 ---------
_run_flag = False
_thread = None


def _should_trigger(dir_name: str, left_on: bool, right_on: bool) -> bool:
    if left_on and right_on:
        return True
    if left_on and dir_name == 'left':
        return True
    if right_on and dir_name == 'right':
        return True
    return False


def _match_coord(cx: int, cy: int, x0: int, y0: int) -> bool:
    try:
        if cx == x0 and abs(cy - y0) <= 3:
            return True
    except Exception:
        pass
    return False


def _loop(get_frame):
    global _run_flag
    last_match = [False]*9
    next_ok = [0.0]*9  # per-slot 쿨다운
    while _run_flag:
        try:
            frame = get_frame()
            if not frame:
                time.sleep(0.1); continue
            if not getattr(frame, 'jump_enable_chk', None) or not frame.jump_enable_chk.isChecked():
                time.sleep(0.05); continue
            try:
                import minimap
                cx = getattr(minimap, 'current_x', None)
                cy = getattr(minimap, 'current_y', None)
                if cx is None or cy is None:
                    time.sleep(0.02); continue
                cx = int(cx); cy = int(cy)
            except Exception:
                time.sleep(0.05); continue
            try:
                import start_stop as ss
                cur_dir = getattr(ss, 'current_key', None)
            except Exception:
                cur_dir = None
            now = time.time()
            for i in range(9):
                try:
                    coord = frame.jump_coords[i]
                    if not coord:
                        last_match[i] = False
                        continue
                    x0, y0 = coord
                    m = _match_coord(cx, cy, x0, y0)
                    # 방향 조건
                    allow = False
                    if cur_dir in ('left','right'):
                        allow = _should_trigger(cur_dir, frame.jump_left_checks[i].isChecked(), frame.jump_right_checks[i].isChecked())
                    # 둘 다 체크 안 했으면 동작 안 함
                    if not allow and not (frame.jump_left_checks[i].isChecked() and frame.jump_right_checks[i].isChecked()):
                        allow = False
                    # 트리거: 매칭 상승엣지 + 방향 허용 + 쿨다운
                    if m and not last_match[i] and allow and now >= next_ok[i]:
                        try:
                            pdi.keyDown('alt'); time.sleep(0.02)
                        except Exception:
                            pass
                        finally:
                            try: pdi.keyUp('alt')
                            except Exception: pass
                        next_ok[i] = now + 0.2
                    last_match[i] = m
                except Exception:
                    pass
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
            return getattr(bf, 'jump_sys_frame', None)
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