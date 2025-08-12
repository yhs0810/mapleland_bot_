import tkinter as tk
import mss
import numpy as np
import cv2
import glob
import os
import threading
import time
from PIL import Image, ImageTk
from concurrent.futures import ThreadPoolExecutor
from numba import njit, int32
import pygame  # pygame 사용
import multiprocessing
import winsound  # winsound 라이브러리 추가
import gc  # 가비지 컬렉션 추가
import minimap  # minimap 모듈 import 추가
from OpenGL.GL import *  # OpenGL 함수 import
from PyQt5.QtWidgets import QPushButton, QMessageBox, QApplication  # QApplication 추가
from PyQt5.QtCore import Qt, QTimer, QFileSystemWatcher  # Qt 플래그/타이머/디렉토리 감시

# 전역 변수
hunting_region = None
is_hunting_capturing = False

IGN_TEMPLATE=None
IGN_W=IGN_H=0
THRESH=0.60
USE_GPU_IGN=False  # CUDA 금지
USE_OPENCL=False   # OpenCL 비활성화 (CPU 전용)
MONSTER_TEMPLATES = []  # [(name, tpl_gray, tw, th, tpl_bgr)]
MON_THRESH = 100.0  # 50~100 (percent)
MON_DIR = os.path.join('imgs','monster')
_MON_SNAPSHOT = None
_MON_WATCHER = None
_MON_TIMER = None

# 실시간 공유 좌표
CURRENT_IGN = None  # (x,y)
MON_POS = []        # list[(x,y)]

# 루루모(매크로방지) 템플릿/임계치/알람
RURU_TEMPLATES = []  # list[(tpl_gray, tw, th, tpl_bgr)]
RURU_THRESH = 0.90
_RURU_ALARM_LAST = 0.0
_RURU_TG_LAST = 0.0

# 자동경비 템플릿/상태
GUARD_TEMPLATES = []  # list[(tpl_gray, tw, th, tpl_bgr)]
GUARD_THRESH = 0.90
_GUARD_ALARM_LAST = 0.0
_GUARD_TG_LAST = 0.0

# 디트와 로이 템플릿/상태
DITROI_TEMPLATES = []  # list[(tpl_gray, tw, th, tpl_bgr)]
DITROI_THRESH = 0.90
_DITROI_ALARM_LAST = 0.0
_DITROI_TG_LAST = 0.0

# 선인인형 템플릿/상태
DOLL_TEMPLATES = []  # list[(tpl_gray, tw, th, tpl_bgr)]
DOLL_THRESH = 0.90
_DOLL_ALARM_LAST = 0.0
_DOLL_TG_LAST = 0.0

# 리치 템플릿/상태
LICH_TEMPLATES = []  # list[(tpl_gray, tw, th, tpl_bgr)]
LICH_THRESH = 0.95
_LICH_ALARM_LAST = 0.0
_LICH_TG_LAST = 0.0

def reload_ign_template():
    """imgs/ign/ign.png 로드해 템플릿 갱신"""
    global IGN_TEMPLATE, IGN_W, IGN_H
    path=os.path.join('imgs','ign','ign.png')
    if os.path.exists(path):
        tpl=cv2.imread(path,cv2.IMREAD_GRAYSCALE)
        if tpl is not None:
            IGN_TEMPLATE=tpl
            IGN_H,IGN_W=tpl.shape
            return True
    IGN_TEMPLATE=None;IGN_W=IGN_H=0
    return False

# 최초 로드
reload_ign_template()

# 루루모 템플릿 로더
def reload_ruru_templates():
    global RURU_TEMPLATES
    tdir = os.path.join('imgs','handle_macro_prevent_mobs')
    names = ['C_2_1.png','C_2_2.png','C_2_3.png','C_2_4.png','C_2_5.png']
    tpls = []
    try:
        if os.path.isdir(tdir):
            for n in names:
                p = os.path.join(tdir, n)
                if not os.path.exists(p):
                    continue
                tpl_bgr = cv2.imread(p, cv2.IMREAD_COLOR)
                if tpl_bgr is None:
                    continue
                tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
                th, tw = tpl_gray.shape
                tpls.append((tpl_gray, tw, th, tpl_bgr))
    except Exception:
        tpls = []
    RURU_TEMPLATES = tpls

# 자동경비 템플릿 로더
def reload_guard_templates():
    global GUARD_TEMPLATES
    tdir = os.path.join('imgs','handle_macro_prevent_mobs')
    names = [f'{i}.png' for i in range(1, 11)]
    tpls = []
    try:
        if os.path.isdir(tdir):
            for n in names:
                p = os.path.join(tdir, n)
                if not os.path.exists(p):
                    continue
                tpl_bgr = cv2.imread(p, cv2.IMREAD_COLOR)
                if tpl_bgr is None:
                    continue
                tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
                th, tw = tpl_gray.shape
                tpls.append((tpl_gray, tw, th, tpl_bgr))
    except Exception:
        tpls = []
    GUARD_TEMPLATES = tpls

# 디트와 로이 템플릿 로더
def reload_ditroi_templates():
    global DITROI_TEMPLATES
    tdir = os.path.join('imgs','handle_macro_prevent_mobs')
    names = [f'{i}.png' for i in range(11, 20)]
    tpls = []
    try:
        if os.path.isdir(tdir):
            for n in names:
                p = os.path.join(tdir, n)
                if not os.path.exists(p):
                    continue
                tpl_bgr = cv2.imread(p, cv2.IMREAD_COLOR)
                if tpl_bgr is None:
                    continue
                tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
                th, tw = tpl_gray.shape
                tpls.append((tpl_gray, tw, th, tpl_bgr))
    except Exception:
        tpls = []
    DITROI_TEMPLATES = tpls

# 선인인형 템플릿 로더
def reload_doll_templates():
    global DOLL_TEMPLATES
    tdir = os.path.join('imgs','handle_macro_prevent_mobs')
    names = [f'{i}.png' for i in range(21, 29)]
    tpls = []
    try:
        if os.path.isdir(tdir):
            for n in names:
                p = os.path.join(tdir, n)
                if not os.path.exists(p):
                    continue
                tpl_bgr = cv2.imread(p, cv2.IMREAD_COLOR)
                if tpl_bgr is None:
                    continue
                tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
                th, tw = tpl_gray.shape
                tpls.append((tpl_gray, tw, th, tpl_bgr))
    except Exception:
        tpls = []
    DOLL_TEMPLATES = tpls

