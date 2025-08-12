from PyQt5.QtWidgets import QCheckBox, QLabel, QFrame, QMessageBox
import threading
import importlib.util

# 전역 UI 참조
lie_chk = None  # QCheckBox

# 정지 이벤트
lie_detector_stop = threading.Event()
_lie_thread = None


def _is_ocr_available() -> bool:
    try:
        # easyocr만 확인 (torch 미사용 경로)
        return importlib.util.find_spec('easyocr') is not None
    except Exception:
        return False


def _make_easyocr_reader():
    try:
        if not _is_ocr_available():
            return None
        import easyocr  # type: ignore
        return easyocr.Reader(['ko'], gpu=False)
    except Exception:
        return None


def _get_logged_in_id():
    try:
        import sys
        _m = sys.modules.get('__main__')
        bframe = getattr(_m, 'buffs_frame', None)
        lf = getattr(bframe, 'login_frame', None) if bframe else None
        return getattr(lf, '_current_login_id', None)
    except Exception:
        return None


def _get_lie_detector_flag(login_id: str) -> int:
    try:
        from database import fetch_one
        import login_frame as _lf
        table = _lf._discover_user_table()
        row = fetch_one(f"SELECT lie_detector FROM `{table}` WHERE login_id=%s LIMIT 1", (login_id,))
        if not row:
            return 0
        val = row.get('lie_detector')
        return int(val) if val is not None else 0
    except Exception:
        return 0


def create_ui(parent_frame: QFrame):
    """플레이어 알람 프레임 내부, 맵 변경 감지 바로 아래에 '거탐' 체크박스 추가"""
    global lie_chk

    lie_chk = QCheckBox("거탐", parent_frame)
    lie_chk.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")

    # 배치 함수: '맵 변경 감지' 체크박스 바로 아래(여백 2px)
    def _place():
        try:
            import sys
            _m = sys.modules.get('__main__')
            anchor = getattr(_m, 'dead_town_check_box', None)
        except Exception:
            anchor = None
        try:
            nx = 6
            if anchor is not None:
                ny = anchor.y() + anchor.height() + 2
            else:
                # fallback: 프레임 내부 상단 기준으로 적절한 기본값
                ny = 30
            lie_chk.move(nx, ny)
        except Exception:
            pass

    _place()

    # 부모 리사이즈 시에도 위치 유지 (anchor 기준 재계산)
    try:
        orig_resize = getattr(parent_frame, 'resizeEvent', None)
        def _on_parent_resize(ev):
            if orig_resize:
                orig_resize(ev)
            _place()
        parent_frame.resizeEvent = _on_parent_resize
    except Exception:
        pass

    # 토글 시 권한 확인 후 시작/정지
    def _on_toggle(checked: bool):
        try:
            if checked:
                login_id = _get_logged_in_id()
                if not login_id:
                    QMessageBox.warning(lie_chk.parent() or parent_frame, "거탐", "로그인 후 사용 가능합니다.")
                    lie_chk.blockSignals(True)
                    lie_chk.setChecked(False)
                    lie_chk.blockSignals(False)
                    return
                flag = _get_lie_detector_flag(login_id)
                if flag != 1:
                    QMessageBox.critical(lie_chk.parent() or parent_frame, "거탐", "이 계정은 거탐 권한이 없습니다.")
                    lie_chk.blockSignals(True)
                    lie_chk.setChecked(False)
                    lie_chk.blockSignals(False)
                    return
                # OCR 가용성 확인 (torch/easyocr 없으면 자동 비활성화)
                if not _is_ocr_available():
                    try:
                        QMessageBox.critical(lie_chk.parent() or parent_frame, "거탐", "OCR 엔진이 설치되어 있지 않아 사용할 수 없습니다.")
                    except Exception:
                        pass
                    lie_chk.blockSignals(True)
                    lie_chk.setChecked(False)
                    lie_chk.blockSignals(False)
                    return
                start()
            else:
                stop()
        except Exception:
            # 오류 시 안전하게 비활성화 복구
            try:
                lie_chk.blockSignals(True)
                lie_chk.setChecked(False)
                lie_chk.blockSignals(False)
            except Exception:
                pass

    try:
        lie_chk.toggled.connect(_on_toggle)
    except Exception:
        pass

    # 전역 노출
    try:
        import sys
        setattr(sys.modules.get('__main__'), 'lie_detector_check_box', lie_chk)
    except Exception:
        pass

    # 초기 상태가 체크되어 있으면 권한 검사 후 시작
    try:
        if lie_chk.isChecked():
            _on_toggle(True)
    except Exception:
        pass

    return lie_chk


# -----------------------
# 요청된 거탐 루프 (그대로 구현) + CUDA 제거 + OpenCL 활성화 + 속도 최적화
# -----------------------

