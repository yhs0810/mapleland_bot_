from PyQt5.QtWidgets import QFrame, QLabel, QPushButton, QCheckBox, QLineEdit, QWidget
from PyQt5.QtCore import Qt

# 외부 로직에서 접근할 수 있도록 글로벌 리스트 보유
jump_blocks = []  # type: list


def _create_row(parent: QWidget, idx:int):
    """하나의 점프다운 블록 생성 (2x2 그리드)"""
    # ===== 행/열 계산 =====
    row = idx // 2  # 0,1
    col = idx % 2   # 0,1

    # 패널 중앙 기준 좌우 균형 잡기 (패널 너비 350 - 그리드폭 320 = 30 -> 좌측 여백 15)
    base_x = 15 + col * 160  # 컬럼별 x 시프트
    y_offset = 26 + row * 70  # 행별 y 위치 (1px 내려서 26)

    # 체크박스(메인)
    main_chk = QCheckBox(parent)
    main_chk.move(base_x, y_offset)

    # label
    lbl = QLabel("점프다운:", parent)
    lbl.setStyleSheet("color:#dcdcdc; font-size:10px;")
    lbl.move(base_x + 20, y_offset + 1)

    # coord button
    coord_btn = QPushButton("(0,0)", parent)
    # 크기 추가 20% 축소 (현재 42x14 → 34x11)
    coord_btn.setFixedSize(34,11)
    coord_btn.setStyleSheet("QPushButton {background:#5d5d5d; color:white; font-size:9px; border:none;} QPushButton:hover{background:#6f6f6f;} QPushButton:pressed{background:#4d4d4d;}")
    # 레이블 바로 오른쪽에 붙여 배치
    label_width = lbl.fontMetrics().boundingRect(lbl.text()).width()
    coord_x = lbl.x() + label_width + 5
    coord_btn.move(coord_x, y_offset + 1)  # 1px 아래로

    # 무시횟수 라벨과 입력창을 레이블 바로 아래 배치
    skip_y = y_offset + 16  # 1px 함께 이동
    skip_lbl = QLabel("무시횟수:", parent)
    skip_lbl.setStyleSheet("color:#dcdcdc; font-size:10px;")
    skip_lbl.move(base_x + 20, skip_y)
    skip_edit = QLineEdit(parent)
    # 인풋창을 coord 버튼 크기와 동일하게 설정
    skip_edit.setFixedSize(34,11)
    # coord 버튼과 동일 x 좌표로 배치
    skip_edit.move(coord_x, skip_y)

    # 층 체크박스들: coord 버튼 이후에 수평으로 나열
    # 점프다운 메인 체크박스 x값에 맞추어 시작
    floor_start_x = main_chk.x()
    from functools import partial

    c_list = []  # 객체 리스트 수집 용도

    # ----------- 블록 객체 미리 생성 (다음 루프에서 참조) -----------
    blk = type("JumpBlock", (object,), {})()

    for col, floor in enumerate(["1층", "2층", "3층", "4층"]):
        c = QCheckBox(floor, parent)
        c.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;} QCheckBox::indicator{width:10px;height:10px;}")
        # 간격을 약간 더 주어 36px 로 조정
        cx_pos = floor_start_x + col*36
        cy_pos = skip_y + 17
        c.move(cx_pos, cy_pos)

        # 빨간 X 표시 라벨 (초기 hidden)
        x_lbl = QLabel("✕", parent)
        x_lbl.setFixedSize(10,10)
        x_lbl.setAlignment(Qt.AlignCenter)
        x_lbl.setStyleSheet("color:#e74c3c; font-size:8px; margin:0px; padding:0px;")
        x_lbl.move(cx_pos, cy_pos)
        x_lbl.hide()
        c.x_label = x_lbl

        # ---- 같은 블록 내 배타만 적용 (교차 배타 제거) ----
        idx_floor = col  # 0~3

        def _chk_toggled(state, blk_ref=None, floor_idx=idx_floor):
            # 블록 내부에서만 상호 배타
            if blk_ref is not None:
                if state:
                    # 체크되면 동일 블록 다른 층 disable & uncheck
                    for i, fc2 in enumerate(blk_ref.floor_checks):
                        if i != floor_idx:
                            fc2.setChecked(False)
                            fc2.setEnabled(False)
                            fc2.x_label.show()
                else:
                    # 해제 시 동일 블록 내 남은 체크 없으면 모두 enable
                    if all(not fc.isChecked() for fc in blk_ref.floor_checks):
                        for fc2 in blk_ref.floor_checks:
                            fc2.setEnabled(True)
                            fc2.x_label.hide()

        # lambda capture default problems, use default arg
        c.toggled.connect(partial(_chk_toggled, blk_ref=blk, floor_idx=idx_floor))

        # 객체 리스트 수집 용도
        c_list.append(c)

    # ----------- 객체 정보 보관 -----------
    blk.main_chk = main_chk
    blk.coord_btn = coord_btn
    blk.skip_edit = skip_edit
    blk.floor_checks = c_list
    blk.coord = None
    blk.prev_floor = None
    blk.triggered = False
    # second attempt 제거
    blk.down_until = 0.0
    blk.next_trigger = 0.0

    # 좌표 기록 버튼 동작
    def _record_coord():
        import minimap
        if minimap.current_x is not None and minimap.current_y is not None:
            blk.coord = (minimap.current_x, minimap.current_y)
            coord_btn.setText(f"{minimap.current_x},{minimap.current_y}")

    coord_btn.clicked.connect(_record_coord)

    jump_blocks.append(blk)

    # 필요하다면 위젯 속성 노출 가능 (row 위젯 제거)
    # 함수는 값을 반환하지 않음



def create_jumpdown_ui(parent_widget:QWidget, anchor_widget:QWidget):
    """사다리 패널 바로 아래 점프다운 패널 생성"""
    panel = QFrame(parent_widget)
    panel.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    # 2행 레이아웃에 맞춰 여백 최소화
    panel.setFixedSize(350, 155)

    title = QLabel("점프다운", panel)
    title.setStyleSheet("color:#f1c40f; font-size:12px; font-weight:bold;")
    title.move(5,2)

    # 4개의 블록을 2x2 그리드로 생성
    for i in range(4):
        _create_row(panel, i)

    # 위치 anchor 아래
    def reposition():
        panel.move(anchor_widget.x(), anchor_widget.y()+anchor_widget.height()+10)
    reposition()

    # anchor resize follow
    orig = parent_widget.resizeEvent if hasattr(parent_widget,'resizeEvent') else None
    def new_resize(e):
        if orig: orig(e)
        reposition()
    parent_widget.resizeEvent = new_resize
    return panel