# 리치 템플릿 로더
def reload_lich_templates():
    global LICH_TEMPLATES
    tdir = os.path.join('imgs','handle_macro_prevent_mobs')
    names = [f'{i}.png' for i in range(31, 48)]
    tpls = []
    try:
        if os.path.isdir(tdir):
            for n in names:
                p = os.path.join(tdir, n)
                if not os.path.exists(p):
                    continue
                tpl_bgr = cv2.imread(p, cv2.IMREAD_COLOR)
                if tpl_bgr is None:
                    continue
                tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
                th, tw = tpl_gray.shape
                tpls.append((tpl_gray, tw, th, tpl_bgr))
    except Exception:
        tpls = []
    LICH_TEMPLATES = tpls

# 색상 마스크 유틸: 빨강/노랑/초록 HSV 범위를 엄격히 정의하고 마스크 생성
def _build_color_masks_from_bgr(img_bgr):
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    # 공통 S/V 하한 (채도/명도 부족 픽셀 제외)
    s_ok = (s >= 100)
    v_ok = (v >= 60)
    sv_ok = (s_ok & v_ok)
    # Red: 0-10 or 170-180
    red1 = ((h >= 0) & (h <= 10))
    red2 = ((h >= 170) & (h <= 180))
    red = ((red1 | red2) & sv_ok)
    # Yellow: 20-35
    yellow = ((h >= 20) & (h <= 35) & sv_ok)
    # Green: 35-85
    green = ((h >= 35) & (h <= 85) & sv_ok)
    # bool -> uint8(0/1)로 반환 (연산 편의)
    return {
        'red': red.astype('uint8'),
        'yellow': yellow.astype('uint8'),
        'green': green.astype('uint8'),
    }

def ensure_mon_watch(parent=None):
    _ensure_mon_watch(parent)
    reload_monster_templates()

# OpenCL 사용 설정 (가능 시)
try:
    if USE_OPENCL and cv2.ocl.haveOpenCL():
        cv2.ocl.setUseOpenCL(True)
except Exception:
    pass

def reload_monster_templates():
    """imgs/monster 폴더의 monster*.png 템플릿을 다시 로드"""
    global MONSTER_TEMPLATES
    MONSTER_TEMPLATES = []
    mdir = MON_DIR
    if not os.path.isdir(mdir):
        return
    for name in sorted(os.listdir(mdir)):
        if not name.lower().endswith('.png'):
            continue
        path = os.path.join(mdir,name)
        tpl_gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        tpl_bgr  = cv2.imread(path, cv2.IMREAD_COLOR)
        if tpl_gray is None or tpl_bgr is None:
            continue
        # 템플릿에서 R/Y/G 마스크 미리 생성
        color_masks = _build_color_masks_from_bgr(tpl_bgr)
        MONSTER_TEMPLATES.append((name, tpl_gray, tpl_gray.shape[1], tpl_gray.shape[0], tpl_bgr, color_masks))
    # 스냅샷 업데이트
    _update_mon_snapshot()

def _snapshot_mon_dir():
    try:
        if not os.path.isdir(MON_DIR):
            return ()
        items=[]
        for f in os.listdir(MON_DIR):
            if not f.lower().endswith('.png'):
                continue
            p=os.path.join(MON_DIR,f)
            try:
                st=os.stat(p)
                items.append((f,int(st.st_mtime),int(st.st_size)))
            except Exception:
                continue
        return tuple(sorted(items))
    except Exception:
        return ()

def _update_mon_snapshot():
    global _MON_SNAPSHOT
    _MON_SNAPSHOT=_snapshot_mon_dir()

def _poll_mon_dir():
    global _MON_SNAPSHOT
    snap=_snapshot_mon_dir()
    if snap!=_MON_SNAPSHOT:
        _MON_SNAPSHOT=snap
        reload_monster_templates()

def _ensure_mon_watch(parent=None):
    global _MON_WATCHER, _MON_TIMER
    try:
        os.makedirs(MON_DIR, exist_ok=True)
    except Exception:
        pass
    # 부모 결정: 전달된 parent 우선, 없으면 QApplication.instance()
    try:
        qapp = QApplication.instance()
    except Exception:
        qapp = None
    owner = parent if parent is not None else qapp
    if _MON_WATCHER is None:
        try:
            _MON_WATCHER = QFileSystemWatcher(owner) if owner is not None else QFileSystemWatcher()
            if os.path.isdir(MON_DIR):
                _MON_WATCHER.addPath(MON_DIR)
            def _changed(_):
                reload_monster_templates()
            _MON_WATCHER.directoryChanged.connect(_changed)
            _MON_WATCHER.fileChanged.connect(_changed)
            try:
                if owner is not None:
                    _MON_WATCHER.moveToThread(owner.thread())
            except Exception:
                pass
        except Exception:
            _MON_WATCHER = None
    if _MON_TIMER is None:
        try:
            _MON_TIMER = QTimer(owner) if owner is not None else QTimer()
            _MON_TIMER.setInterval(1000)
            _MON_TIMER.timeout.connect(_poll_mon_dir)
            try:
                if owner is not None:
                    _MON_TIMER.moveToThread(owner.thread())
            except Exception:
                pass
            try:
                from PyQt5.QtCore import QMetaObject as _QMetaObject
                _QMetaObject.invokeMethod(_MON_TIMER, "start", Qt.QueuedConnection)
            except Exception:
                try:
                    _MON_TIMER.start()
                except Exception:
                    pass
        except Exception:
            _MON_TIMER=None

def create_hunting_capture_button(parent_widget, minimap_button):
    """사냥구역 캡처 버튼 생성"""
    hunting_button = QPushButton("사냥구역 캡처", parent_widget)
    hunting_button.setFixedSize(120, 30)
    # 호버 효과 포함 스타일
    hunting_button.setStyleSheet("QPushButton {background:#7d7d7d; color:white; border:none;} QPushButton:hover{background:#9e9e9e;} QPushButton:pressed{background:#5d5d5d;}")
    
    # 미니맵 캡처 버튼 바로 아래에 배치
    hunting_button.move(minimap_button.x(), minimap_button.y() + minimap_button.height() + 5)
    
    hunting_button.clicked.connect(lambda: handle_hunting_capture())
    
    return hunting_button

