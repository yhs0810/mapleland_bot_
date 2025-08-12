from PyQt5.QtWidgets import QLabel, QLineEdit, QPushButton
import minimap
import current_f


def create_boundary_ui(parent_widget):
    """왼쪽 하단에 1층L/R 입력 UI 배치"""
    # 요소 생성
    l_label = QLabel("1층L:", parent_widget)
    l_input = QLineEdit(parent_widget)
    l_input.setFixedWidth(25)
    l_input.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:9px;}")

    r_label = QLabel("1층R:", parent_widget)
    r_input = QLineEdit(parent_widget)
    r_input.setFixedWidth(25)
    r_input.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:9px;}")

    # 2~9층 L/R 생성
    floor_labels = []  # list of (l_label, l_input, r_label, r_input)
    for f in range(2, 9):
        l_lbl = QLabel(f"{f}층L:", parent_widget)
        l_in = QLineEdit(parent_widget); l_in.setFixedWidth(25)
        l_in.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:9px;}")
        r_lbl = QLabel(f"{f}층R:", parent_widget)
        r_in = QLineEdit(parent_widget); r_in.setFixedWidth(25)
        r_in.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:9px;}")
        floor_labels.append((l_lbl, l_in, r_lbl, r_in))

    y_button = QPushButton("1층Y", parent_widget)
    y_button.setFixedSize(60, 25)

    def update_y():
        if minimap.current_y is not None:
            current_f.set_first_floor_y(minimap.current_y)
            y_button.setText(f"1층Y:{minimap.current_y}")
    y_button.clicked.connect(update_y)

    # 배치 함수 정의
    def reposition():
        base_x = 10
        base_y = parent_widget.height() - l_label.height() + 5  # 하단에서 5px 여유
        l_label.move(base_x, base_y)
        l_input.move(base_x + 33, base_y - 2)
        r_label.move(base_x + 63, base_y + 2)
        r_input.move(base_x + 98, base_y -2)
        y_button.move(base_x + 130, base_y - 5)  # 3px 더 왼쪽 이동

        # 2~9층을 수평으로 배치, 10px 간격
        x_base = y_button.x() + y_button.width() + 10
        step = 130  # tighter spacing per floor segment
        for idx,(l_lbl,l_in,r_lbl,r_in) in enumerate(floor_labels):
            x_offset = x_base + idx*step
            l_lbl.move(x_offset, base_y + 2)
            l_in.move(x_offset + 35, base_y -2)
            r_lbl.move(x_offset + 65, base_y +2)
            r_in.move(x_offset + 100, base_y -2)

    # 첫 배치
    reposition()

    # 부모 resize 이벤트 훅
    original_resize = getattr(parent_widget, "resizeEvent", None)

    def new_resize(event):
        if original_resize:
            original_resize(event)
        reposition()
    parent_widget.resizeEvent = new_resize


    # collect all inputs
    extras = []
    for _,l_in,_,r_in in floor_labels:
        extras.extend([l_in,r_in])
    # 전역 dict 로 노출: {층번호:(l_input,r_input)}
    global FLOOR_INPUTS
    FLOOR_INPUTS = {1:(l_input,r_input)}
    for idx,(l_in,r_in) in enumerate([(l_in,r_in) for _,l_in,_,r_in in floor_labels],start=2):
        FLOOR_INPUTS[idx]=(l_in,r_in)

    return (l_input, r_input, y_button, *extras)