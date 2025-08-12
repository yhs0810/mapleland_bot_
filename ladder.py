from PyQt5.QtWidgets import (
    QFrame, QCheckBox, QLabel, QWidget, QLineEdit, QPushButton
)
from PyQt5.QtCore import Qt

ladder_blocks = []  # 외부 모듈에서 접근


def _create_block(parent: QWidget, idx: int):
    """하나의 사다리 블록 UI 생성 (기능 없이 디자인만)"""
    block = QFrame(parent)
    block.setStyleSheet("background:#6a6a6a; border:1px solid #444;")
    block.setFixedSize(110, 100)

    # 체크박스 + 라벨
    chk = QCheckBox(block)
    chk.setText("")
    chk.move(4, 4)
    chk.setStyleSheet("QCheckBox::indicator { width: 11px; height: 11px; }")

    name = QLabel(f"사다리{idx}", block)
    name.setStyleSheet("color:#dcdcdc; font-size:10px;")
    name.move(33, 5)

    # 빨간색 버튼 모양 레이블들 (좌표, 초기화)
    btn1 = QPushButton("좌표", block)
    btn1.setStyleSheet("QPushButton {background:#7d7d7d; color:white; font-size:9px; border:none;} QPushButton:hover{background:#9e9e9e;} QPushButton:pressed{background:#6a6a6a;}")
    btn1.setFixedSize(100, 12)
    btn1.move(5, 18)

    # 위치 교체: 목표를 원래 초기화 자리에, 초기화를 목표 자리로
    goal = QPushButton("목표(0)", block)
    goal.setStyleSheet("QPushButton {background:#2962ff; color:white; font-size:9px; border:none;} QPushButton:hover{background:#447bff;} QPushButton:pressed{background:#1e4bd8;}")
    goal.setFixedSize(100, 12)
    goal.move(5, 33)

    btn2 = QPushButton("초기화", block)
    btn2.setStyleSheet("QPushButton {background:#c0392b; color:white; font-size:9px; border:none;} QPushButton:hover{background:#e74c3c;} QPushButton:pressed{background:#a93226;}")
    btn2.setFixedSize(100, 12)
    btn2.move(5, 48)

    # 무시 / 층 입력
    ign_lbl = QLabel("무시:", block)
    ign_lbl.setStyleSheet("color:#dcdcdc; font-size:9px;")
    ign_lbl.move(5, 65)
    ign_edit = QLineEdit(block)
    ign_edit.setFixedSize(24, 12)
    ign_edit.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:8px;}")
    ign_edit.move(ign_lbl.x() + 28, 65)

    fl_lbl = QLabel("층:", block)
    fl_lbl.setStyleSheet("color:#dcdcdc; font-size:9px;")
    fl_lbl.move(ign_edit.x() + ign_edit.width() + 4, 65)
    fl_edit = QLineEdit(block)
    fl_edit.setFixedSize(24, 12)
    fl_edit.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:8px;}")
    fl_edit.move(fl_lbl.x() + 18, 65)

    # 좌/우 체크박스 하단
    chk_left = QCheckBox("좌", block)
    chk_left.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;} QCheckBox::indicator{width:10px; height:10px;}")
    chk_left.move(5, 80)

    chk_right = QCheckBox("우", block)
    chk_right.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;} QCheckBox::indicator{width:10px; height:10px;}")
    chk_right.move(61, 80)

    # 좌/우 상호 배타 설정
    def _left_toggled(state):
        if state:
            chk_right.blockSignals(True)
            chk_right.setChecked(False)
            chk_right.blockSignals(False)

    def _right_toggled(state):
        if state:
            chk_left.blockSignals(True)
            chk_left.setChecked(False)
            chk_left.blockSignals(False)

    chk_left.toggled.connect(_left_toggled)
    chk_right.toggled.connect(_right_toggled)

    # 상태 저장용 속성 부여
    block.main_chk = chk
    block.chk_left = chk_left
    block.chk_right = chk_right
    block.btn_coord = btn1
    block.btn_reset = btn2
    block.btn_goal = goal
    block.ign_edit = ign_edit
    block.floor_edit = fl_edit
    block.coord = None  # (x, y)
    block.goal_y = None
    block.up_active = False  # up 키 눌린 상태 추적
    block.pending_up = False
    block.alt_time = 0.0
    block.pre_y = 0
    block.start_t = 0

    def record_coord():
        import minimap
        if minimap.current_x is not None and minimap.current_y is not None:
            block.coord = (minimap.current_x, minimap.current_y)
            btn1.setText(f"{minimap.current_x},{minimap.current_y}")

    btn1.clicked.connect(record_coord)

    def record_goal():
        import minimap
        if minimap.current_y is not None:
            block.goal_y = minimap.current_y
            goal.setText(f"목표({block.goal_y})")

    goal.clicked.connect(record_goal)

    def reset_all():
        block.coord = None
        block.goal_y = None
        btn1.setText("좌표")
        goal.setText("목표(0)")
        ign_edit.setText("")
        fl_edit.setText("")
        chk_left.setChecked(False)
        chk_right.setChecked(False)
        chk.setChecked(False)

    btn2.clicked.connect(reset_all)

    return block


def create_ladder_ui(parent_widget, canvas_widget):
    """캔버스 왼쪽에 사다리 패널(3x3 블록) 생성"""
    panel = QFrame(parent_widget)
    panel.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    panel.setFixedSize(350, 327)  # 하단 여백 3px 더 제거

    # 블록 배치
    margin = 5
    cols = 3
    for i in range(9):
        block = _create_block(panel, i + 1)
        ladder_blocks.append(block)
        row = i // cols
        col = i % cols
        x = margin + col * (block.width() + margin)
        y = margin + row * (block.height() + margin)
        block.move(x, y)

    def reposition():
        x = canvas_widget.x() - panel.width() - 10
        y = canvas_widget.y()
        panel.move(x, y)

    reposition()

    original_resize = getattr(parent_widget, "resizeEvent", None)

    def new_resize(event):
        if original_resize:
            original_resize(event)
        reposition()

    parent_widget.resizeEvent = new_resize

    return panel 