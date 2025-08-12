import os, sys, pyautogui, cv2, numpy as np
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QEventLoop
from PyQt5.QtGui import QPainter, QPen, QColor
import minimap
import training_fun

IGN_DIR = os.path.join('imgs', 'ign')
IGN_PATH = os.path.join(IGN_DIR, 'ign.png')

_selected_region = None  # 내부 전역

def _overlay_show_and_select():
    """풀스크린 오버레이 표시 후 영역 선택, 선택되지 않으면 None 반환"""
    app = QApplication.instance() or QApplication(sys.argv)

    overlay = QWidget()
    overlay.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    overlay.setAttribute(Qt.WA_TranslucentBackground)
    geo = QApplication.primaryScreen().geometry()
    overlay.setGeometry(geo)

    state = { 'start':None, 'end':None, 'region':None }

    def paint_event(_):
        if state['start'] and state['end']:
            qp = QPainter(overlay)
            qp.setPen(QPen(QColor(0,255,0),2))
            x=min(state['start'].x(),state['end'].x())
            y=min(state['start'].y(),state['end'].y())
            w=abs(state['end'].x()-state['start'].x())
            h=abs(state['end'].y()-state['start'].y())
            qp.drawRect(x,y,w,h)

    def mouse_press(e):
        state['start']=e.pos();state['end']=e.pos();overlay.update()
    def mouse_move(e):
        state['end']=e.pos();overlay.update()
    def mouse_release(e):
        state['end']=e.pos()
        x=min(state['start'].x(),state['end'].x())
        y=min(state['start'].y(),state['end'].y())
        w=abs(state['end'].x()-state['start'].x())
        h=abs(state['end'].y()-state['start'].y())
        if w>5 and h>5:
            state['region']=(x,y,w,h)
        overlay.close()

    overlay.paintEvent=paint_event
    overlay.mousePressEvent=mouse_press
    overlay.mouseMoveEvent=mouse_move
    overlay.mouseReleaseEvent=mouse_release

    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    loop = QEventLoop()
    overlay.destroyed.connect(loop.quit)
    loop.exec_()
    return state['region']

def capture_ign():
    """오버레이로 영역 선택 후 imgs/ign/ign.png 저장, 성공 시 경로 반환"""
    # minimap 방식 오버레이 사용
    region=minimap.capture_minimap()
    if not region:
        return None
    screenshot=pyautogui.screenshot(region=region)
    frame=cv2.cvtColor(np.array(screenshot),cv2.COLOR_RGB2BGR)
    os.makedirs(IGN_DIR,exist_ok=True)
    cv2.imwrite(IGN_PATH,frame)
    # 템플릿 갱신
    training_fun.reload_ign_template()
    return IGN_PATH
