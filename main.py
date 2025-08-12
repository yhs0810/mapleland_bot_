import os
import sys

# .venv PyQt5 Qt5 plugins 경로를 최우선으로 등록 (PyQt 임포트 이전)
if hasattr(sys, "frozen"):
    qt_plugin_path = os.path.join(sys._MEIPASS, "PyQt5", "Qt5", "plugins")
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    qt_plugin_path = os.path.join(base_dir, ".venv", "Lib", "site-packages", "PyQt5", "Qt5", "plugins")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = qt_plugin_path
os.environ.setdefault("QT_PLUGIN_PATH", qt_plugin_path)

from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLabel
from PyQt5.QtOpenGL import QGLWidget
from PyQt5.QtGui import QIcon
import os
from PyQt5.QtCore import Qt
from OpenGL.GL import *
from OpenGL.GLU import *
import minimap
import boundary
import start_stop
import current_f
import ladder
import training_fun
import ign_capture
import monster_capture
import attack_range
import attack_key
import buffs
from math import cos, sin, pi
from collections import deque
import jump_down
import portal_system
from PyQt5.QtWidgets import QSlider
from PyQt5.QtCore import Qt as _Qt
import training_fun as _tf
from PyQt5.QtWidgets import QFrame, QCheckBox
import dead_or_town
import lie_detector
from PyQt5.QtCore import QTimer
import sys as _sys
import sys as _sys

# (moved to top)


# 전역: 로그인 상태
IS_LOGGED_IN = False


def create_gl_canvas():
    gl_widget = QGLWidget()
    gl_widget.setFixedSize(300, 150)
    # 회색 테두리 추가
    gl_widget.setStyleSheet("border: 1px solid #666;")
    
    def initializeGL():
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glEnable(GL_TEXTURE_2D)
    
    def resizeGL(width, height):
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, width, 0, height, -1, 1)
        glMatrixMode(GL_MODELVIEW)
    
    def paintGL():
        glClear(GL_COLOR_BUFFER_BIT)
        glLoadIdentity()
        
        # 텍스처가 있으면 그리기
        if hasattr(gl_widget, 'texture_id'):
            glBindTexture(GL_TEXTURE_2D, gl_widget.texture_id)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 1); glVertex2f(0, 0)
            glTexCoord2f(1, 1); glVertex2f(300, 0)
            glTexCoord2f(1, 0); glVertex2f(300, 150)
            glTexCoord2f(0, 0); glVertex2f(0, 150)
            glEnd()
            glBindTexture(GL_TEXTURE_2D, 0)

        # 원형 테두리 그리기 (minimap.py)
        minimap.draw_circle(gl_widget)
    
    gl_widget.initializeGL = initializeGL
    gl_widget.resizeGL = resizeGL
    gl_widget.paintGL = paintGL
    
    return gl_widget

def create_hunting_gl_canvas():
    """사냥구역용 OpenGL 캔버스 생성"""
    hunting_gl_widget = QGLWidget()
    hunting_gl_widget.setFixedSize(300, 150)
    # 회색 테두리 추가
    hunting_gl_widget.setStyleSheet("border: 1px solid #666;")
    
    def initializeGL():
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glEnable(GL_TEXTURE_2D)
    
    def resizeGL(width, height):
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, width, 0, height, -1, 1)
        glMatrixMode(GL_MODELVIEW)
    
    def paintGL():
        glClear(GL_COLOR_BUFFER_BIT)
        glLoadIdentity()
        
        # 텍스처가 있으면 그리기
        if hasattr(hunting_gl_widget, 'texture_id'):
            glBindTexture(GL_TEXTURE_2D, hunting_gl_widget.texture_id)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 1); glVertex2f(0, 0)
            glTexCoord2f(1, 1); glVertex2f(300, 0)
            glTexCoord2f(1, 0); glVertex2f(300, 150)
            glTexCoord2f(0, 0); glVertex2f(0, 150)
            glEnd()
            glBindTexture(GL_TEXTURE_2D, 0)
    
    hunting_gl_widget.initializeGL = initializeGL
    hunting_gl_widget.resizeGL = resizeGL
    hunting_gl_widget.paintGL = paintGL
    
    return hunting_gl_widget

