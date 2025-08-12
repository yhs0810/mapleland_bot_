import pyautogui
import time
from datetime import datetime
import os
import pygame
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QImage
from OpenGL.GL import *
import threading
from numba import njit, int32
import current_f
import ladder
import jump_down

# 전역 변수
capture_region = None
is_capturing = False
capture_thread = None
capture_timer = None  # QTimer 기반 캡처 타이머

# 마지막으로 탐지된 원형 위치 저장
last_bbox = None
current_y = None
current_x = None

# 플레이어 알람(시작 시 고정) 및 알림 쿨타임/사운드 캐시
PLAYER_ALARM_ENABLED = False
_ALARM_LAST_T = 0.0
_ALARM_INIT = False
_ALARM_SOUND = None
# 텔레그램 전송 쿨타임(플레이어 알람 전용)
_TG_PLAYER_LAST = 0.0

# 빨간점 탐지 차단 영역(미니맵 캔버스 좌표계 기준: 300x150)
RED_BLOCKS = []  # list[(x, y, w, h)]

# ==========================================
# 템플릿 이미지에서 중앙 색상 추출 (노란색)
# ==========================================
template_path = os.path.join('imgs', 'Character', 'p.png')
if os.path.exists(template_path):
    template_img = cv2.imread(template_path)
    th, tw, _ = template_img.shape
    center_bgr = template_img[th // 2, tw // 2]
    center_hsv = cv2.cvtColor(np.uint8([[center_bgr]]), cv2.COLOR_BGR2HSV)[0][0]
    # 허용 오차 범위 설정
    h_tol = 15
    s_tol = 60
    v_tol = 60
    # uint8 오버플로우 방지: 정수형으로 변환 후 계산
    _hsv_i = np.array(center_hsv, dtype=np.int16)
    lower_hsv = np.array([
        max(0, int(_hsv_i[0]) - h_tol),
        max(0, int(_hsv_i[1]) - s_tol),
        max(0, int(_hsv_i[2]) - v_tol)
    ], dtype=np.uint8)
    upper_hsv = np.array([
        min(179, int(_hsv_i[0]) + h_tol),
        min(255, int(_hsv_i[1]) + s_tol),
        min(255, int(_hsv_i[2]) + v_tol)
    ], dtype=np.uint8)
else:
    # 기본 노란색 HSV 범위 (fallback)
    lower_hsv = np.array([20, 100, 100])
    upper_hsv = np.array([40, 255, 255])

# ==========================================
# puto.png 중앙 색상 추출 (플레이어 알람용, 빨간 원형)
# ==========================================
player_template_path = os.path.join('imgs', 'Character', 'puto.png')
if os.path.exists(player_template_path):
    _pimg = cv2.imread(player_template_path)
    if _pimg is not None and _pimg.size > 0:
        ph, pw, _ = _pimg.shape
        p_center_bgr = _pimg[ph // 2, pw // 2]
        p_center_hsv = cv2.cvtColor(np.uint8([[p_center_bgr]]), cv2.COLOR_BGR2HSV)[0][0]
        p_h_tol = 15; p_s_tol = 60; p_v_tol = 60
        # uint8 오버/언더플로우 방지: 정수형으로 변환 후 계산
        _p_i = np.array(p_center_hsv, dtype=np.int16)
        player_lower_hsv = np.array([
            max(0, int(_p_i[0]) - p_h_tol),
            max(0, int(_p_i[1]) - p_s_tol),
            max(0, int(_p_i[2]) - p_v_tol)
        ], dtype=np.uint8)
        player_upper_hsv = np.array([
            min(179, int(_p_i[0]) + p_h_tol),
            min(255, int(_p_i[1]) + p_s_tol),
            min(255, int(_p_i[2]) + p_v_tol)
        ], dtype=np.uint8)
    else:
        player_lower_hsv = np.array([0,100,100]); player_upper_hsv = np.array([10,255,255])
        p_center_hsv = np.array([0,200,200])
else:
    # 기본 빨강 근사 범위
    player_lower_hsv = np.array([0,100,100]); player_upper_hsv = np.array([10,255,255])
    p_center_hsv = np.array([0,200,200])


def find_target_bbox(rgb_img):
    """RGB 이미지에서 타깃 색상을 찾아 가장 정확도가 높은 (원형) 경계 상자를 반환 (CPU 전용)
    주황색(orange) 구간은 노란점 추적에서 제외한다.
    """
    # CPU 전용 경로
    hsv = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2HSV)
    # 기본 노란색 마스크
    mask_y = cv2.inRange(hsv, lower_hsv, upper_hsv)
    # 주황색 마스크(제외 구간)
    orange_lower = np.array([8, 100, 80], dtype=np.uint8)
    orange_upper = np.array([22, 255, 255], dtype=np.uint8)
    mask_orange = cv2.inRange(hsv, orange_lower, orange_upper)
    # 노랑에서 주황 제외
    mask = cv2.bitwise_and(mask_y, cv2.bitwise_not(mask_orange))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_bbox = None
    best_score = float('inf')
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 3:  # 최소 면적을 50으로 증가 (너무 작은 원 제외)
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue

        # 사각형 형태 제외
        approx = cv2.approxPolyDP(cnt, 0.02 * perimeter, True)
        if len(approx) == 4:
            continue

        circularity = 4 * np.pi * area / (perimeter ** 2)
        if circularity < 0.3:  # 원형 필터링 더 느슨
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        # 크기나 정사각형 여부 제한 제거(원형이면 허용)
        roi_hsv = hsv[y:y+h, x:x+w]
        if roi_hsv.size == 0:
            continue
        mean_hsv = roi_hsv.reshape(-1, 3).mean(axis=0)
        dist = np.linalg.norm(mean_hsv - center_hsv)
        score = dist / area
        if score < best_score:
            best_score = score
            best_bbox = (x, y, w, h)
    return best_bbox


def find_player_bbox(rgb_img):
    """puto.png 중심색 기반으로 빨간 원형 하나만 탐지 (노란점과 동일 절차)"""
    hsv = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, player_lower_hsv, player_upper_hsv)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_bbox = None
    best_score = float('inf')
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 2:  # 더 느슨: 최소 면적 완화
            continue
        per = cv2.arcLength(cnt, True)
        if per == 0:
            continue
        approx = cv2.approxPolyDP(cnt, 0.02 * per, True)
        if len(approx) == 4:
            continue
        circ = 4 * np.pi * area / (per * per)
        if circ < 0.2:  # 더 느슨: 원형성 임계치 하향
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        roi = hsv[y:y+h, x:x+w]
        if roi.size == 0:
            continue
        mean_hsv = roi.reshape(-1,3).mean(axis=0)
        dist = np.linalg.norm(mean_hsv - p_center_hsv)
        score = dist / max(1.0, area)
        if score < best_score:
            best_score = score
            best_bbox = (x, y, w, h)
    return best_bbox


