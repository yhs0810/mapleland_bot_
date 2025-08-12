from PyQt5.QtWidgets import QCheckBox

def create_chase_checkbox(parent):
    """공격 설정 프레임에 들어갈 몹추적 체크박스 생성"""
    chk = QCheckBox("몹추적", parent)
    chk.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
    chk.setChecked(False)
    return chk