def create_main_window():
    window = QMainWindow()
    window.setWindowTitle("Kakaotalk")
    icon_path = os.path.join('imgs', 'icon', 'no.ico')
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.setGeometry(100, 100, 1200, 800)
    window.setFixedSize(1200, 800)
    
    central_widget = QWidget()
    central_widget.setStyleSheet("background-color: #d0d0d0;")  # 한 단계 더 어둡게
    window.setCentralWidget(central_widget)
    
    minimap_button = QPushButton("미니맵 캡처", central_widget)
    minimap_button.setFixedSize(120, 30)
    minimap_button.setStyleSheet("QPushButton {background:#7d7d7d; color:white; border:none;} QPushButton:hover{background:#9e9e9e;} QPushButton:pressed{background:#5d5d5d;}")
    minimap_button.move(10, 10)
    minimap_button.clicked.connect(lambda: minimap.handle_minimap_capture(gl_canvas, coord_label))

    # 사냥구역 캡처 버튼 추가
    hunting_button = training_fun.create_hunting_capture_button(central_widget, minimap_button)

    # IGN 캡처 버튼
    ign_button = QPushButton("IGN 캡처", central_widget)
    ign_button.setFixedSize(120, 30)
    ign_button.setStyleSheet("QPushButton {background:#7d7d7d; color:white; border:none;} QPushButton:hover{background:#9e9e9e;} QPushButton:pressed{background:#5d5d5d;}")
    ign_button.move(10, 10 + minimap_button.height()*2 + 10)  # 사냥구역 버튼 아래
    ign_button.clicked.connect(lambda: ign_capture.capture_ign())

    # 좌표 레이블 박스 생성
    coord_label = QLabel("캐릭터좌표: 0,0", central_widget)
    coord_label.setFixedSize(118, 30)
    coord_label.setStyleSheet("border: 1px solid black; background-color: #ffffff;")
    coord_label.move(140, 10)

    # GPU 캔버스 - 오른쪽 꼭대기에 절대 위치로 배치
    gl_canvas = create_gl_canvas()
    gl_canvas.setParent(central_widget)
    gl_canvas.move(890, 10)
    minimap.canvas_widget = gl_canvas
    gl_canvas.coord_label = coord_label  # coord_label을 gl_canvas에 설정
    floor_label = current_f.create_floor_ui(central_widget)
    gl_canvas.floor_label = floor_label

    # 사냥구역 캔버스 - 미니맵 캔버스 아래에 배치
    hunting_canvas = create_hunting_gl_canvas()
    hunting_canvas.setParent(central_widget)
    hunting_canvas.move(890, 161)  # 미니맵 캔버스 아래 (10 + 150 + 10)
    gl_canvas.hunting_canvas = hunting_canvas  # gl_canvas에 hunting_canvas 연결
    
    # IGN 좌표 레이블 추가 (전역 변수로 노출)
    global ign_coord_label
    ign_coord_label = QLabel("IGN 좌표: 0,0", central_widget)
    ign_coord_label.setFixedSize(118, 30)
    ign_coord_label.setStyleSheet("background: transparent; border: none;")
    ign_coord_label.move(890, 310)  # 10px 위로 이동
    hunting_canvas.ign_coord_label = ign_coord_label

    # 가장 가까운 몹 좌표 레이블 (IGN 오른쪽)
    nearest_label = QLabel("가장 가까운 몬스터: 0,0", central_widget)
    nearest_label.setFixedSize(160, 30)
    nearest_label.setStyleSheet("background: transparent; border: none;")
    nearest_label.move(ign_coord_label.x() + ign_coord_label.width() + 26, ign_coord_label.y())  # y 이동 자동 반영 (+14px)
    hunting_canvas.nearest_label = nearest_label

    # 몬스터 캡처/초기화 버튼 생성 (IGN 버튼 아래)
    mon_cap_btn, mon_clr_btn, mon_open_btn = monster_capture.create_monster_buttons(central_widget, ign_button)

    # 포탈 프레임 (몬스터 폴더 바로 아래)
    try:
        global portal_frame
        portal_frame = portal_system.create_portal_ui(central_widget, mon_open_btn)
    except Exception:
        portal_frame = None

    # 정확도 슬라이더 + 레이블
    acc_label = QLabel("몬스터 정확도: 100", central_widget)
    acc_label.move(138, 56) 
    acc_slider = QSlider(_Qt.Horizontal, central_widget)
    acc_slider.setMinimum(50); acc_slider.setMaximum(100); acc_slider.setValue(100)
    # 레이블 바로 아래 배치
    acc_slider.move(acc_label.x(), acc_label.y() + acc_label.height() + 3)
    # 미니맵 캡처 버튼 색상에 맞춘 스타일
    acc_slider.setStyleSheet(
        """
        QSlider::groove:horizontal { height:6px; background:#6c6c6c; border-radius:3px; }
        QSlider::sub-page:horizontal { background:#8a8a8a; border-radius:3px; }
        QSlider::add-page:horizontal { background:#4f4f4f; border-radius:3px; }
        QSlider::handle:horizontal { background:#bfbfbf; width:14px; height:14px; margin:-5px 0; border:1px solid #3a3a3a; border-radius:7px; }
        QSlider::handle:horizontal:hover { background:#d5d5d5; }
        QSlider::handle:horizontal:pressed { background:#e0e0e0; }
        """
    )
    # 캐릭터좌표 레이블 오른쪽 끝에 맞춰 가로 길이 설정
    target_right = coord_label.x() + coord_label.width()
    slider_width = max(60, target_right - acc_slider.x())
    acc_slider.setFixedWidth(slider_width)
    def _on_acc(val):
        acc_label.setText(f"몬스터 정확도: {val}")
        _tf.MON_THRESH = float(val)
    # 초기값 동기화 보장
    _on_acc(100)
    acc_slider.valueChanged.connect(_on_acc)
    # 전역 보관 (다른 모듈에서 접근 필요 시)
    global monster_acc_slider
    monster_acc_slider = acc_slider
    global monster_acc_label
    monster_acc_label = acc_label

    # 사다리 프레임 추가 (캔버스 왼쪽)
    ladder_frame = ladder.create_ladder_ui(central_widget, gl_canvas)
    jump_frame = jump_down.create_jumpdown_ui(central_widget, ladder_frame)

    # 공격 범위 설정 프레임: x 는 IGN 좌표 기준, y 는 jump_frame 과 동일
    atk_frame = attack_range.create_attack_range_ui(central_widget, ign_coord_label)
    atk_frame.move(atk_frame.x(), jump_frame.y())
    # jump_frame 높이에 맞춰 아래로 확장
    atk_frame.setFixedHeight(jump_frame.height())
    attack_range.adjust_layout(atk_frame)

    # 공격 제어 프레임 (atk_frame 오른쪽, nearest_label 우측 끝까지)
    ctrl_frame = attack_key.create_attack_ctrl_ui(central_widget, atk_frame, nearest_label)

    global attack_key_frame
    attack_key_frame = ctrl_frame
    
    # 버프 프레임 추가 (공격 프레임 아래)
    try:
        global buffs_frame
        buffs_frame = buffs.create_buffs_ui(central_widget, ctrl_frame)
        # 사다리 프레임 꼭대기 y 기준, 사다리 프레임 바로 왼쪽에 배치
        def _place_buffs():
            try:
                margin = 6
                # 폭을 캐릭터좌표 레이블 오른쪽끝까지 확장
                coord_right = minimap_button.x() + (gl_canvas.coord_label.x() + gl_canvas.coord_label.width() - minimap_button.x())
                target_w = max(220, coord_right - 6)
                buffs_frame.setFixedWidth(target_w)
                new_x = max(6, ladder_frame.x() - buffs_frame.width() - margin)
                new_y = ladder_frame.y()
                buffs_frame.move(new_x, new_y)
                # 펫먹이/자동줍기/고정키/텔레포트 프레임을 세로로 나란히 배치
                try:
                    if hasattr(buffs_frame, 'pet_frame') and buffs_frame.pet_frame:
                        buffs_frame.pet_frame.setFixedWidth(buffs_frame.width())
                        buffs_frame.pet_frame.move(buffs_frame.x(), buffs_frame.y() + buffs_frame.height() + 6)
                    # 자동줍기: 펫먹이 바로 아래
                    if hasattr(buffs_frame, 'loot_frame') and buffs_frame.loot_frame:
                        buffs_frame.loot_frame.setFixedWidth(buffs_frame.width())
                        buffs_frame.loot_frame.move(
                            buffs_frame.x(),
                            buffs_frame.pet_frame.y() + buffs_frame.pet_frame.height() + 6
                        )
                    # 고정키: 자동줍기 바로 아래
                    if hasattr(buffs_frame, 'fixed_key_frame') and buffs_frame.fixed_key_frame:
                        buffs_frame.fixed_key_frame.setFixedWidth(buffs_frame.width())
                        buffs_frame.fixed_key_frame.move(
                            buffs_frame.x(),
                            buffs_frame.loot_frame.y() + buffs_frame.loot_frame.height() + 6
                        )
                    # 텔레포트: 고정키 바로 아래 (없으면 자동줍기 아래)
                    if hasattr(buffs_frame, 'tele_frame') and buffs_frame.tele_frame:
                        anchor_y = (buffs_frame.fixed_key_frame.y() + buffs_frame.fixed_key_frame.height() + 6) if (
                            hasattr(buffs_frame, 'fixed_key_frame') and buffs_frame.fixed_key_frame
                        ) else (buffs_frame.loot_frame.y() + buffs_frame.loot_frame.height() + 6)
                        buffs_frame.tele_frame.setFixedWidth(buffs_frame.width())
                        buffs_frame.tele_frame.move(buffs_frame.x(), anchor_y)
                    # 점프 시스템: 텔레포트 바로 아래
                    try:
                        if hasattr(buffs_frame, 'jump_sys_frame') and buffs_frame.jump_sys_frame:
                            buffs_frame.jump_sys_frame.setFixedWidth(buffs_frame.width())
                            buffs_frame.jump_sys_frame.move(buffs_frame.x(), buffs_frame.tele_frame.y() + buffs_frame.tele_frame.height() + 7)
                    except Exception:
                        pass
                    # 매크로방지 몹 핸들러: 점프 시스템 바로 아래, 동일 폭
                    try:
                        if hasattr(buffs_frame, 'macro_handler_frame') and buffs_frame.macro_handler_frame and hasattr(buffs_frame, 'jump_sys_frame') and buffs_frame.jump_sys_frame:
                            mh = buffs_frame.macro_handler_frame
                            jf = buffs_frame.jump_sys_frame
                            mh.setFixedWidth(buffs_frame.width())
                            mh.move(buffs_frame.x(), jf.y() + jf.height() + 6)
                            try:
                                mh.show()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # 몬스터 미감지: 점프 시스템 왼쪽에 동일 크기/수평 정렬 (간격 9px, 너비 -2px)
                    try:
                        if hasattr(buffs_frame, 'ignore_mob_frame') and getattr(buffs_frame, 'ignore_mob_frame') and hasattr(buffs_frame, 'jump_sys_frame') and getattr(buffs_frame, 'jump_sys_frame'):
                            ig = buffs_frame.ignore_mob_frame
                            jf = buffs_frame.jump_sys_frame
                            # 기존 왼쪽 기준 보존 (폭 jf.width()-2, 간격 12)
                            left_old = jf.x() - max(0, jf.width()-2) - 12
                            ig.setFixedSize(max(0, jf.width()-4), jf.height())
                            ig.move(left_old, jf.y()+1)
                    except Exception:
                        pass
                    # 윗텔: 미감지 바로 아래 동일 크기 배치
                    try:
                        if hasattr(buffs_frame, 'login_frame') and getattr(buffs_frame, 'login_frame') and hasattr(buffs_frame, 'ignore_mob_frame') and getattr(buffs_frame, 'ignore_mob_frame'):
                            up = buffs_frame.login_frame
                            ig = buffs_frame.ignore_mob_frame
                            up.setFixedSize(ig.width(), ig.height())
                            up.move(ig.x(), ig.y() + ig.height() + 6)
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass
        _place_buffs()
        # 부모 리사이즈 시에도 재배치
        orig_resize = getattr(central_widget, 'resizeEvent', None)
        def _bz_resize(ev):
            if orig_resize:
                orig_resize(ev)
            _place_buffs()
        central_widget.resizeEvent = _bz_resize
    except Exception:
        pass

    # ----- 플레이어 알람 프레임 (몬스터캡처 버튼 오른쪽) -----
    player_alarm_frame = QFrame(central_widget)
    player_alarm_frame.setStyleSheet("background:#4a4a4a; border:1px solid #666; border-radius:6px;")
    player_alarm_frame.setFixedHeight(60)
    # 체크박스
    player_alarm_check = QCheckBox("플레이어 알람", player_alarm_frame)
    player_alarm_check.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:10px;}")
    player_alarm_check.move(6, 10)

    # 죽음/마을 감지 UI 추가 (플레이어 알람 요소 바로 아래)
    try:
        import dead_or_town
        dead_or_town.create_ui(player_alarm_frame, player_alarm_check)
        # 거탐 체크박스 UI 추가 (맵 변경 레이블 아래)
        try:
            import lie_detector
            lie_detector.create_ui(player_alarm_frame)
        except Exception:
            pass
    except Exception:
        pass
    # 배치 함수: 몬스터캡처 버튼 오른쪽, 펫먹이 프레임 왼쪽 x 까지 폭 확장
    def _place_player_alarm():
        try:
            margin = 6
            x = mon_cap_btn.x() + mon_cap_btn.width() + margin
            # 세로 범위: 몬스터 캡처 버튼 y 부터 몬스터 폴더 버튼 하단까지 확장
            y_top = mon_cap_btn.y()
            y_bottom = mon_open_btn.y() + mon_open_btn.height()
            height = max(30, y_bottom - y_top)
            player_alarm_frame.setFixedHeight(height)
            y = y_top
            right_limit = x + 200
            try:
                if hasattr(buffs_frame, 'pet_frame'):
                    right_limit = buffs_frame.pet_frame.x()
                else:
                    right_limit = buffs_frame.x()
            except Exception:
                pass
            # 캐릭터좌표 레이블 오른쪽 끝 - 5px 로 제한
            try:
                coord_right = gl_canvas.coord_label.x() + gl_canvas.coord_label.width()
                right_limit = min(right_limit, coord_right - 5)
            except Exception:
                pass
            # 여유를 10px까지 축소
            w = max(120, (right_limit - x))
            player_alarm_frame.setFixedWidth(w)
            player_alarm_frame.move(x, y)

        except Exception:
            pass
    _place_player_alarm()
    # 중앙 위젯 리사이즈 시 재배치 포함
    old_resize = getattr(central_widget, 'resizeEvent', None)
    def _pa_resize(ev):
        if old_resize and old_resize is not _bz_resize:
            old_resize(ev)
        _place_player_alarm()
    central_widget.resizeEvent = _pa_resize

    # 전역 노출 (start 시 상태 캡처용)
    global player_alarm_check_box
    player_alarm_check_box = player_alarm_check

    # 사냥캔버스 오른쪽 끝까지 레이블/공격설정 프레임 폭 확장 (초기+지연 재적용)
    try:
        def _apply_right_edge_layout():
            try:
                right_edge = gl_canvas.hunting_canvas.x() + gl_canvas.hunting_canvas.width()
                # 가장 가까운 몬스터 레이블 폭 확장
                if hasattr(gl_canvas.hunting_canvas, 'nearest_label'):
                    nl = gl_canvas.hunting_canvas.nearest_label
                    nl.setFixedWidth(max(160, right_edge - nl.x() - 6))
                # 공격 설정 프레임 폭 확장
                if 'attack_key_frame' in globals():
                    akf = attack_key_frame
                    akf.setFixedWidth(max(140, right_edge - akf.x() - 6))
            except Exception:
                pass
        _apply_right_edge_layout()
        QTimer.singleShot(200, _apply_right_edge_layout)
        QTimer.singleShot(800, _apply_right_edge_layout)
    except Exception:
        pass
    
    # 전역 노출
    global attack_range_frame
    attack_range_frame = atk_frame

    # 하단 왼쪽 Boundary UI 추가
    boundary_inputs = boundary.create_boundary_ui(central_widget)
    start_button, stop_button = start_stop.create_start_stop_ui(central_widget, boundary_inputs)
    # 전역 플래그 초기화 (F1 가드)
    _m = _sys.modules.get('__main__')
    setattr(_m, 'F1_DISABLED', False)
    # 현재층 레이블을 시작 버튼 바로 위로 재배치
    try:
        if hasattr(gl_canvas, 'floor_label') and gl_canvas.floor_label:
            _floor_lbl = gl_canvas.floor_label
            def _place_floor():
                try:
                    new_y = start_button.y() - _floor_lbl.height() - 4
                    _floor_lbl.move(_floor_lbl.x(), new_y)
                except Exception:
                    pass
            _place_floor()
            _prev_resize = getattr(central_widget, 'resizeEvent', None)
            def _floor_resize(ev):
                if _prev_resize:
                    _prev_resize(ev)
                _place_floor()
            central_widget.resizeEvent = _floor_resize
        # 정지 버튼 전역 노출
        _m = sys.modules.get('__main__')
        setattr(_m, 'stop_button_instance', stop_button)
    except Exception:
        pass
    
    # monster 폴더 실시간 감시 시작
    try:
        training_fun.ensure_mon_watch(central_widget)
    except Exception:
        pass
    
    # ----- 모든 위젯 비활성화 후 로그인 버튼만 활성화 -----
    def _set_enabled_all(root: QWidget, enabled: bool):
        try:
            lf = getattr(buffs_frame, 'login_frame', None)
            for w in root.findChildren(QWidget):
                # 로그인 프레임과 그 버튼은 항상 제외
                if lf and (w is lf or w is getattr(lf, 'login_btn', None) or w is getattr(lf, 'logout_btn', None)):
                    continue
                w.setEnabled(enabled)
        except Exception:
            pass

    # 강제 로그아웃 및 전체 잠금
    def _force_logout_and_lock():
        try:
            lf = getattr(buffs_frame, 'login_frame', None)
            login_id = getattr(lf, '_current_login_id', None) if lf else None
            if login_id:
                try:
                    from database import execute
                    from login_frame import _discover_user_table
                    table = _discover_user_table()
                    # GUI 종료 시 session_count를 0으로 초기화
                    execute(f"UPDATE `{table}` SET is_logined = 0, session_count = 0 WHERE login_id = %s", (login_id,))
                except Exception:
                    pass
        except Exception:
            pass
        # 모든 매크로/핫키 정지 및 UI 잠금
        try:
            import start_stop as _ss
            _ss.disable_all_and_stop()
        except Exception:
            pass
        # 자원 정리
        try:
            if hasattr(minimap, 'canvas_widget') and minimap.canvas_widget:
                minimap.reset_minimap(minimap.canvas_widget)
        except Exception:
            pass
        try:
            if hasattr(minimap, 'canvas_widget') and hasattr(minimap.canvas_widget, 'hunting_canvas'):
                training_fun.reset_hunting(minimap.canvas_widget)
        except Exception:
            pass
        try:
            _set_enabled_all(central_widget, False)
            lf = getattr(buffs_frame, 'login_frame', None)
            if lf:
                lf.set_user("-")
                lf.set_remaining(0)
                lf.set_logged_in(False)
                setattr(lf, '_current_login_id', None)
                lf.setEnabled(True)
                try:
                    lf.login_btn.setEnabled(True)
                    lf.logout_btn.setEnabled(True)
                except Exception:
                    pass
        except Exception:
            pass

    # 초기 비활성화
    _set_enabled_all(central_widget, False)
    try:
        lf = getattr(buffs_frame, 'login_frame', None)
        if lf and hasattr(lf, 'login_btn') and hasattr(lf, 'logout_btn'):
            lf.setEnabled(True)
            lf.login_btn.setEnabled(True)
            lf.logout_btn.setEnabled(True)
            # 콜백 연결: 로그인 성공/로그아웃 시 토글 + 전역 플래그 갱신
            def _on_login_cb():
                import sys as _sys
                _m = _sys.modules.get('__main__')
                setattr(_m, 'IS_LOGGED_IN', True)
                setattr(_m, 'F1_DISABLED', False)
                _set_enabled_all(central_widget, True)
                try:
                    lf.logout_btn.setEnabled(True)
                except Exception:
                    pass
            def _on_logout_cb():
                import sys as _sys
                _m = _sys.modules.get('__main__')
                setattr(_m, 'IS_LOGGED_IN', False)
                setattr(_m, 'F1_DISABLED', True)
                # 로그아웃 시에도 자원 정리
                try:
                    if hasattr(minimap, 'canvas_widget') and minimap.canvas_widget:
                        minimap.reset_minimap(minimap.canvas_widget)
                except Exception:
                    pass
                try:
                    if hasattr(minimap, 'canvas_widget') and hasattr(minimap.canvas_widget, 'hunting_canvas'):
                        training_fun.reset_hunting(minimap.canvas_widget)
                except Exception:
                    pass
                _set_enabled_all(central_widget, False)
                try:
                    lf.login_btn.setEnabled(True)
                    lf.logout_btn.setEnabled(True)
                except Exception:
                    pass
            lf.on_login_success = _on_login_cb
            lf.on_logout = _on_logout_cb
    except Exception:
        pass

    # 로그인 완료 시 복원 콜백 연결 (버튼 클릭 신호 외에 콜백 보강)
    try:
        if hasattr(buffs_frame, 'login_frame') and buffs_frame.login_frame:
            lf = buffs_frame.login_frame
            if hasattr(lf, 'login_btn'):
                lf.login_btn.clicked.connect(lambda: None)
            if hasattr(lf, 'logout_btn'):
                lf.logout_btn.clicked.connect(lambda: _set_enabled_all(central_widget, False))
    except Exception:
        pass

    # 윈도우 종료/앱 종료 훅: 언제든 종료 시 강제 로그아웃 및 잠금
    try:
        orig_close = getattr(window, 'closeEvent', None)
        def _on_close(ev):
            try:
                _force_logout_and_lock()
            finally:
                if orig_close:
                    orig_close(ev)
                else:
                    ev.accept()
        window.closeEvent = _on_close
    except Exception:
        pass

    try:
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(_force_logout_and_lock)
    except Exception:
        pass

    # atexit / signal 핸들러 등록 (최후 보루)
    try:
        import atexit, signal
        atexit.register(_force_logout_and_lock)
        atexit.register(lambda: training_fun.stop_mon_watch())
        def _sig_handler(sig, frame):
            try:
                _force_logout_and_lock()
            finally:
                os._exit(0)
        for s in (getattr(signal, 'SIGINT', None), getattr(signal, 'SIGTERM', None), getattr(signal, 'SIGBREAK', None)):
            if s is not None:
                try:
                    signal.signal(s, _sig_handler)
                except Exception:
                    pass
    except Exception:
        pass


    return window


if __name__ == '__main__':
    from PyQt5.QtCore import QCoreApplication
    try:
        QCoreApplication.addLibraryPath(qt_plugin_path)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("Kakaotalk")
    icon_path = os.path.join('imgs', 'icon', 'no.ico')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    # DB 하트비트 시작 (GUI와 분리)
    try:
        from database import start_heartbeat
        start_heartbeat()
    except Exception:
        pass
    window = create_main_window()
    window.show()
    rc = app.exec_()
    try:
        from database import stop_heartbeat
        stop_heartbeat()
    except Exception:
        pass
    try:
        training_fun.stop_mon_watch()
    except Exception:
        pass
    sys.exit(rc)