# ===== 클래스 없이 오버레이 위젯 생성 =====
def create_overlay_widget():
    overlay = QWidget()
    overlay.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    overlay.setAttribute(Qt.WA_TranslucentBackground)
    overlay.setAttribute(Qt.WA_DeleteOnClose, True)
    overlay.setGeometry(0, 0, QApplication.desktop().screenGeometry().width(),
                        QApplication.desktop().screenGeometry().height())
    overlay.start_pos = None
    overlay.end_pos = None
    overlay.is_dragging = False

    def paint_event(event):
        painter = QPainter(overlay)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(overlay.rect(), QColor(0, 0, 0, 50))
        if overlay.start_pos and overlay.end_pos:
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            x = min(overlay.start_pos.x(), overlay.end_pos.x())
            y = min(overlay.start_pos.y(), overlay.end_pos.y())
            w = abs(overlay.end_pos.x() - overlay.start_pos.x())
            h = abs(overlay.end_pos.y() - overlay.start_pos.y())
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(x, y, w, h, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.drawRect(x, y, w, h)

    def mouse_press(event):
        if event.button() == Qt.LeftButton:
            overlay.start_pos = event.pos()
            overlay.end_pos = event.pos()
            overlay.is_dragging = True
            overlay.update()

    def mouse_move(event):
        if overlay.is_dragging:
            overlay.end_pos = event.pos()
            overlay.update()

    def mouse_release(event):
        if event.button() == Qt.LeftButton and overlay.is_dragging:
            overlay.end_pos = event.pos()
            overlay.is_dragging = False
            global capture_region
            x = min(overlay.start_pos.x(), overlay.end_pos.x())
            y = min(overlay.start_pos.y(), overlay.end_pos.y())
            w = abs(overlay.end_pos.x() - overlay.start_pos.x())
            h = abs(overlay.end_pos.y() - overlay.start_pos.y())
            capture_region = (x, y, w, h)
            overlay.close()

    overlay.paintEvent = paint_event
    overlay.mousePressEvent = mouse_press
    overlay.mouseMoveEvent = mouse_move
    overlay.mouseReleaseEvent = mouse_release
    return overlay


# ===== 캡처: QTimer로 클래스 없이 구현 =====
def start_capture_timer(region, canvas_widget):
    global capture_timer
    if capture_timer is not None:
        capture_timer.stop()
        capture_timer.deleteLater()
        capture_timer = None

    capture_timer = QTimer(canvas_widget)
    capture_timer.setTimerType(Qt.PreciseTimer)

    def on_timeout():
        try:
            screenshot = pyautogui.screenshot(region=region)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            update_canvas(frame, canvas_widget)
        except Exception as e:
            pass

    capture_timer.timeout.connect(on_timeout)
    capture_timer.setInterval(2)
    try:
        from PyQt5.QtCore import QMetaObject as _QMetaObject
        _QMetaObject.invokeMethod(capture_timer, "start", Qt.QueuedConnection)
    except Exception:
        try:
            capture_timer.start()
        except Exception:
            pass  # 마지막 방어


def start_overlay():
    """오버레이 시작"""
    global is_capturing
    is_capturing = True

    overlay = create_overlay_widget()
    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    overlay.setFocus()

    # 오버레이가 닫힐 때까지 대기
    while overlay.isVisible():
        QApplication.processEvents()
        time.sleep(0.01)

    is_capturing = False
    return capture_region


def capture_minimap():
    """미니맵 캡처 함수"""
    # 오버레이 시작
    region = start_overlay()

    if region:
        return region
    else:
        return None


def start_capture(region, canvas_widget):
    """캡처 시작"""
    global capture_region, is_capturing
    capture_region = region
    is_capturing = True
    # 캐릭터 좌표 레이블 초기화
    if hasattr(canvas_widget, 'coord_label') and canvas_widget.coord_label:
        canvas_widget.coord_label.setText("캐릭터좌표: 0,0")
    # 플레이어 알람: 시작 시 체크 상태를 동결
    try:
        import sys
        _main = sys.modules.get('__main__')
        chk = getattr(_main, 'player_alarm_check_box', None)
        globals()['PLAYER_ALARM_ENABLED'] = bool(chk and chk.isChecked())
    except Exception:
        globals()['PLAYER_ALARM_ENABLED'] = False
    start_capture_timer(region, canvas_widget)


def update_canvas(frame, canvas_widget):
    """캔버스 업데이트"""
    try:
        # OpenGL 캔버스에 텍스처로 그리기
        if hasattr(canvas_widget, 'paintGL'):
            # OpenGL 컨텍스트에서 텍스처 업데이트
            canvas_widget.makeCurrent()

            # 텍스처 생성 및 업데이트
            if not hasattr(canvas_widget, 'texture_id'):
                canvas_widget.texture_id = glGenTextures(1)

            # BGR을 RGB로 변환
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # 캔버스 크기에 맞게 리사이즈 (비율 유지)
            canvas_width, canvas_height = 300, 150
            
            # =========================================
            # 1) 원본 해상도에서 타깃 색상 탐지
            # =========================================
            global last_bbox
            bbox_full = find_target_bbox(frame_rgb)  # full-resolution 탐지
            if bbox_full is not None:
                fx, fy, fw, fh = bbox_full
                # 원본 -> 캔버스 스케일 비율
                scale_x = canvas_width / frame_rgb.shape[1]
                scale_y = canvas_height / frame_rgb.shape[0]
                # 스케일링된 bbox (캔버스 기준)
                last_bbox = (
                    int(fx * scale_x),
                    int(fy * scale_y),
                    int(fw * scale_x),
                    int(fh * scale_y),
                )

            # 플레이어 알람(빨간 점) 탐지: 시작 시 체크되었을 때만
            # 런타임 체크박스 상태도 함께 확인 (해제 시 비활성)
            red_bbox = None
            runtime_enabled = False
            try:
                import sys
                _main = sys.modules.get('__main__')
                chk = getattr(_main, 'player_alarm_check_box', None)
                runtime_enabled = bool(chk and chk.isChecked())
            except Exception:
                runtime_enabled = False
            # 시작 시 플래그와 무관하게, 체크박스가 켜져 있으면 항상 탐지 수행
            if runtime_enabled:
                # 차단 영역 적용: 캔버스 좌표계 → 원본 프레임 좌표계로 스케일 후 해당 영역을 무효화
                frame_rgb_red = frame_rgb.copy()
                try:
                    fw, fh = frame_rgb.shape[1], frame_rgb.shape[0]
                    sx = fw / 300.0
                    sy = fh / 150.0
                    if RED_BLOCKS:
                        for (bx, by, bw, bh) in RED_BLOCKS:
                            x0 = max(0, int(bx * sx)); y0 = max(0, int(by * sy))
                            x1 = min(fw, int((bx + bw) * sx)); y1 = min(fh, int((by + bh) * sy))
                            if x1 > x0 and y1 > y0:
                                # 해당 영역 픽셀을 완전 검은색으로 덮어서 탐지 제외
                                frame_rgb_red[y0:y1, x0:x1] = (0,0,0)
                except Exception:
                    pass
                red_bbox = find_player_bbox(frame_rgb_red)
 
            # 캔버스 표시용 프레임 준비
            frame_resized = cv2.resize(frame_rgb, (canvas_width, canvas_height), interpolation=cv2.INTER_LINEAR)
            # 차단 영역 시각화(보라색 사각형)
            try:
                # RED_BLOCKS는 캔버스 좌표(300x150 기준). 현재 frame_resized도 동일 스케일
                if capture_region is not None and RED_BLOCKS:
                    for (bx, by, bw, bh) in RED_BLOCKS:
                        rx, ry, rw, rh = int(bx), int(by), int(bw), int(bh)
                        if rw > 0 and rh > 0:
                            cv2.rectangle(frame_resized, (rx, ry), (rx+rw, ry+rh), (255,0,255), 2)
            except Exception:
                pass

            # ---- 점프다운 저장 좌표 표시 ----
            try:
                for jb in jump_down.jump_blocks:
                    if jb.coord is None:
                        continue
                    jx, jy = jb.coord
                    if 0 <= jx < canvas_width and 0 <= jy < canvas_height:
                        # 점프다운 표시 (녹색 점)
                        cv2.circle(frame_resized, (int(jx), int(jy)), 3, (0,255,0), -1)
                        cv2.putText(frame_resized, "JD", (int(jx)+4, int(jy)-4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0,255,0), 1, cv2.LINE_AA)
                # 플레이어 알람: 빨간점 박스 표시 + 캐릭터 이미지 표시 + mp3 알림 (1.5s 쿨타임)
                if red_bbox is not None:
                    x,y,w,h = red_bbox
                    sx = canvas_width / frame_rgb.shape[1]
                    sy = canvas_height / frame_rgb.shape[0]
                    rx,ry,rw,rh = int(x*sx), int(y*sy), int(w*sx), int(h*sy)
                    # 파란색 테두리 (RGB) - 프레임당 1회만 그리기
                    try:
                        if not hasattr(canvas_widget, '_redbox_drawn') or not canvas_widget._redbox_drawn:
                            cv2.rectangle(frame_resized, (rx,ry), (rx+rw, ry+rh), (0,0,255), 2)
                            canvas_widget._redbox_drawn = True
                    except Exception:
                        cv2.rectangle(frame_resized, (rx,ry), (rx+rw, ry+rh), (0,0,255), 2)
                    # 캐릭터 이미지 그리기 제거
                    try:
                        pass
                    except Exception:
                        pass
                    # pygame 사운드(mp3) 알람 (1.5s 쿨타임)
                    import time as _t
                    nowt = _t.time()
                    if nowt - globals()['_ALARM_LAST_T'] >= 1.5:
                        try:
                            if not globals()['_ALARM_INIT']:
                                pygame.mixer.init()
                                globals()['_ALARM_INIT'] = True
                            if globals()['_ALARM_SOUND'] is None:
                                mp3p = os.path.join('imgs','alarm','alarm.mp3')
                                if os.path.exists(mp3p):
                                    globals()['_ALARM_SOUND'] = pygame.mixer.Sound(mp3p)
                            if globals()['_ALARM_SOUND'] is not None:
                                globals()['_ALARM_SOUND'].play()
                        except Exception:
                            pass
                        globals()['_ALARM_LAST_T'] = nowt
                        # 텔레그램 전송 (플레이어 발견!) - 5초 쿨타임
                        try:
                            import sys
                            _m = sys.modules.get('__main__')
                            pal = getattr(_m, 'player_alarm_check_box', None)
                            if pal and pal.isChecked():
                                # 자체 쿨타임 저장
                                global _TG_PLAYER_LAST
                                if nowt - _TG_PLAYER_LAST >= 5.0:
                                    try:
                                        import telegram as _tg
                                        if _tg.is_configured():
                                            _tg.send_message_async('플레이어 발견!')
                                    except Exception:
                                        pass
                                    _TG_PLAYER_LAST = nowt
                        except Exception:
                            pass
                # ---- 사다리 좌표 & 목표 Y 표시 ----
                for blk in ladder.ladder_blocks:
                    # ladder coordinate
                    if blk.coord is not None:
                        lx, ly = blk.coord
                        if 0 <= lx < canvas_width and 0 <= ly < canvas_height:
                            cv2.circle(frame_resized,(int(lx),int(ly)),3,(0,255,255),-1)  # yellow
                            cv2.putText(frame_resized,"L",(int(lx)+4,int(ly)-4),cv2.FONT_HERSHEY_SIMPLEX,0.35,(0,255,255),1,cv2.LINE_AA)
                            # ladder coord to goal_y 연결선
                            if blk.goal_y is not None and 0<=blk.goal_y<canvas_height:
                                cv2.line(frame_resized,(int(lx),int(ly)),(int(lx),int(blk.goal_y)),(0,255,255),1)

                    # goal_y red horizontal segment
                    if blk.goal_y is not None and blk.floor_edit.text().isdigit():
                        gy = blk.goal_y
                        if 0 <= gy < canvas_height:
                            try:
                                import boundary
                                floor_dict=getattr(boundary,'FLOOR_INPUTS',{})
                            except Exception:
                                floor_dict={}
                            fnum=int(blk.floor_edit.text())
                            start_x=0; end_x=canvas_width-1
                            if fnum in floor_dict:
                                li,ri=floor_dict[fnum]
                                if li.text().isdigit(): start_x=int(li.text())
                                if ri.text().isdigit(): end_x=min(canvas_width-1,int(ri.text()))
                            cv2.line(frame_resized,(start_x,int(gy)),(end_x,int(gy)),(255,0,0),1)
                            floor_label = blk.floor_edit.text()+"F"
                            cv2.putText(frame_resized,floor_label,(start_x+2,int(gy)-2),cv2.FONT_HERSHEY_SIMPLEX,0.35,(255,0,0),1,cv2.LINE_AA)
                # 1층 기준선 표시
                if current_f.first_floor_y is not None:
                    fy = int(current_f.first_floor_y)
                    if 0 <= fy < canvas_height:
                        try:
                            import boundary
                            floor_dict=getattr(boundary,'FLOOR_INPUTS',{})
                        except Exception:
                            floor_dict={}
                        start_x=0; end_x=canvas_width-1
                        if 1 in floor_dict:
                            li,ri=floor_dict[1]
                            if li.text().isdigit(): start_x=int(li.text())
                            if ri.text().isdigit(): end_x=min(canvas_width-1,int(ri.text()))
                        cv2.line(frame_resized,(start_x,fy),(end_x,fy),(255,0,0),1)
                        cv2.putText(frame_resized,"1F",(start_x+2,fy-2),cv2.FONT_HERSHEY_SIMPLEX,0.35,(255,0,0),1,cv2.LINE_AA)

                # ---- 점프 시스템 좌표 표시 (보라색 점 + JP) ----
                try:
                    import sys
                    _m = sys.modules.get('__main__')
                    bf = getattr(_m, 'buffs_frame', None)
                    js = getattr(bf, 'jump_sys_frame', None) if bf else None
                    if js and hasattr(js, 'jump_coords'):
                        for c in js.jump_coords:
                            if not c:
                                continue
                            jx, jy = c
                            if 0 <= jx < canvas_width and 0 <= jy < canvas_height:
                                cv2.circle(frame_resized, (int(jx), int(jy)), 2, (255,0,255), -1)
                                cv2.putText(frame_resized, "JP", (int(jx)+4, int(jy)-4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255,0,255), 1, cv2.LINE_AA)
                except Exception:
                    pass

                # ---- 몬스터 미감지 L/R 표시 (초록 점 + 선) ----
                try:
                    import ignore_mob as _ig
                    lefts = getattr(_ig, '_LEFT_COORDS', [])
                    rights = getattr(_ig, '_RIGHT_COORDS', [])
                    n = min(len(lefts), len(rights)) if isinstance(lefts, list) and isinstance(rights, list) else 0
                    for i in range(n):
                        l = lefts[i] if i < len(lefts) else None
                        r = rights[i] if i < len(rights) else None
                        # 점 그리기
                        if isinstance(l, (list, tuple)) and len(l)==2:
                            lx, ly = int(l[0]), int(l[1])
                            if 0 <= lx < canvas_width and 0 <= ly < canvas_height:
                                cv2.circle(frame_resized, (lx, ly), 2, (0,255,0), -1)
                        if isinstance(r, (list, tuple)) and len(r)==2:
                            rx, ry = int(r[0]), int(r[1])
                            if 0 <= rx < canvas_width and 0 <= ry < canvas_height:
                                cv2.circle(frame_resized, (rx, ry), 2, (0,255,0), -1)
                        # 선 연결
                        if isinstance(l, (list, tuple)) and isinstance(r, (list, tuple)) and len(l)==2 and len(r)==2:
                            lx, ly = int(l[0]), int(l[1])
                            rx, ry = int(r[0]), int(r[1])
                            if (0 <= lx < canvas_width and 0 <= ly < canvas_height and
                                0 <= rx < canvas_width and 0 <= ry < canvas_height):
                                cv2.line(frame_resized, (lx, ly), (rx, ry), (0,255,0), 1)
                except Exception:
                    pass

                # ---- 포탈 좌표 표시 (흰색 점 + P) ----
                try:
                    import sys
                    _m = sys.modules.get('__main__')
                    pf = getattr(_m, 'portal_frame', None)
                    if pf and hasattr(pf, 'portal_coords'):
                        for c in pf.portal_coords:
                            if not c:
                                continue
                            px, py = c
                            if 0 <= px < canvas_width and 0 <= py < canvas_height:
                                cv2.circle(frame_resized, (int(px), int(py)), 2, (255,255,255), -1)
                                cv2.putText(frame_resized, "P", (int(px)+4, int(py)-4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255,255,255), 1, cv2.LINE_AA)
                except Exception:
                    pass
            except Exception:
                pass
            
            # 캔버스 위젯에 bbox 전달 (OpenGL에서 원 그리기용)
            canvas_widget.last_bbox = last_bbox

            # 레이블/좌표 업데이트
            if hasattr(canvas_widget, 'coord_label') and canvas_widget.coord_label is not None:
                if last_bbox is not None:
                    x, y, w, h = last_bbox
                    cx, cy = compute_center_int(x, y, w, h)

                    # 바로 갱신 (스무딩 제거로 실시간 업데이트)

                    canvas_widget.last_cx, canvas_widget.last_cy = cx, cy
                    global current_y, current_x
                    current_y = cy
                    current_x = cx
                    canvas_widget.coord_label.setText(f"캐릭터좌표: {cx},{cy}")

                    # 프레임에 직접 좌표 텍스트 그리기 (겹침 방지) - 초록색 태두리 중앙 바로 위에 배치
                    text = f"{cx},{cy}"
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    tx = int(cx - 29)  # 왼쪽으로 3px 추가 이동
                    ty = max(10, int(cy) - 20)  # 더 위로 이동
                    
                    # 텍스트 크기 계산
                    (text_width, text_height), baseline = cv2.getTextSize(text, font, 0.45, 1)
                    
                    # 검정색 배경 박스 그리기
                    cv2.rectangle(frame_resized, (tx - 2, ty - text_height - 2), (tx + text_width + 2, ty + baseline + 2), (0, 0, 0), -1)
                    
                    # 빨간색 텍스트 그리기
                    cv2.putText(frame_resized, text, (tx, ty), font, 0.4, (255, 0, 0), 1, cv2.LINE_AA)

                    # 층 표시 업데이트
                    if hasattr(canvas_widget, 'floor_label'):
                        new_floor = None
                        # num바 가속 층 계산
                        try:
                            first_y = current_f.first_floor_y if current_f.first_floor_y is not None else -1
                            goals = []
                            floors_arr = []
                            for blk in ladder.ladder_blocks:
                                if blk.goal_y is None:
                                    continue
                                if not blk.floor_edit.text().isdigit():
                                    continue
                                fnum = int(blk.floor_edit.text())
                                if fnum <= 0:
                                    continue
                                goals.append(blk.goal_y)
                                floors_arr.append(fnum)
                            if not goals:
                                new_floor = _determine_floor(current_y, first_y, np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32))
                            else:
                                new_floor = _determine_floor(current_y, first_y, np.array(goals, dtype=np.int32), np.array(floors_arr, dtype=np.int32))

                                # y 오차 허용(-1~-10)으로 보정: 노란점 y(current_y)가 기준 y-1..-10 사이에 있으면 해당 층으로 판정 유지
                                try:
                                    tol = [-1, -2, -3, -4, -5, -6, -7, -8, -9, -10]
                                    cy = int(current_y)
                                    # 1층 기준
                                    if first_y != -1 and any(cy == first_y + d for d in tol):
                                        new_floor = 1
                                    # 사다리 목표 y 비교
                                    for gy, fl in zip(goals, floors_arr):
                                        if any(cy == gy + d for d in tol):
                                            new_floor = fl
                                            break
                                except Exception:
                                    pass

                            if new_floor <= 0:
                                new_floor = None  # 층 미인식시 업데이트 유지
                        except Exception:
                            new_floor = None

                        if new_floor is not None:
                            desired = f"현재층: {new_floor}"
                            if canvas_widget.floor_label.text() != desired:
                                canvas_widget.floor_label.setText(desired)
                                canvas_widget.floor_label.adjustSize()
                                current_f.set_current_floor(new_floor)

            glBindTexture(GL_TEXTURE_2D, canvas_widget.texture_id)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, canvas_width, canvas_height, 0, GL_RGB, GL_UNSIGNED_BYTE, frame_resized)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

            canvas_widget.update()
            # 프레임 종료 시 플래그 리셋
            try:
                if hasattr(canvas_widget, '_redbox_drawn'):
                    canvas_widget._redbox_drawn = False
            except Exception:
                pass

    except Exception as e:
        pass

