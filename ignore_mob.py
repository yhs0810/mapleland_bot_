from PyQt5.QtWidgets import QFrame, QLabel, QWidget, QPushButton
import os, json

# 저장 파일 경로
_CONFIG_FILE = os.path.join('config', 'ignore_mob.json')
# 파일 저장/로드 사용 여부 (False: 저장하지 않음)
PERSIST_IGNORE_COORDS = False

# 좌표 저장소 (모듈 전역)
_LEFT_COORDS = [None]*9   # 각 원소: (x, y) 또는 None
_RIGHT_COORDS = [None]*9  # 각 원소: (x, y) 또는 None

def _ensure_dir():
    try:
        os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
    except Exception:
        pass

def save_state():
    _ensure_dir()
    try:
        data = {
            'left': [list(v) if isinstance(v, tuple) else v for v in _LEFT_COORDS],
            'right': [list(v) if isinstance(v, tuple) else v for v in _RIGHT_COORDS]
        }
        with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

def load_state():
    global _LEFT_COORDS, _RIGHT_COORDS
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            left = data.get('left', [None]*9)
            right = data.get('right', [None]*9)
            _LEFT_COORDS = [tuple(v) if isinstance(v, (list, tuple)) and len(v)==2 else None for v in left]
            _RIGHT_COORDS = [tuple(v) if isinstance(v, (list, tuple)) and len(v)==2 else None for v in right]
    except Exception:
        pass

def is_blocked(cx: int, cy: int) -> bool:
    try:
        if cx is None or cy is None:
            return False
        # L/R 두 점을 잇는 축정렬 사각형 내부면 차단
        for i in range(9):
            l = _LEFT_COORDS[i]
            r = _RIGHT_COORDS[i]
            if not (isinstance(l, tuple) and isinstance(r, tuple) and len(l)==2 and len(r)==2):
                continue
            lx, ly = int(l[0]), int(l[1])
            rx, ry = int(r[0]), int(r[1])
            x_min, x_max = (lx, rx) if lx <= rx else (rx, lx)
            y_min, y_max = (ly, ry) if ly <= ry else (ry, ly)
            if x_min <= cx <= x_max and y_min <= cy <= y_max:
                return True
    except Exception:
        return False
    return False