def lie_detector_loop():
    global lie_detector_stop
    reader = _make_easyocr_reader()
    if reader is None:
        # OCR 미가용 시 즉시 종료 (예외 없이)
        return
    import numpy as np
    import time
    import cv2
    import mss
    import pygame
    import os
    import threading as _threading
    import gc

    # OpenCL 사용 시도
    try:
        if cv2.ocl.haveOpenCL():
            cv2.ocl.setUseOpenCL(True)
    except Exception:
        pass

    # EasyOCR CPU 모드, 캔버스 사이즈 축소로 가속
    keywords = ["안전", "전한", "한장", "장소", "소에", "에서", "서창", "창을", "을", "번클", "클릭", "릭하", "세요"]
    region = (6, 123, 1278, 656)
    last_alarm_time = 0
    cooltime = 9
    frame_count = 0
    alarm_sound_path = 'imgs/alarm/alarm.mp3'

    _sound_cache = {"init": False, "obj": None}

    def play_alarm():
        try:
            import pygame as _pg, os as _os
            if not _sound_cache["init"]:
                _pg.mixer.init()
                _sound_cache["init"] = True
            if _sound_cache["obj"] is None and _os.path.exists(alarm_sound_path):
                _sound_cache["obj"] = _pg.mixer.Sound(alarm_sound_path)
            if _sound_cache["obj"] is not None:
                _sound_cache["obj"].play()
        except Exception as e:
            print(f'사운드 재생 오류: {e}')

    SCALE = 1.0  # 다운스케일 해제(인식률 유지)

    with mss.mss() as sct:
        monitor = {
            "left": region[0],
            "top": region[1],
            "width": region[2] - region[0],
            "height": region[3] - region[1]
        }
        while not lie_detector_stop.is_set():
            sct_img = sct.grab(monitor)
            frame = np.array(sct_img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            if SCALE != 1.0:
                frame = cv2.resize(frame, (int(frame.shape[1]*SCALE), int(frame.shape[0]*SCALE)), interpolation=cv2.INTER_AREA)

            # OpenCL UMat 가속 시도
            try:
                if cv2.ocl.useOpenCL():
                    frame_u = cv2.UMat(frame)
                    hsv_u = cv2.cvtColor(frame_u, cv2.COLOR_BGR2HSV)
                    hsv = hsv_u.get()
                else:
                    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            except Exception:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            h, s, v = cv2.split(hsv)
            # 간소화된 주변 유사도 강조(다운스케일로도 충분)
            ksize = 3
            pad = ksize // 2
            h_pad = cv2.copyMakeBorder(h, pad, pad, pad, pad, cv2.BORDER_REFLECT)
            patches = np.lib.stride_tricks.sliding_window_view(h_pad, (ksize, ksize))
            center = h
            patch_flat = patches.reshape(h.shape[0], h.shape[1], -1)
            center_exp = center[..., None]
            similar = np.sum(np.abs(patch_flat.astype(int) - center_exp) < 20, axis=-1)
            mask = similar >= 3
            s[mask] = 255
            v[mask] = 255
            hsv_new = cv2.merge([h, s, v])
            processed = cv2.cvtColor(hsv_new, cv2.COLOR_HSV2BGR)

            processed_gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
            processed_bin = cv2.adaptiveThreshold(
                processed_gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 21, 0
            )

            # OCR 호출(캔버스 축소 파라미터 적용) - 두 입력 중 먼저 성공 시 빠른 종료
            alarm_triggered = False
            draw_boxes1 = []
            draw_boxes2 = []

            try:
                results1 = reader.readtext(processed, detail=1, paragraph=False, canvas_size=1280, mag_ratio=0.7)
            except Exception:
                results1 = []
            for (bbox, text, conf) in results1:
                if conf >= 0.55 and any(kw in text for kw in keywords):
                    draw_boxes1.append((bbox, text, conf))
                    alarm_triggered = True
                    break  # 빠른 종료

            if not alarm_triggered:
                try:
                    results2 = reader.readtext(processed_bin, detail=1, paragraph=False, canvas_size=1280, mag_ratio=0.7)
                except Exception:
                    results2 = []
                for (bbox, text, conf) in results2:
                    if conf >= 0.55 and any(kw in text for kw in keywords):
                        draw_boxes2.append((bbox, text, conf))
                        alarm_triggered = True
                        break

            # 감지 시에만 복사/그리기/저장 수행
            if alarm_triggered:
                try:
                    # 저장 비활성화: 시각화만 내부 유지 (파일로 기록하지 않음)
                    # processed_box = processed.copy()
                    # for (bbox, _, _) in draw_boxes1:
                    #     pts = np.array(bbox, dtype=np.int32)
                    #     cv2.polylines(processed_box, [pts], isClosed=True, color=(0,0,255), thickness=2)
                    # processed_bin_color = cv2.cvtColor(processed_bin, cv2.COLOR_GRAY2BGR)
                    # for (bbox, _, _) in draw_boxes2:
                    #     pts = np.array(bbox, dtype=np.int32)
                    #     cv2.polylines(processed_bin_color, [pts], isClosed=True, color=(0,0,255), thickness=2)
                    pass
                except Exception:
                    pass

            now = time.time()
            if alarm_triggered and (now - last_alarm_time > cooltime):
                try:
                    _threading.Thread(target=play_alarm, daemon=True).start()
                except Exception:
                    pass
                last_alarm_time = now
                # 텔레그램 전송 (거탐 발견!) - 쿨타임 없음
                try:
                    import telegram as _tg
                    if _tg.is_configured():
                        _tg.send_message_async('거탐 발견!')
                except Exception:
                    pass

            frame_count += 1
            if frame_count % 100 == 0:
                try:
                    del processed_gray, processed_bin
                    gc.collect()
                except Exception:
                    pass

            if lie_detector_stop.is_set():
                break


def start():
    global _lie_thread
    try:
        if _lie_thread and _lie_thread.is_alive():
            return
    except Exception:
        pass
    try:
        if not (lie_chk and lie_chk.isChecked()):
            return
    except Exception:
        return
    lie_detector_stop.clear()
    _lie_thread = threading.Thread(target=lie_detector_loop, daemon=True)
    _lie_thread.start()


def stop():
    lie_detector_stop.set()
    try:
        if _lie_thread and _lie_thread.is_alive():
            _lie_thread.join(timeout=0.1)
    except Exception:
        pass