def handle_hunting_capture():
    """사냥구역 캡처 핸들러"""
    global hunting_region
    
    # 예/아니오 다이얼로그 표시
    reply = QMessageBox.question(
        None, 
        "사냥구역 설정", 
        "기본 영역 을 사용하시겠습니까?\n\n예: 기본 영역 사용\n아니오: 수동 영역 선택",
        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
    )
    
    if reply == QMessageBox.Cancel:
        return
    elif reply == QMessageBox.Yes:
        # 기본 영역 사용
        hunting_region = (6, 124, 1275, 539)
        print(f"✅ 기본 사냥구역 설정 완료: {hunting_region}")
        start_hunting_capture()
    else:
        # 수동 영역 선택: minimap 오버레이 재사용 + 기존 minimap.capture_region 보존/복원
        try:
            old_region = getattr(minimap, 'capture_region', None)
        except Exception:
            old_region = None
        region = minimap.capture_minimap()
        # 미니맵 상태 복원 (오염 방지)
        try:
            minimap.capture_region = old_region
        except Exception:
            pass
        if region:
            hunting_region = region
            print(f"✅ 사용자 정의 사냥구역 설정 완료: {hunting_region}")
            start_hunting_capture()

def capture_hunting_region():
    """사냥구역 캡처 함수"""
    # 오버레이 시작
    region = start_hunting_overlay()
    
    if region:
        return region
    else:
        return None

def start_hunting_capture():
    """사냥구역 캡처 시작 (main에서 설정한 minimap.canvas_widget.hunting_canvas를 사용)"""
    global hunting_region
    if hunting_region and hasattr(minimap, "canvas_widget"):
        # 사냥구역 캔버스는 minimap.canvas_widget.hunting_canvas로 고정
        start_hunting_canvas_capture(hunting_region, minimap.canvas_widget)

def start_hunting_overlay():
    """사냥구역 오버레이 시작"""
    global is_hunting_capturing
    is_hunting_capturing = True
    
    # 오버레이 위젯 생성
    overlay = create_hunting_overlay_widget()
    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    overlay.setFocus()
    
    # 오버레이가 닫힐 때까지 대기
    while overlay.isVisible():
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
        import time
        time.sleep(0.01)
    
    is_hunting_capturing = False
    return hunting_region

def create_hunting_overlay_widget():
    """사냥구역 오버레이 위젯 생성"""
    from PyQt5.QtWidgets import QWidget
    from PyQt5.QtGui import QPainter, QPen, QColor
    
    overlay = QWidget()
    overlay.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    overlay.setAttribute(Qt.WA_TranslucentBackground)
    overlay.setAttribute(Qt.WA_DeleteOnClose, True)
    overlay.setGeometry(0, 0, 1920, 1080)  # 전체 화면
    
    start_pos = None
    end_pos = None
    is_drawing = False
    
    def paint_event(event):
        painter = QPainter(overlay)
        painter.setPen(QPen(QColor(255, 0, 0), 2))
        
        if start_pos and end_pos:
            x = min(start_pos.x(), end_pos.x())
            y = min(start_pos.y(), end_pos.y())
            w = abs(end_pos.x() - start_pos.x())
            h = abs(end_pos.y() - start_pos.y())
            painter.drawRect(x, y, w, h)
    
    def mouse_press(event):
        nonlocal start_pos, is_drawing
        start_pos = event.pos()
        is_drawing = True
    
    def mouse_move(event):
        nonlocal end_pos
        if is_drawing:
            end_pos = event.pos()
            overlay.update()
    
    def mouse_release(event):
        nonlocal end_pos, is_drawing
        if is_drawing:
            end_pos = event.pos()
            is_drawing = False
            
            if start_pos and end_pos:
                x = min(start_pos.x(), end_pos.x())
                y = min(start_pos.y(), end_pos.y())
                w = abs(end_pos.x() - start_pos.x())
                h = abs(end_pos.y() - start_pos.y())
                
                global hunting_region
                hunting_region = (x, y, w, h)
                overlay.close()
    
    overlay.paintEvent = paint_event
    overlay.mousePressEvent = mouse_press
    overlay.mouseMoveEvent = mouse_move
    overlay.mouseReleaseEvent = mouse_release
    
    return overlay

def get_hunting_region():
    """사냥구역 반환"""
    return hunting_region

def start_hunting_canvas_capture(region, canvas_widget):
    """사냥구역 캔버스 캡처 시작 (타이머 중복 방지, 텍스처 초기화)"""
    global hunting_region
    hunting_region = region
    
    # 사냥구역 캔버스 객체 가져오기
    if not hasattr(canvas_widget, 'hunting_canvas'):
        return
    hunting_canvas = canvas_widget.hunting_canvas
    
    # 기존 타이머가 있으면 정지 및 제거
    if hasattr(hunting_canvas, 'capture_timer') and hunting_canvas.capture_timer:
        hunting_canvas.capture_timer.stop()
        hunting_canvas.capture_timer.deleteLater()
        hunting_canvas.capture_timer = None
    
    # 기존 텍스처 제거 (메모리 누수 방지)
    if hasattr(hunting_canvas, 'texture_id'):
        try:
            glDeleteTextures(int(hunting_canvas.texture_id))
        except Exception:
            pass
        delattr(hunting_canvas, 'texture_id')
    
    # 새 캡처 타이머 시작
    # 스케일 저장
    hunting_canvas.scale_x = 300 / region[2]
    hunting_canvas.scale_y = 150 / region[3]
    start_hunting_capture_timer(region, hunting_canvas)

def start_hunting_capture_timer(region, hunting_canvas):
    """사냥구역 캡처 타이머 시작"""
    from PyQt5.QtCore import QTimer, Qt
    import pyautogui
    import cv2
    import numpy as np
    
    # 기존 타이머가 있으면 정지
    if hasattr(hunting_canvas, 'capture_timer') and hunting_canvas.capture_timer:
        hunting_canvas.capture_timer.stop()
        hunting_canvas.capture_timer.deleteLater()
    
    # 새로운 타이머 생성
    hunting_canvas.capture_timer = QTimer(hunting_canvas)
    hunting_canvas.capture_timer.setTimerType(Qt.PreciseTimer)
    
    def on_hunting_timeout():
        try:
            screenshot = pyautogui.screenshot(region=region)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            update_hunting_canvas(frame, hunting_canvas)
        except Exception as e:
            pass
    
    hunting_canvas.capture_timer.timeout.connect(on_hunting_timeout)
    hunting_canvas.capture_timer.setInterval(2)
    try:
        from PyQt5.QtCore import QMetaObject as _QMetaObject
        _QMetaObject.invokeMethod(hunting_canvas.capture_timer, "start", Qt.QueuedConnection)
    except Exception:
        try:
            hunting_canvas.capture_timer.start()
        except Exception:
            pass

