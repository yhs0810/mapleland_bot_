from PyQt5.QtWidgets import QFrame, QLabel, QWidget, QCheckBox
import threading, time, os
import cv2
import numpy as np
import pygame

_RUN = False
_THREAD = None
_LAST_ALARM = 0.0
_TEMPLATES = None


def create_macro_prevent_mobs_ui(parent: QWidget, jump_frame: QFrame) -> QFrame:
    frame = QFrame(parent)
    frame.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    # 초기 크기/위치: 점프 시스템과 동일 크기, 바로 아래
    try:
        frame.setFixedSize(jump_frame.width(), jump_frame.height())
        frame.move(jump_frame.x(), jump_frame.y() + jump_frame.height() + 6)
    except Exception:
        pass

    # 상단 중앙에 레이블 + 체크박스
    title = QLabel("매크로방지 몹 핸들러", frame)
    title.setStyleSheet("color:#f1c40f; font-size:12px; font-weight:bold;")
    try:
        title.adjustSize()
    except Exception:
        pass

    enable_chk = QCheckBox("루루모", frame)
    enable_chk.setStyleSheet(
        "QCheckBox {color:#dcdcdc; font-size:14px;} "
        "QCheckBox::indicator { width:18px; height:18px; }"
    )
    guard_chk = QCheckBox("자동경비시스템", frame)
    guard_chk.setStyleSheet(
        "QCheckBox {color:#dcdcdc; font-size:14px;} "
        "QCheckBox::indicator { width:18px; height:18px; }"
    )
    ditroi_chk = QCheckBox("디트와 로이", frame)
    ditroi_chk.setStyleSheet(
        "QCheckBox {color:#dcdcdc; font-size:14px;} "
        "QCheckBox::indicator { width:18px; height:18px; }"
    )
    doll_chk = QCheckBox("선인인형", frame)
    doll_chk.setStyleSheet(
        "QCheckBox {color:#dcdcdc; font-size:14px;} "
        "QCheckBox::indicator { width:18px; height:18px; }"
    )
    lich_chk = QCheckBox("리치", frame)
    lich_chk.setStyleSheet(
        "QCheckBox {color:#dcdcdc; font-size:14px;} "
        "QCheckBox::indicator { width:18px; height:18px; }"
    )

    def place_controls():
        try:
            # 제목 좌상단, 체크박스는 제목 바로 아래 → 그 아래에 자동경비시스템 → 그 아래에 디트와 로이 → 그 아래에 선인인형 → 그 아래에 리치
            title.move(6, 4)
            y0 = 4 + (title.sizeHint().height() if hasattr(title, 'sizeHint') else title.height()) + 6
            enable_chk.move(6, y0)
            y1 = y0 + (enable_chk.sizeHint().height() if hasattr(enable_chk, 'sizeHint') else 20) + 6
            guard_chk.move(6, y1)
            y2 = y1 + (guard_chk.sizeHint().height() if hasattr(guard_chk, 'sizeHint') else 20) + 6
            ditroi_chk.move(6, y2)
            y3 = y2 + (ditroi_chk.sizeHint().height() if hasattr(ditroi_chk, 'sizeHint') else 20) + 6
            doll_chk.move(6, y3)
            y4 = y3 + (doll_chk.sizeHint().height() if hasattr(doll_chk, 'sizeHint') else 20) + 6
            lich_chk.move(6, y4)
        except Exception:
            pass

    place_controls()

    # 리사이즈 시에도 왼쪽 정렬 유지
    try:
        _orig_resize = getattr(frame, 'resizeEvent', None)
        def _on_resize(ev):
            if _orig_resize:
                _orig_resize(ev)
            place_controls()
        frame.resizeEvent = _on_resize
    except Exception:
        pass

    # 참조 보관 (외부 접근 용)
    frame.title_label = title
    frame.enable_chk = enable_chk
    frame.guard_chk = guard_chk
    frame.ditroi_chk = ditroi_chk
    frame.doll_chk = doll_chk
    frame.lich_chk = lich_chk
    frame.place_controls = place_controls

    return frame


