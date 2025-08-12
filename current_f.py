from PyQt5.QtWidgets import QLabel

# 전역 저장 변수
first_floor_y = None
current_floor = None

def set_first_floor_y(y):
    global first_floor_y
    first_floor_y = y

def set_current_floor(f):
    global current_floor
    current_floor = f


def create_floor_ui(parent_widget):
    """왼쪽 하단에 현재층 레이블 생성"""
    label = QLabel("현재층:",parent_widget)
    label.setStyleSheet("border:1px solid black; padding:2px; background:#fafafa; font-size:10px;")
    label.setFixedWidth(59)  # 오른쪽 1px 추가 제거
    label.setFixedHeight(22)  # 세로 크기 확장

    def reposition():
        base_x = 11
        try:
            import start_stop
            # 시작 버튼 바로 위쪽에 배치
            # start_stop.create_start_stop_ui 내부에서 버튼이 배치되므로 위치를 직접 참조하기 어렵다.
            # 대신 '시작' 버튼을 탐색하여 y를 가져온다.
            from PyQt5.QtWidgets import QPushButton
            buttons = [w for w in parent_widget.findChildren(QPushButton) if w.text()=="시작"]
            if buttons:
                start_btn = buttons[0]
                y = start_btn.y() - label.height() - 4
            else:
                y = parent_widget.height() - 83
        except Exception:
            y = parent_widget.height() - 83
        label.move(base_x, y)

    reposition()

    original_resize = getattr(parent_widget, "resizeEvent", None)

    def new_resize(event):
        if original_resize:
            original_resize(event)
        reposition()

    parent_widget.resizeEvent = new_resize

    return label