def reset_hunting(canvas_widget):
    """사냥구역 캡처 및 상태 초기화"""
    global hunting_region
    hunting_region = None
    if hasattr(canvas_widget, 'hunting_canvas'):
        hc = canvas_widget.hunting_canvas
        # 타이머 정리
        try:
            if hasattr(hc, 'capture_timer') and hc.capture_timer:
                try:
                    hc.capture_timer.stop()
                except Exception:
                    pass
                try:
                    hc.capture_timer.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            hc.capture_timer = None
        except Exception:
            pass
        # 텍스처 정리
        try:
            if hasattr(hc, 'texture_id'):
                try:
                    glDeleteTextures(int(hc.texture_id))
                except Exception:
                    pass
                try:
                    delattr(hc, 'texture_id')
                except Exception:
                    pass
        except Exception:
            pass
        # 표시 갱신
        try:
            hc.update()
        except Exception:
            pass

def update_hunting_canvas(frame, hunting_canvas):
    """사냥구역 캔버스 업데이트"""
    try:
        global CURRENT_IGN, MON_POS
        # OpenGL 캔버스에 텍스처로 그리기
        if hasattr(hunting_canvas, 'paintGL'):
            # OpenGL 컨텍스트에서 텍스처 업데이트
            hunting_canvas.makeCurrent()
            
            # 텍스처 생성 및 업데이트
            if not hasattr(hunting_canvas, 'texture_id'):
                hunting_canvas.texture_id = glGenTextures(1)
            
            # 원본 그레이스케일
            gray_orig=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
            # BGR을 RGB로 변환
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 캔버스 크기에 맞게 리사이즈 (비율 유지)
            canvas_width, canvas_height = 300, 150
            
            # 캔버스 표시용 프레임 준비
            frame_resized = cv2.resize(frame_rgb, (canvas_width, canvas_height), interpolation=cv2.INTER_LINEAR)
            # 트레이닝캔버스에서는 보라색 차단 영역을 표시하지 않음

            # ----- 루루모(매크로방지) 템플릿 매칭: 점프/몬스터와 동일 방식으로 원형 테두리 표시 -----
            try:
                import sys as _sys
                _m = _sys.modules.get('__main__')
                bf = getattr(_m, 'buffs_frame', None)
                mh = getattr(bf, 'macro_handler_frame', None) if bf else None
                enabled = bool(mh and hasattr(mh,'enable_chk') and mh.enable_chk.isChecked())
                guard_enabled = bool(mh and hasattr(mh,'guard_chk') and mh.guard_chk.isChecked())
                ditroi_enabled = bool(mh and hasattr(mh,'ditroi_chk') and mh.ditroi_chk.isChecked())
                doll_enabled = bool(mh and hasattr(mh,'doll_chk') and mh.doll_chk.isChecked())
                lich_enabled = bool(mh and hasattr(mh,'lich_chk') and mh.lich_chk.isChecked())
                if enabled:
                    if not RURU_TEMPLATES:
                        reload_ruru_templates()
                    if RURU_TEMPLATES:
                        # 원본 그레이스케일에서 매칭 후, 캔버스로 스케일하여 동그라미 표시
                        res_sx = canvas_width / max(1, frame.shape[1])
                        res_sy = canvas_height / max(1, frame.shape[0])
                        gray_orig = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        drawn = False
                        for (tpl, tw, th, tpl_col) in RURU_TEMPLATES:
                            try:
                                res = cv2.matchTemplate(gray_orig, tpl, cv2.TM_CCOEFF_NORMED)
                                yx = np.where(res >= RURU_THRESH)
                                coords = list(zip(yx[0].tolist(), yx[1].tolist()))
                                if coords:
                                    coords.sort(key=lambda rc: res[rc[0], rc[1]], reverse=True)
                                    coords = coords[:10]
                                for (y, x) in coords:
                                    try:
                                        roi = frame[y:y+th, x:x+tw]
                                        if roi.shape[0] != th or roi.shape[1] != tw:
                                            continue
                                        diff = np.abs(roi.astype(np.int16) - tpl_col.astype(np.int16))
                                        mask = (diff[:,:,0] <= 32) & (diff[:,:,1] <= 32) & (diff[:,:,2] <= 32)
                                        color_ratio = mask.mean()
                                        if color_ratio < 0.20:
                                            continue
                                    except Exception:
                                        continue
                                    tl_scaled = (int(x*res_sx), int(y*res_sy))
                                    w_scaled = int(tw*res_sx); h_scaled = int(th*res_sy)
                                    cv2.rectangle(
                                        frame_resized,
                                        (tl_scaled[0], tl_scaled[1]),
                                        (tl_scaled[0] + w_scaled, tl_scaled[1] + h_scaled),
                                        (255,0,0), 2
                                    )
                                    drawn = True
                            except Exception:
                                pass
                        if drawn:
                            try:
                                import sys as __sys
                                _m2 = __sys.modules.get('__main__')
                                _btn = getattr(_m2, 'stop_button_instance', None)
                                if _btn:
                                    _btn.click()
                            except Exception:
                                pass
                            global _RURU_ALARM_LAST, _RURU_TG_LAST
                            nowt = time.time()
                            if nowt - _RURU_ALARM_LAST >= 1.5:
                                try:
                                    if not pygame.mixer.get_init():
                                        pygame.mixer.init()
                                    mp3p = os.path.join('imgs','alarm','alarm.mp3')
                                    if os.path.exists(mp3p):
                                        snd = pygame.mixer.Sound(mp3p)
                                        snd.play()
                                except Exception:
                                    pass
                                _RURU_ALARM_LAST = nowt
                            try:
                                if nowt - _RURU_TG_LAST >= 5.0:
                                    import telegram as _tg
                                    try:
                                        if hasattr(_tg, 'is_configured'):
                                            if _tg.is_configured():
                                                _tg.send_message_async('매크로방지 몹 감지!')
                                        else:
                                            _tg.send_message_async('매크로방지 몹 감지!')
                                    except Exception:
                                        pass
                                    _RURU_TG_LAST = nowt
                            except Exception:
                                pass
                # ----- 자동경비시스템 -----
                if guard_enabled:
                    if not GUARD_TEMPLATES:
                        reload_guard_templates()
                    if GUARD_TEMPLATES:
                        res_sx = canvas_width / max(1, frame.shape[1])
                        res_sy = canvas_height / max(1, frame.shape[0])
                        gray_orig = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        g_drawn = False
                        for (tpl, tw, th, tpl_col) in GUARD_TEMPLATES:
                            try:
                                res = cv2.matchTemplate(gray_orig, tpl, cv2.TM_CCOEFF_NORMED)
                                yx = np.where(res >= GUARD_THRESH)
                                coords = list(zip(yx[0].tolist(), yx[1].tolist()))
                                if coords:
                                    coords.sort(key=lambda rc: res[rc[0], rc[1]], reverse=True)
                                    coords = coords[:10]
                                for (y, x) in coords:
                                    try:
                                        roi = frame[y:y+th, x:x+tw]
                                        if roi.shape[0] != th or roi.shape[1] != tw:
                                            continue
                                        diff = np.abs(roi.astype(np.int16) - tpl_col.astype(np.int16))
                                        mask = (diff[:,:,0] <= 32) & (diff[:,:,1] <= 32) & (diff[:,:,2] <= 32)
                                        color_ratio = mask.mean()
                                        if color_ratio < 0.20:
                                            continue
                                    except Exception:
                                        continue
                                    tl_scaled = (int(x*res_sx), int(y*res_sy))
                                    w_scaled = int(tw*res_sx); h_scaled = int(th*res_sy)
                                    cv2.rectangle(
                                        frame_resized,
                                        (tl_scaled[0], tl_scaled[1]),
                                        (tl_scaled[0] + w_scaled, tl_scaled[1] + h_scaled),
                                        (255,0,0), 2
                                    )
                                    g_drawn = True
                            except Exception:
                                pass
                        if g_drawn:
                            try:
                                import sys as __sys
                                _m2 = __sys.modules.get('__main__')
                                _btn = getattr(_m2, 'stop_button_instance', None)
                                if _btn:
                                    _btn.click()
                            except Exception:
                                pass
                            global _GUARD_ALARM_LAST, _GUARD_TG_LAST
                            nowt = time.time()
                            if nowt - _GUARD_ALARM_LAST >= 1.5:
                                try:
                                    if not pygame.mixer.get_init():
                                        pygame.mixer.init()
                                    mp3p = os.path.join('imgs','alarm','alarm.mp3')
                                    if os.path.exists(mp3p):
                                        snd = pygame.mixer.Sound(mp3p)
                                        snd.play()
                                except Exception:
                                    pass
                                _GUARD_ALARM_LAST = nowt
                            try:
                                if nowt - _GUARD_TG_LAST >= 5.0:
                                    import telegram as _tg
                                    try:
                                        if hasattr(_tg, 'is_configured'):
                                            if _tg.is_configured():
                                                _tg.send_message_async('매크로방지몹 감지!')
                                        else:
                                            _tg.send_message_async('매크로방지몹 감지!')
                                    except Exception:
                                        pass
                                    _GUARD_TG_LAST = nowt
                            except Exception:
                                pass
                # ----- 디트와 로이 -----
                if ditroi_enabled:
                    if not DITROI_TEMPLATES:
                        reload_ditroi_templates()
                    if DITROI_TEMPLATES:
                        res_sx = canvas_width / max(1, frame.shape[1])
                        res_sy = canvas_height / max(1, frame.shape[0])
                        gray_orig = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        d_drawn = False
                        for (tpl, tw, th, tpl_col) in DITROI_TEMPLATES:
                            try:
                                res = cv2.matchTemplate(gray_orig, tpl, cv2.TM_CCOEFF_NORMED)
                                yx = np.where(res >= DITROI_THRESH)
                                coords = list(zip(yx[0].tolist(), yx[1].tolist()))
                                if coords:
                                    coords.sort(key=lambda rc: res[rc[0], rc[1]], reverse=True)
                                    coords = coords[:10]
                                for (y, x) in coords:
                                    try:
                                        roi = frame[y:y+th, x:x+tw]
                                        if roi.shape[0] != th or roi.shape[1] != tw:
                                            continue
                                        diff = np.abs(roi.astype(np.int16) - tpl_col.astype(np.int16))
                                        mask = (diff[:,:,0] <= 32) & (diff[:,:,1] <= 32) & (diff[:,:,2] <= 32)
                                        color_ratio = mask.mean()
                                        if color_ratio < 0.20:
                                            continue
                                    except Exception:
                                        continue
                                    tl_scaled = (int(x*res_sx), int(y*res_sy))
                                    w_scaled = int(tw*res_sx); h_scaled = int(th*res_sy)
                                    cv2.rectangle(
                                        frame_resized,
                                        (tl_scaled[0], tl_scaled[1]),
                                        (tl_scaled[0] + w_scaled, tl_scaled[1] + h_scaled),
                                        (255,0,0), 2
                                    )
                                    d_drawn = True
                            except Exception:
                                pass
                        if d_drawn:
                            try:
                                import sys as __sys
                                _m2 = __sys.modules.get('__main__')
                                _btn = getattr(_m2, 'stop_button_instance', None)
                                if _btn:
                                    _btn.click()
                            except Exception:
                                pass
                            global _DITROI_ALARM_LAST, _DITROI_TG_LAST
                            nowt = time.time()
                            if nowt - _DITROI_ALARM_LAST >= 1.5:
                                try:
                                    if not pygame.mixer.get_init():
                                        pygame.mixer.init()
                                    mp3p = os.path.join('imgs','alarm','alarm.mp3')
                                    if os.path.exists(mp3p):
                                        snd = pygame.mixer.Sound(mp3p)
                                        snd.play()
                                except Exception:
                                    pass
                                _DITROI_ALARM_LAST = nowt
                            try:
                                if nowt - _DITROI_TG_LAST >= 5.0:
                                    import telegram as _tg
                                    try:
                                        if hasattr(_tg, 'is_configured'):
                                            if _tg.is_configured():
                                                _tg.send_message_async('매크로방지몹 감지!')
                                        else:
                                            _tg.send_message_async('매크로방지몹 감지!')
                                    except Exception:
                                        pass
                                    _DITROI_TG_LAST = nowt
                            except Exception:
                                pass
                # ----- 선인인형 -----
                if doll_enabled:
                    if not DOLL_TEMPLATES:
                        reload_doll_templates()
                    if DOLL_TEMPLATES:
                        res_sx = canvas_width / max(1, frame.shape[1])
                        res_sy = canvas_height / max(1, frame.shape[0])
                        gray_orig = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        drawn3 = False
                        for (tpl, tw, th, tpl_col) in DOLL_TEMPLATES:
                            try:
                                res = cv2.matchTemplate(gray_orig, tpl, cv2.TM_CCOEFF_NORMED)
                                yx = np.where(res >= DOLL_THRESH)
                                coords = list(zip(yx[0].tolist(), yx[1].tolist()))
                                if coords:
                                    coords.sort(key=lambda rc: res[rc[0], rc[1]], reverse=True)
                                    coords = coords[:10]
                                for (y, x) in coords:
                                    try:
                                        roi = frame[y:y+th, x:x+tw]
                                        if roi.shape[0] != th or roi.shape[1] != tw:
                                            continue
                                        diff = np.abs(roi.astype(np.int16) - tpl_col.astype(np.int16))
                                        mask = (diff[:,:,0] <= 32) & (diff[:,:,1] <= 32) & (diff[:,:,2] <= 32)
                                        color_ratio = mask.mean()
                                        if color_ratio < 0.20:
                                            continue
                                    except Exception:
                                        continue
                                    tl_scaled = (int(x*res_sx), int(y*res_sy))
                                    w_scaled = int(tw*res_sx); h_scaled = int(th*res_sy)
                                    cv2.rectangle(
                                        frame_resized,
                                        (tl_scaled[0], tl_scaled[1]),
                                        (tl_scaled[0] + w_scaled, tl_scaled[1] + h_scaled),
                                        (255,0,0), 2
                                    )
                                    drawn3 = True
                            except Exception:
                                pass
                        if drawn3:
                            try:
                                import sys as __sys
                                _m2 = __sys.modules.get('__main__')
                                _btn = getattr(_m2, 'stop_button_instance', None)
                                if _btn:
                                    _btn.click()
                            except Exception:
                                pass
                            global _DOLL_ALARM_LAST, _DOLL_TG_LAST
                            nowt = time.time()
                            if nowt - _DOLL_ALARM_LAST >= 1.5:
                                try:
                                    if not pygame.mixer.get_init():
                                        pygame.mixer.init()
                                    mp3p = os.path.join('imgs','alarm','alarm.mp3')
                                    if os.path.exists(mp3p):
                                        snd = pygame.mixer.Sound(mp3p)
                                        snd.play()
                                except Exception:
                                    pass
                                _DOLL_ALARM_LAST = nowt
                            try:
                                if nowt - _DOLL_TG_LAST >= 5.0:
                                    import telegram as _tg
                                    try:
                                        if hasattr(_tg, 'is_configured'):
                                            if _tg.is_configured():
                                                _tg.send_message_async('매크로방지몹 감지!')
                                        else:
                                            _tg.send_message_async('매크로방지몹 감지!')
                                    except Exception:
                                        pass
                                    _DOLL_TG_LAST = nowt
                            except Exception:
                                pass
                # ----- 리치 -----
                if lich_enabled:
                    if not LICH_TEMPLATES:
                        reload_lich_templates()
                    if LICH_TEMPLATES:
                        res_sx = canvas_width / max(1, frame.shape[1])
                        res_sy = canvas_height / max(1, frame.shape[0])
                        gray_orig = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        drawn4 = False
                        for (tpl, tw, th, tpl_col) in LICH_TEMPLATES:
                            try:
                                res = cv2.matchTemplate(gray_orig, tpl, cv2.TM_CCOEFF_NORMED)
                                yx = np.where(res >= LICH_THRESH)
                                coords = list(zip(yx[0].tolist(), yx[1].tolist()))
                                if coords:
                                    coords.sort(key=lambda rc: res[rc[0], rc[1]], reverse=True)
                                    coords = coords[:10]
                                for (y, x) in coords:
                                    try:
                                        roi = frame[y:y+th, x:x+tw]
                                        if roi.shape[0] != th or roi.shape[1] != tw:
                                            continue
                                        diff = np.abs(roi.astype(np.int16) - tpl_col.astype(np.int16))
                                        mask = (diff[:,:,0] <= 32) & (diff[:,:,1] <= 32) & (diff[:,:,2] <= 32)
                                        color_ratio = mask.mean()
                                        if color_ratio < 0.20:
                                            continue
                                    except Exception:
                                        continue
                                    tl_scaled = (int(x*res_sx), int(y*res_sy))
                                    w_scaled = int(tw*res_sx); h_scaled = int(th*res_sy)
                                    cv2.rectangle(
                                        frame_resized,
                                        (tl_scaled[0], tl_scaled[1]),
                                        (tl_scaled[0] + w_scaled, tl_scaled[1] + h_scaled),
                                        (255,0,0), 2
                                    )
                                    drawn4 = True
                            except Exception:
                                pass
                        if drawn4:
                            try:
                                import sys as __sys
                                _m2 = __sys.modules.get('__main__')
                                _btn = getattr(_m2, 'stop_button_instance', None)
                                if _btn:
                                    _btn.click()
                            except Exception:
                                pass
                            global _LICH_ALARM_LAST, _LICH_TG_LAST
                            nowt = time.time()
                            if nowt - _LICH_ALARM_LAST >= 1.5:
                                try:
                                    if not pygame.mixer.get_init():
                                        pygame.mixer.init()
                                    mp3p = os.path.join('imgs','alarm','alarm.mp3')
                                    if os.path.exists(mp3p):
                                        snd = pygame.mixer.Sound(mp3p)
                                        snd.play()
                                except Exception:
                                    pass
                                _LICH_ALARM_LAST = nowt
                            try:
                                if nowt - _LICH_TG_LAST >= 5.0:
                                    import telegram as _tg
                                    try:
                                        if hasattr(_tg, 'is_configured'):
                                            if _tg.is_configured():
                                                _tg.send_message_async('매크로방지몹 감지!')
                                        else:
                                            _tg.send_message_async('매크로방지몹 감지!')
                                    except Exception:
                                        pass
                                    _LICH_TG_LAST = nowt
                            except Exception:
                                pass
            except Exception:
                pass

            # ---- 점프다운 저장 좌표 표시 ----
            try:
                pass
            except Exception:
                pass

            # 캔버스 스케일 확보
            sx=getattr(hunting_canvas,'scale_x',300/max(1,frame.shape[1]))
            sy=getattr(hunting_canvas,'scale_y',150/max(1,frame.shape[0]))

            # IGN 탐지 (GPU OpenCL 활성 가능)
            found_ign = False
            if IGN_TEMPLATE is not None:
                try:
                    # 템플릿 매칭은 원본 해상도로 수행
                    # sx, sy 는 상단에서 확보됨
                    tw,th=IGN_W,IGN_H
                    tpl_use=IGN_TEMPLATE
                    res=None
                    # OpenCL(Umat) 우선, 실패 시 CPU
                    res=None
                    if USE_OPENCL and cv2.ocl.haveOpenCL():
                        try:
                            gray_u=cv2.UMat(gray_orig)
                            tpl_u=cv2.UMat(tpl_use)
                            res_u=cv2.matchTemplate(gray_u,tpl_u,cv2.TM_CCOEFF_NORMED)
                            res=res_u.get()
                        except Exception:
                            res=None
                    if res is None:
                        res=cv2.matchTemplate(gray_orig,tpl_use,cv2.TM_CCOEFF_NORMED)
                    min_val,max_val,min_loc,max_loc=cv2.minMaxLoc(res)
                    if max_val>=THRESH:
                        top_left=max_loc
                        # 캔버스 좌표로 변환 (중심 좌표 기준)
                        center_x = top_left[0] + tw/2.0
                        center_y = top_left[1] + th/2.0
                        tl_scaled=(int(top_left[0]*sx),int(top_left[1]*sy))
                        w_scaled=int(tw*sx);h_scaled=int(th*sy)
                        # 정확도가 가장 높은 IGN만 빨간색 테두리로 그리기
                        cv2.rectangle(frame_resized,tl_scaled,(tl_scaled[0]+w_scaled,tl_scaled[1]+h_scaled),(0,0,255),2)
                        
                        # IGN 좌표 레이블 업데이트 (캔버스 좌표로 변환)
                        # 레이블 직접 업데이트
                        if hasattr(hunting_canvas, 'ign_coord_label'):
                            canvas_x = int(center_x * sx)
                            canvas_y = int(center_y * sy)
                            hunting_canvas.ign_coord_label.setText(f"IGN 좌표: {canvas_x},{canvas_y}")
                        found_ign = True
                        global CURRENT_IGN
                        CURRENT_IGN = (center_x, center_y)
                except Exception:
                    pass

            # IGN 좌표 레이블 초기화 (탐지 실패 시)
            if not found_ign:
                try:
                    pass  # IGN 미탐지 시 마지막 좌표 유지
                except Exception:
                    pass

            # 몬스터 템플릿 매칭 (여러개, 최대 200개 표기)
            try:
                matches = []
                if MONSTER_TEMPLATES:
                    for (_, tpl, tw2, th2, tpl_col, color_masks) in MONSTER_TEMPLATES:
                        res = None
                        # OpenCL(Umat) 우선, 실패 시 CPU
                        if USE_OPENCL and cv2.ocl.haveOpenCL():
                            try:
                                gray_u=cv2.UMat(gray_orig)
                                tpl_u=cv2.UMat(tpl)
                                res_u=cv2.matchTemplate(gray_u, tpl_u, cv2.TM_CCOEFF_NORMED)
                                res=res_u.get()
                            except Exception:
                                res=None
                        if res is None:
                            res = cv2.matchTemplate(gray_orig, tpl, cv2.TM_CCOEFF_NORMED)
                        yx = np.where(res >= (MON_THRESH/100.0))
                        # 점수 내림차순으로 상위 10개만 선택
                        coords = list(zip(yx[0].tolist(), yx[1].tolist()))
                        if coords:
                            coords.sort(key=lambda rc: res[rc[0], rc[1]], reverse=True)
                            coords = coords[:10]
                        for (y,x) in coords:
                            # 강화된 색상 일치: 템플릿의 빨/노/초 마스크가 ROI 내에서도 충분 비율로 존재해야 함
                            try:
                                roi = frame[y:y+th2, x:x+tw2]  # BGR
                                if roi.shape[0] != th2 or roi.shape[1] != tw2:
                                    continue
                                roi_masks = _build_color_masks_from_bgr(roi)
                                # 템플릿 마스크 픽셀 수 (각 색이 실제 템플릿에 존재해야 비교 의미 있음)
                                tol_pix = 12  # 최소 픽셀 수 기준
                                ok = True
                                for color in ('red','yellow','green'):
                                    tpl_mask = color_masks[color]
                                    tpl_count = int(tpl_mask.sum())
                                    if tpl_count < tol_pix:
                                        # 템플릿에 해당 색이 충분치 않으면 이 색은 스킵(요구하지 않음)
                                        continue
                                    roi_mask = roi_masks[color]
                                    # 템플릿의 해당 색이 있는 위치가 ROI에서도 동일 색으로 충분히 존재해야 함
                                    # 교집합 비율(템플릿 색 픽셀 중 ROI에서도 같은 색 비율)
                                    inter = int((tpl_mask & roi_mask).sum())
                                    ratio = inter / max(1, tpl_count)
                                    if ratio < 0.85:  # 매우 엄격: 85% 이상 동일 색
                                        ok = False
                                        break
                                if not ok:
                                    continue
                            except Exception:
                                continue
                            matches.append((x, y, tw2, th2, res[y,x]))
                # 몬스터 중심 좌표 리스트 저장
                MON_POS = [(mx+tw2/2.0, my+th2/2.0) for (mx,my,tw2,th2,_) in matches] if matches else []

                # 점수 기준 상위 200개 한정
                if matches:
                    matches.sort(key=lambda t: t[4], reverse=True)
                    for (mx,my,tw2,th2,score) in matches[:200]:
                        tl_scaled=(int(mx*sx),int(my*sy))
                        w_scaled=int(tw2*sx); h_scaled=int(th2*sy)
                        # 원형 테두리로 강조
                        center=(tl_scaled[0]+w_scaled//2, tl_scaled[1]+h_scaled//2)
                        radius=max(4,int(min(w_scaled,h_scaled)/2))
                        cv2.circle(frame_resized, center, radius, (0,0,255), 2)
                # IGN과 가장 가까운 몬스터 찾기 및 표시
                if matches and 'center_x' in locals():
                    ign_cx = int(center_x * sx); ign_cy = int(center_y * sy)
                    best = None; best_d = 1e12
                    for (mx,my,tw2,th2,score) in matches:
                        cx = int((mx + tw2/2.0) * sx)
                        cy = int((my + th2/2.0) * sy)
                        d = (cx-ign_cx)*(cx-ign_cx) + (cy-ign_cy)*(cy-ign_cy)
                        if d < best_d:
                            best_d = d; best = (cx, cy)
                    if best:
                        # 노란색 선 그리기
                        cv2.line(frame_resized, (ign_cx, ign_cy), (best[0], best[1]), (0,255,255), 2)
                        # 레이블 업데이트
                        if hasattr(hunting_canvas, 'nearest_label'):
                            hunting_canvas.nearest_label.setText(f"가장 가까운 몬스터: {best[0]},{best[1]}")
                            try:
                                # 사냥 캔버스 오른쪽 끝까지 폭 확장
                                right_edge = hunting_canvas.x() + 300
                                left_x = hunting_canvas.nearest_label.x()
                                hunting_canvas.nearest_label.setFixedWidth(max(160, right_edge - left_x - 6))
                                # 공격 설정 프레임도 동일 오른쪽 끝에 맞춰 폭 확장
                                import sys
                                _main = sys.modules.get('__main__')
                                atk_frame = getattr(_main, 'attack_key_frame', None)
                                if atk_frame is not None:
                                    new_w = max(140, right_edge - atk_frame.x() - 6)
                                    atk_frame.setFixedWidth(new_w)
                            except Exception:
                                pass
            except Exception:
                pass

            # ---- 공격 범위 박스 표시 ----
            try:
                import attack_range as _ar, sys
                _main_mod = sys.modules.get('__main__')
                atk_panel = getattr(_main_mod, 'attack_range_frame', None)
                rng = _ar.get_ranges(atk_panel)
                if rng and ('center_x' in locals() or CURRENT_IGN is not None):
                    if 'center_x' in locals():
                        base_x, base_y = center_x, center_y
                    else:
                        base_x, base_y = CURRENT_IGN
                    dy_min, dy_max, dx_lmin, dx_lmax, dx_rmin, dx_rmax, _ = rng if len(rng) == 7 else (*rng,0)
                    # 반대몹 감지 창문 표시 (노란색)
                    try:
                        import attack_range as _ar2, start_stop as _ss
                        rng2 = _ar2.get_ranges(atk_panel)
                        if rng2 and len(rng2)>=7:
                            dy_min2, dy_max2, _, _, _, _, opp = rng2
                            move_dir = getattr(_ss, 'current_key', None)
                            if move_dir in ('left','right') and opp:
                                # IGN 기준 x 창문 계산
                                if move_dir == 'right':
                                    x1 = base_x - opp; x2 = base_x
                                else:
                                    x1 = base_x; x2 = base_x + opp
                                y1 = base_y + dy_min2; y2 = base_y + dy_max2
                                # ordering 보장
                                if x1 > x2: x1, x2 = x2, x1
                                if y1 > y2: y1, y2 = y2, y1
                                tl2 = (int(x1 * sx), int(y1 * sy))
                                br2 = (int(x2 * sx), int(y2 * sy))
                                cv2.rectangle(frame_resized, tl2, br2, (0,255,255), 1)
                    except Exception:
                        pass
                    # 박스 좌표 (원본 기준)
                    # 왼쪽 범위: 가장 작은 오프셋(더 음수) 사용
                    x_left = base_x + min(dx_lmin, dx_lmax)
                    # 오른쪽 범위: 가장 큰 양수 사용
                    x_right = base_x + max(dx_rmin, dx_rmax)
                    y_up = base_y + dy_min
                    y_down = base_y + dy_max
                    # 캔버스 스케일
                    # ensure ordering
                    if x_left > x_right:
                        x_left, x_right = x_right, x_left
                    if y_up > y_down:
                        y_up, y_down = y_down, y_up
                    tl = (int(x_left * sx), int(y_up * sy))
                    br = (int(x_right * sx), int(y_down * sy))
                    color = (255,0,0)  # 빨간 테두리
                    thickness = 1
                    cv2.rectangle(frame_resized, tl, br, color, thickness)
                    # 상/하/좌/우 안내선 (십자) 추가
                    cv2.line(frame_resized,(int(base_x*sx)-3,int(base_y*sy)),(int(base_x*sx)+3,int(base_y*sy)),color,1)
                    cv2.line(frame_resized,(int(base_x*sx),int(base_y*sy)-3),(int(base_x*sx),int(base_y*sy)+3),color,1)
            except Exception:
                pass

            # 회색 테두리 그리기
            cv2.rectangle(frame_resized,(0,0),(canvas_width-1,canvas_height-1),(128,128,128),1)
            
            # OpenGL 텍스처 업데이트
            glBindTexture(GL_TEXTURE_2D, hunting_canvas.texture_id)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, canvas_width, canvas_height, 0, GL_RGB, GL_UNSIGNED_BYTE, frame_resized)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            
            hunting_canvas.update()
            
    except Exception as e:
        pass