def _load_templates():
    global _TEMPLATES
    if _TEMPLATES is not None:
        return _TEMPLATES
    tdir = os.path.join('imgs', 'handle_macro_prevent_mobs')
    names = [
        'C_2_1.png',
        'C_2_2.png',
        'C_2_3.png',
        'C_2_4.png',
        'C_2_5.png',
    ]
    tpls = []
    for n in names:
        p = os.path.join(tdir, n)
        if os.path.exists(p):
            img = cv2.imread(p, cv2.IMREAD_COLOR)
            if img is not None:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                tpls.append((img, gray))
    _TEMPLATES = tpls
    return _TEMPLATES


def _loop(get_frame, get_hunting_canvas):
    global _RUN, _LAST_ALARM
    # pygame mixer lazy init
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
    except Exception:
        pass
    while _RUN:
        try:
            frame_widget = get_frame()
            if not frame_widget or not getattr(frame_widget, 'enable_chk', None) or not frame_widget.enable_chk.isChecked():
                time.sleep(0.1); continue
            # 트레이닝 캔버스 프레임을 가져오기 (training_fun.update_hunting_canvas 에서 쓰는 캔버스)
            try:
                hc = get_hunting_canvas()
            except Exception:
                hc = None
            if not hc:
                time.sleep(0.05); continue
            # training_fun 모듈에서 최신 프레임 접근 경로가 없다면 스킵. 여기서는 템플릿 매칭을 위해 hunting 캡처 루프가 그리는 텍스처 대신 재탐색이 필요하지만,
            # 간소화: minimap 캡처 프레임을 재사용 (원본 프레임 기반). 없으면 스킵
            try:
                import training_fun as tf
                # tf 내부에서 마지막 frame을 보관하지 않으므로, hunting 텍스처를 직접 얻을 수 없음 → 스킵 방지용으로 tf.hunting_region 이 있으면 pyautogui로 재캡처
                import pyautogui
                region = getattr(tf, 'hunting_region', None)
                if not region:
                    time.sleep(0.05); continue
                screenshot = pyautogui.screenshot(region=region)
                bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            except Exception:
                time.sleep(0.05); continue

            if bgr is None or bgr.size == 0:
                time.sleep(0.05); continue
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            tpls = _load_templates()
            found_pts = []
            for (tpl_bgr, tpl_gray) in tpls:
                try:
                    res = cv2.matchTemplate(gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
                    loc = np.where(res >= 0.90)
                    for (y, x) in zip(loc[0].tolist(), loc[1].tolist()):
                        th, tw = tpl_gray.shape
                        cx = x + tw//2; cy = y + th//2
                        found_pts.append((cx, cy, tw, th))
                except Exception:
                    pass
            # 사냥 캔버스에 빨간 동그라미로 오버레이 표시 (OpenGL 텍스처 그리기 전에 frame_resized에 그렸던 방식과 유사하게 처리 불가 → 간소화: 중앙 좌표 텍스트만 표시)
            try:
                if hasattr(hc, 'nearest_label') and found_pts:
                    cx, cy, _, _ = found_pts[0]
                    hc.nearest_label.setText(f"루루모: {cx},{cy}")
                # 알람 1.5s 쿨타임
                now = time.time()
                if found_pts and now - _LAST_ALARM >= 1.5:
                    try:
                        mp3p = os.path.join('imgs','alarm','alarm.mp3')
                        if os.path.exists(mp3p):
                            snd = pygame.mixer.Sound(mp3p)
                            snd.play()
                    except Exception:
                        pass
                    _LAST_ALARM = now
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(0.05)


def start():
    global _RUN, _THREAD
    if _RUN:
        return
    def _get_frame():
        try:
            import sys
            _m = sys.modules.get('__main__')
            bf = getattr(_m, 'buffs_frame', None)
            return getattr(bf, 'macro_handler_frame', None)
        except Exception:
            return None
    def _get_hc():
        try:
            import sys
            _m = sys.modules.get('__main__')
            gc = getattr(getattr(_m, 'minimap', None), 'canvas_widget', None)
            return getattr(gc, 'hunting_canvas', None)
        except Exception:
            return None
    _RUN = True
    _THREAD = threading.Thread(target=_loop, args=(_get_frame, _get_hc), daemon=True)
    _THREAD.start()


def stop():
    global _RUN, _THREAD
    _RUN = False
    try:
        if _THREAD and _THREAD.is_alive():
            _THREAD.join(timeout=0.1)
    except Exception:
        pass
    _THREAD = None
