from PyQt5.QtWidgets import QCheckBox

def create_no_turn_checkbox(parent):
    chk = QCheckBox("방향전환X", parent)
    chk.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
    chk.setChecked(False)
    return chk
