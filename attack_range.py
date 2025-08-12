from PyQt5.QtWidgets import QFrame, QLabel, QLineEdit, QWidget
from PyQt5.QtCore import Qt

def create_attack_range_ui(parent: QWidget, anchor_widget: QWidget):
    """IGN 좌표 레이블 기준 좌측 하단에 배치되는 공격 범위 설정 프레임 생성"""
    # 패널 스타일 다른 프레임과 동일(#4a4a4a 배경, 라운드)
    panel = QFrame(parent)
    panel.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    panel.setFixedSize(140, 115)

    # 위치: anchor_widget 왼쪽 아래 정렬
    ax = anchor_widget.x()
    ay = anchor_widget.y() + anchor_widget.height() + 4
    panel.move(ax, ay)

    labels = [
        "Y최소값:",
        "Y최대값:",
        "왼쪽최소:",
        "왼쪽최대:",
        "오른쪽최소:",
        "오른쪽최대:",
        "반대몹 감지:",
    ]
    defaults = ["-50", "50", "-50", "-1", "1", "50", "50"]
    edits = []
    lbls = []
    y_offset = 4
    for idx, (txt, dval) in enumerate(zip(labels, defaults)):
        lbl = QLabel(txt, panel)
        lbl.setStyleSheet("color:#dcdcdc; font-size:9px;")
        lbl.move(6, y_offset+idx*15)
        edit = QLineEdit(panel)
        edit.setFixedSize(40, 12)
        edit.setText(dval)
        edit.setStyleSheet("QLineEdit {background:#ffffff; border:1px solid #888; font-size:8px;}")
        edit.move(panel.width()-46, y_offset+idx*15)
        edits.append(edit)
        lbls.append(lbl)

    # 참조용 속성 보관
    panel.edits = edits
    panel.labels = lbls

    adjust_layout(panel)  # initial layout based on current height
    return panel


# --------------------------------------------------
# 헬퍼: 현재 입력값 반환 (ymin,ymax,xmin_left,xmax_left) => (dy_min,dy_max,dx_min,dx_max, mob_detect)
# --------------------------------------------------
def get_ranges(panel_global=None):
    """현재 패널 입력값을 정수로 파싱하여 (dy_min, dy_max, dx_left_min, dx_left_max, mob_detect) 반환.
    panel_global 은 create_attack_range_ui 가 반환한 패널 객체. 없으면 None -> 반환 None.
    """
    try:
        if panel_global is None:
            return None
        ed = getattr(panel_global, 'edits', None)
        if not ed or len(ed) < 7:
            return None
        vals = []
        for e in ed:
            try:
                vals.append(int(e.text()))
            except ValueError:
                vals.append(0)
        # 순서: y_min,y_max,x_left_min,x_left_max,x_right_min,x_right_max,mob_detect
        return tuple(vals)
    except Exception:
        return None


def adjust_layout(panel: QFrame):
    """재배치: 현재 패널 높이에 맞춰 행들을 균등 분포"""
    rows = len(getattr(panel, 'edits', []))
    if rows == 0:
        return
    row_h = 15  # 각 행 높이(라벨 폰트 기준)
    avail_h = panel.height()
    margin = max(2, (avail_h - rows * row_h) // (rows + 1))
    y = margin
    for idx in range(rows):
        lbl = panel.labels[idx]
        edit = panel.edits[idx]
        lbl.move(6, y)
        edit.move(panel.width() - 46, y)
        y += row_h + margin
    panel.update()