@njit(cache=True)
def _find_ign_coord(frame_gray, template, threshold):
    """numba 가속 IGN 좌표 탐지"""
    if template is None:
        return -1, -1
    h, w = template.shape
    fh, fw = frame_gray.shape
    best_x = best_y = -1
    best_val = threshold
    
    for y in range(fh - h + 1):
        for x in range(fw - w + 1):
            # 간단한 템플릿 매칭
            match_val = 0.0
            for ty in range(h):
                for tx in range(w):
                    diff = abs(int(frame_gray[y+ty, x+tx]) - int(template[ty, tx]))
                    match_val += 1.0 - (diff / 255.0)
            match_val /= (h * w)
            
            if match_val > best_val:
                best_val = match_val
                best_x = x + w // 2
                best_y = y + h // 2
    
    return best_x, best_y

def stop_mon_watch():
    """몬스터 폴더 감시/타이머 정지 및 정리"""
    global _MON_TIMER, _MON_WATCHER
    try:
        if _MON_TIMER is not None:
            try:
                _MON_TIMER.stop()
            except Exception:
                pass
            try:
                _MON_TIMER.deleteLater()
            except Exception:
                pass
            _MON_TIMER = None
    except Exception:
        pass
    try:
        if _MON_WATCHER is not None:
            try:
                # disconnect는 안전하게 skip
                pass
            except Exception:
                pass
            try:
                _MON_WATCHER.deleteLater()
            except Exception:
                pass
            _MON_WATCHER = None
    except Exception:
        pass