def create_ignore_mob_ui(parent: QWidget, jump_frame: QFrame) -> QFrame:
    frame = QFrame(parent)
    frame.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")

    title = QLabel("몬스터 미감지 좌표 설정", frame)
    title.setStyleSheet("color:#f1c40f; font-size:12px; font-weight:bold;")
    title.move(6, 2)
    try:
        title.adjustSize()
    except Exception:
        pass

    # 3x3 L/R 버튼 그리드 생성
    btns_left = []
    btns_right = []
    base_style = (
        "QPushButton {background:#5a5a5a; color:#dcdcdc; border:1px solid #777; border-radius:3px; font-size:10px;} "
        "QPushButton:hover{background:#6a6a6a;} "
        "QPushButton:pressed{background:#4a4a4a;} "
        "QPushButton:checked{background:#7a7a7a; border:1px solid #aaa;}"
    )
    for i in range(9):
        lb = QPushButton("L", frame); lb.setCheckable(True); lb.setStyleSheet(base_style); lb.setFixedSize(18,16)
        rb = QPushButton("R", frame); rb.setCheckable(True); rb.setStyleSheet(base_style); rb.setFixedSize(18,16)
        btns_left.append(lb)
        btns_right.append(rb)

    # 하단 초기화 버튼
    reset_btn = QPushButton("초기화", frame)
    reset_btn.setStyleSheet(
        "QPushButton {background:#e74c3c; color:white; border:none; border-radius:4px; font-size:10px;} "
        "QPushButton:hover{background:#ec7063;} "
        "QPushButton:pressed{background:#c0392b;}"
    )
    reset_btn.setFixedSize(60, 18)

    def _reset_all():
        global _LEFT_COORDS, _RIGHT_COORDS
        try:
            _LEFT_COORDS = [None]*9
            _RIGHT_COORDS = [None]*9
            for j in range(9):
                btns_left[j].setChecked(False)
                btns_right[j].setChecked(False)
                btns_left[j].setToolTip("")
                btns_right[j].setToolTip("")
            if PERSIST_IGNORE_COORDS:
                save_state()
        except Exception:
            pass
    reset_btn.clicked.connect(_reset_all)

    # 레이아웃 계산/배치
    def _layout():
        try:
            margin_x = 6
            margin_top = 6
            gap_col = 6
            gap_row = 8
            inner_gap = 4  # L/R 사이 간격
            cols = 3
            rows = 3

            title_h = title.sizeHint().height() if hasattr(title, 'sizeHint') else title.height()
            grid_top = title.y() + title_h + margin_top

            # 하단 초기화 버튼 영역 보장
            reset_h = reset_btn.height()
            bottom_margin = 6
            grid_bottom_limit = frame.height() - bottom_margin - reset_h - 6  # reset 위 여유 6
            grid_height = max(0, grid_bottom_limit - grid_top)

            avail_w = max(0, frame.width() - margin_x*2)
            col_w = max(30, (avail_w - gap_col*(cols-1)) // cols)
            row_h = max(16, (grid_height - gap_row*(rows-1)) // rows) if grid_height > 0 else 20

            # 버튼 크기: 셀 폭에 맞춤
            btn_w = max(18, (col_w - inner_gap) // 2)
            btn_h = max(16, min(20, row_h - 2))

            # 배치
            for i in range(9):
                r = i // cols
                c = i % cols
                cell_x = 6 + c * (col_w + gap_col)
                cell_y = grid_top + r * (row_h + gap_row)
                lb = btns_left[i]
                rb = btns_right[i]
                lb.setFixedSize(btn_w, btn_h)
                rb.setFixedSize(btn_w, btn_h)
                lb.move(cell_x, cell_y)
                rb.move(cell_x + btn_w + inner_gap, cell_y)

            # 초기화 버튼 하단 중앙
            reset_x = 6 + (avail_w - reset_btn.width()) // 2
            reset_y = frame.height() - bottom_margin - reset_btn.height()
            reset_btn.move(max(6, reset_x), max(grid_top, reset_y))
        except Exception:
            pass

    # 상태 로드 후 버튼 표시 갱신 (지속 저장 사용 시에만)
    try:
        if PERSIST_IGNORE_COORDS:
            load_state()
            for i in range(9):
                l = _LEFT_COORDS[i]; r = _RIGHT_COORDS[i]
                btns_left[i].setChecked(bool(l))
                btns_right[i].setChecked(bool(r))
                if l: btns_left[i].setToolTip(f"L: {l[0]},{l[1]}")
                if r: btns_right[i].setToolTip(f"R: {r[0]},{r[1]}")
    except Exception:
        pass

    # 캡처 핸들러 연결
    def _capture(idx: int, side: str):
        global _LEFT_COORDS, _RIGHT_COORDS
        try:
            import minimap
            cx = getattr(minimap, 'current_x', None)
            cy = getattr(minimap, 'current_y', None)
            if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
                val = (int(cx), int(cy))
                if side == 'L':
                    _LEFT_COORDS[idx] = val
                    btns_left[idx].setChecked(True)
                    btns_left[idx].setToolTip(f"L: {val[0]},{val[1]}")
                else:
                    _RIGHT_COORDS[idx] = val
                    btns_right[idx].setChecked(True)
                    btns_right[idx].setToolTip(f"R: {val[0]},{val[1]}")
                if PERSIST_IGNORE_COORDS:
                    save_state()
        except Exception:
            pass

    for i in range(9):
        btns_left[i].clicked.connect(lambda checked=False, idx=i: _capture(idx, 'L'))
        btns_right[i].clicked.connect(lambda checked=False, idx=i: _capture(idx, 'R'))

    # 점프 프레임과 거의 동일 크기(오른쪽만 2px 줄임 → 폭: jump-4)
    try:
        frame.setFixedSize(max(0, jump_frame.width() - 4), jump_frame.height())
    except Exception:
        pass

    # 점프 프레임의 왼쪽에 바로 붙여 배치: 왼쪽 가장자리는 유지, 오른쪽만 2px 줄어들도록 계산
    def _place():
        try:
            # 기준 왼쪽(기존 규칙: 폭 jump-2, 간격 12)
            left_old = (jump_frame.x() - max(0, jump_frame.width() - 2) - 12)
            # 새 폭은 jump-4 (오른쪽만 2 줄임)
            frame.setFixedSize(max(0, jump_frame.width() - 4), jump_frame.height())
            frame.move(left_old, jump_frame.y())
            _layout()
        except Exception:
            pass

    _place()

    # 프레임 리사이즈 시 내부 그리드 재배치
    try:
        orig_resize = getattr(frame, 'resizeEvent', None)
        def _on_resize(ev):
            try:
                if orig_resize:
                    orig_resize(ev)
            except Exception:
                pass
            _layout()
        frame.resizeEvent = _on_resize
    except Exception:
        pass

    # 참조 보관
    frame.ignore_title = title
    frame.ignore_left_buttons = btns_left
    frame.ignore_right_buttons = btns_right
    frame.ignore_reset_btn = reset_btn
    frame.ignore_left_coords = _LEFT_COORDS
    frame.ignore_right_coords = _RIGHT_COORDS
    frame.place_ignore = _place
    frame.layout_ignore = _layout

    return frame