# 핸들러 함수 정의를 추가합니다.
def handle_minimap_capture(canvas_widget, coord_label):
    """미니맵 캡처 핸들러"""
    canvas_widget.coord_label = coord_label
    region = capture_minimap()
    if region:
        start_capture(region, canvas_widget)


def draw_circle(gl_widget):
    """OpenGL 원형 테두리 그리기 (초록색, x-2 오프셋)"""
    if not hasattr(gl_widget, 'last_bbox') or gl_widget.last_bbox is None:
        return
    x, y, w, h = gl_widget.last_bbox
    # 파란색 박스(사각형)로 변경
    left = float(x)
    right = float(x + w + 1)
    top = float(150 - y)
    bottom = float(150 - (y + h))
    glColor3f(0.0, 0.0, 1.0)  # 파란색
    glBegin(GL_LINE_LOOP)
    glVertex2f(left, bottom)
    glVertex2f(right, bottom)
    glVertex2f(right, top)
    glVertex2f(left, top)
    glEnd()
    glColor3f(1.0, 1.0, 1.0)

# numba 가속 중심 좌표 계산
@njit(cache=True)
def compute_center_int(x, y, w, h):
    return x + w // 2, y + h // 2

# numba 가속 층 계산
@njit(cache=True)
def _determine_floor(cur_y:int32, first_y:int32, goals, floors)->int32:
    # 1층 판정
    if first_y != -1 and abs(cur_y - first_y) <= 3:
        return 1
    # 사다리 목표 y 비교
    for i in range(goals.size):
        if goals[i] == -9999:
            continue
        if cur_y == goals[i]:
            return floors[i]
    return 0

def reset_character_coordinates():
    """캐릭터 좌표 초기화"""
    global last_bbox, current_x, current_y
    last_bbox = None
    current_x = None
    current_y = None

def reset_minimap(canvas_widget):
    """미니맵 캡처/자원 정리"""
    global capture_timer, last_bbox, current_x, current_y, is_capturing
    try:
        if capture_timer is not None:
            try:
                capture_timer.stop()
            except Exception:
                pass
            try:
                capture_timer.deleteLater()
            except Exception:
                pass
            capture_timer = None
    except Exception:
        pass
    try:
        if hasattr(canvas_widget, 'texture_id'):
            try:
                glDeleteTextures(int(canvas_widget.texture_id))
            except Exception:
                pass
            try:
                delattr(canvas_widget, 'texture_id')
            except Exception:
                pass
    except Exception:
        pass
    last_bbox = None
    current_x = None
    current_y = None
    is_capturing = False
    try:
        canvas_widget.update()
    except Exception:
        pass
