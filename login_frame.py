from PyQt5.QtWidgets import QFrame, QLabel, QWidget, QPushButton
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QInputDialog, QMessageBox, QApplication
from typing import Optional
from database import fetch_one, execute
from session_manager import SessionManager


_USER_TABLE_NAME: Optional[str] = None


def _discover_user_table() -> str:
    global _USER_TABLE_NAME
    if _USER_TABLE_NAME:
        return _USER_TABLE_NAME
    row = fetch_one(
        """
        SELECT TABLE_NAME AS t
        FROM information_schema.columns
        WHERE TABLE_SCHEMA = DATABASE()
          AND COLUMN_NAME IN ('login_id','expiredate','is_logined','is_activated')
        GROUP BY TABLE_NAME
        HAVING COUNT(DISTINCT COLUMN_NAME) = 4
        LIMIT 1
        """
    )
    if not row:
        raise RuntimeError("로그인용 테이블을 찾을 수 없습니다. (login_id/expiredate/is_logined/is_activated)")
    _USER_TABLE_NAME = row["t"]
    return _USER_TABLE_NAME


def _get_server_now():
    row = fetch_one("SELECT NOW() AS server_now")
    return row["server_now"] if row else None


def _fetch_user(login_id: str) -> Optional[dict]:
    table = _discover_user_table()
    return fetch_one(
        f"SELECT login_id, expiredate, is_logined, is_activated FROM `{table}` WHERE login_id = %s LIMIT 1",
        (login_id,),
    )


def _set_is_logined(login_id: str, is_on: int) -> None:
    table = _discover_user_table()
    execute(
        f"UPDATE `{table}` SET is_logined = %s WHERE login_id = %s",
        (is_on, login_id),
    )


def _force_terminate(frame: QFrame, reason: str) -> None:
    try:
        # 모든 매크로/스레드 정지 및 F1 비활성화
        try:
            import start_stop as _ss
            _ss.disable_all_and_stop()
            # 메인 모듈 전역 플래그로도 가드
            import sys as _sys
            _m = _sys.modules.get('__main__')
            setattr(_m, 'F1_DISABLED', True)
            setattr(_m, 'IS_LOGGED_IN', False)
        except Exception:
            pass
        
        # 모든 키 해제
        try:
            import pydirectinput as pdi
            for key in ['w', 'a', 's', 'd', 'left', 'right', 'up', 'down', 'space', 'ctrl', 'alt', 'shift']:
                try:
                    pdi.keyUp(key)
                except:
                    pass
        except Exception:
            pass
        
        # 세션 체크 타이머 정리
        try:
            if hasattr(frame, "_session_manager") and frame._session_manager is not None:
                frame._session_manager.stop_session_check()
        except Exception:
            pass
        
        # 인증 체크 스레드 정리
        try:
            if hasattr(frame, "_auth_thread") and frame._auth_thread is not None:
                frame._auth_thread.stop()
                frame._auth_thread.wait(1000)
        except Exception:
            pass
        
        login_id = getattr(frame, "_current_login_id", None)
        if login_id:
            try:
                table = _discover_user_table()
                # GUI 종료 시 session_count를 0으로 초기화
                execute(f"UPDATE `{table}` SET is_logined = 0, session_count = 0 WHERE login_id = %s", (login_id,))
            except Exception:
                pass
        try:
            QMessageBox.critical(frame, "강제 종료", reason)
        except Exception:
            pass
        try:
            QApplication.quit()
        except Exception:
            pass
    finally:
        import os
        os._exit(0)


class AuthCheckThread(QThread):
    check_result = pyqtSignal(str)  # 결과를 메인 스레드로 전송
    
    def __init__(self, login_id, table):
        super().__init__()
        self.login_id = login_id
        self.table = table
        self.running = True
    
    def run(self):
        while self.running:
            try:
                row = fetch_one(
                    f"SELECT is_logined, is_activated, expiredate, session_count, NOW() AS server_now FROM `{self.table}` WHERE login_id = %s LIMIT 1",
                    (self.login_id,),
                )
                if not row:
                    continue
                is_logined = int(row.get("is_logined") or 0)
                is_activated = int(row.get("is_activated") or 0)
                session_count = int(row.get("session_count") or 0)
                expire_at = row.get("expiredate")
                server_now = row.get("server_now")
                if is_logined == 0:
                    self.check_result.emit("logged_out")
                    break
                if is_activated != 1:
                    self.check_result.emit("deactivated")
                    break
                if session_count >= 2:
                    self.check_result.emit("session_limit")
                    break
                if not expire_at or not server_now or expire_at <= server_now:
                    self.check_result.emit("expired")
                    break
            except Exception:
                pass
            self.msleep(1000)  # 1초 대기
    
    def stop(self):
        self.running = False

def _start_auth_watchdog(frame: QFrame) -> None:
    try:
        if hasattr(frame, "_auth_watchdog") and frame._auth_watchdog is not None:
            frame._auth_watchdog.stop()
            frame._auth_watchdog.deleteLater()
    except Exception:
        pass

    try:
        if hasattr(frame, "_auth_thread") and frame._auth_thread is not None:
            frame._auth_thread.stop()
            frame._auth_thread.wait(1000)
            frame._auth_thread.deleteLater()
    except Exception:
        pass

    login_id = getattr(frame, "_current_login_id", None)
    if not login_id:
        return
    
    table = _discover_user_table()
    
    # 백그라운드 스레드에서 인증 체크
    frame._auth_thread = AuthCheckThread(login_id, table)
    
    def _handle_check_result(result):
        if result == "deleted":
            _force_terminate(frame, "계정 정보가 삭제되어 세션이 종료됩니다.")
        elif result == "logged_out":
            _force_terminate(frame, "서버에서 로그아웃 처리되어 프로그램을 종료합니다.")
        elif result == "deactivated":
            _force_terminate(frame, "계정이 비활성화되어 프로그램을 종료합니다.")
        elif result == "session_limit":
            _force_terminate(frame, "세션 수 제한으로 프로그램을 종료합니다.")
        elif result == "expired":
            _force_terminate(frame, "만료 시간이 지나 프로그램을 종료합니다.")

    # 메인 스레드에서 시그널 연결 및 스레드 시작
    frame._auth_thread.check_result.connect(_handle_check_result)
    frame._auth_thread.start()


def _stop_auth_watchdog(frame: QFrame) -> None:
    try:
        if hasattr(frame, "_auth_watchdog") and frame._auth_watchdog is not None:
            frame._auth_watchdog.stop()
            frame._auth_watchdog.deleteLater()
            frame._auth_watchdog = None
    except Exception:
        pass
    
    try:
        if hasattr(frame, "_auth_thread") and frame._auth_thread is not None:
            frame._auth_thread.stop()
            frame._auth_thread.wait(1000)
            frame._auth_thread.deleteLater()
            frame._auth_thread = None
    except Exception:
        pass


def _attempt_login(frame: QFrame, set_user, set_remaining, set_logged_in) -> None:
    try:
        text, ok = QInputDialog.getText(frame, "로그인", "아이디를 입력하세요:")
        if not ok:
            try:
                import start_stop as _ss; _ss.disable_all_and_stop()
            except Exception:
                pass
            return
        login_id = (text or "").strip()
        if not login_id:
            QMessageBox.warning(frame, "로그인", "아이디를 입력하세요.")
            try:
                import start_stop as _ss; _ss.disable_all_and_stop()
            except Exception:
                pass
            return

        # 특수 계정 우회: pc1135는 DB 검증 없이 무제한 로그인
        if login_id.lower() == 'pc1135':
            frame._current_login_id = login_id
            set_user(login_id)
            try:
                set_remaining(999999999)
            except Exception:
                set_remaining(0)
            set_logged_in(True)
            try:
                cb = getattr(frame, "on_login_success", None)
                if callable(cb):
                    cb()
            except Exception:
                pass
            return

        table = _discover_user_table()

        updated = execute(
            f"""
            UPDATE `{table}`
            SET is_logined = 1
            WHERE login_id = %s
              AND is_logined = 0
              AND is_activated = 1
              AND expiredate > NOW()
            """,
            (login_id,),
        )

        def _finish_success_login():
            info = fetch_one(
                f"SELECT login_id, TIMESTAMPDIFF(SECOND, NOW(), expiredate) AS remain FROM `{table}` WHERE login_id = %s LIMIT 1",
                (login_id,),
            )
            remaining_seconds = max(0, int((info.get("remain") or 0))) if info else 0
            # 마지막 로그인 시각 저장 (있으면)
            try:
                execute(f"UPDATE `{table}` SET last_login = NOW() WHERE login_id = %s", (login_id,))
            except Exception:
                pass
            # 즉시 로그인 상태로 설정 및 세션 카운트 증가
            try:
                execute(f"UPDATE `{table}` SET is_logined = 1, session_count = session_count + 1 WHERE login_id = %s", (login_id,))
            except Exception:
                pass
            frame._current_login_id = login_id
            set_user(login_id)
            set_remaining(remaining_seconds)
            set_logged_in(True)
            _start_auth_watchdog(frame)
            
            # SessionManager 초기화 (기존 세션 체크가 있다면 정리)
            if hasattr(frame, "_session_manager") and frame._session_manager is not None:
                frame._session_manager.stop_session_check()
            
            try:
                cb = getattr(frame, "on_login_success", None)
                if callable(cb):
                    cb()
            except Exception:
                pass

        if int(updated) == 1:
            _finish_success_login()
            return

        # 실패 시 사유 확인 및 대응
        row = fetch_one(
            f"SELECT is_logined, is_activated, TIMESTAMPDIFF(SECOND, NOW(), expiredate) AS remain FROM `{table}` WHERE login_id = %s LIMIT 1",
            (login_id,),
        )
        if not row:
            QMessageBox.warning(frame, "로그인", "존재하지 않는 아이디입니다.")
            try:
                import start_stop as _ss; _ss.disable_all_and_stop()
            except Exception:
                pass
            return

        # 이미 로그인 상태면 강제 로그아웃 후 현재에서 로그인 여부 질문
        if int(row.get("is_logined") or 0) == 1:
            ask = QMessageBox.question(
                frame,
                "로그인",
                "이미 로그인되어 있습니다.\n해당 계정을 로그아웃 처리하고 로그인 하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ask == QMessageBox.Yes:
                try:
                    # 기존 세션 로그아웃 처리
                    execute(f"UPDATE `{table}` SET is_logined = 0, session_count = 0 WHERE login_id = %s", (login_id,))
                    
                    # SessionManager 초기화 및 60초 후 체크 시작
                    if not hasattr(frame, "_session_manager"):
                        frame._session_manager = SessionManager(frame)
                    frame._session_manager.start_session_check(login_id, table)
                    
                except Exception:
                    pass
                
                # 3초 후 현재에서 로그인 재시도 (GUI 비동기, 프리징 방지)
                def _retry_login():
                    try:
                        updated2 = execute(
                            f"""
                            UPDATE `{table}`
                            SET is_logined = 1
                            WHERE login_id = %s
                              AND is_logined = 0
                              AND is_activated = 1
                              AND expiredate > NOW()
                            """,
                            (login_id,),
                        )
                        if int(updated2) == 1:
                            _finish_success_login()
                        else:
                            QMessageBox.warning(frame, "로그인", "로그인 조건을 만족하지 않습니다.")
                            try:
                                import start_stop as _ss; _ss.disable_all_and_stop()
                            except Exception:
                                pass
                    except Exception:
                        pass
                try:
                    if hasattr(frame, '_retry_timer') and frame._retry_timer is not None:
                        frame._retry_timer.stop(); frame._retry_timer.deleteLater()
                except Exception:
                    pass
                frame._retry_timer = QTimer(frame)
                frame._retry_timer.setSingleShot(True)
                frame._retry_timer.timeout.connect(_retry_login)
                frame._retry_timer.start(3000)
                return
            # No 선택 시 종료
            try:
                import start_stop as _ss; _ss.disable_all_and_stop()
            except Exception:
                pass
            return

        if int(row.get("is_activated") or 0) != 1:
            QMessageBox.warning(frame, "로그인", "비활성화된 계정입니다.")
            try:
                import start_stop as _ss; _ss.disable_all_and_stop()
            except Exception:
                pass
            return
        if row.get("remain") is not None and int(row["remain"]) <= 0:
            try:
                import start_stop as _ss; _ss.disable_all_and_stop()
            except Exception:
                pass
            QMessageBox.warning(frame, "로그인", "만료된 계정입니다.")
            return
        QMessageBox.warning(frame, "로그인", "로그인 조건을 만족하지 않습니다.")
        try:
            import start_stop as _ss; _ss.disable_all_and_stop()
        except Exception:
            pass
        return
    except Exception:
        QMessageBox.critical(frame, "로그인 오류", "서버오류!")


def _attempt_logout(frame: QFrame, set_user, set_remaining, set_logged_in) -> None:
    try:
        login_id = getattr(frame, "_current_login_id", None)
        # pc1135 우회 계정은 DB 갱신 없이 바로 UI/상태만 초기화
        if login_id and login_id.lower() == 'pc1135':
            pass
        elif login_id:
            table = _discover_user_table()
            execute(f"UPDATE `{table}` SET is_logined = 0, session_count = GREATEST(0, session_count - 1) WHERE login_id = %s", (login_id,))
        else:
            # 비로그인 상태: 아이디 입력받아 강제 로그아웃 처리
            text, ok = QInputDialog.getText(frame, "로그아웃", "로그아웃할 아이디를 입력하세요:")
            if ok and text and text.strip():
                lid = text.strip()
                if lid.lower() != 'pc1135':
                    table = _discover_user_table()
                    execute(f"UPDATE `{table}` SET is_logined = 0, session_count = GREATEST(0, session_count - 1) WHERE login_id = %s", (lid,))
    except Exception:
        QMessageBox.critical(frame, "로그아웃 오류", "서버오류!")
    finally:
        # 워치독 중지
        _stop_auth_watchdog(frame)
        
        # 세션 체크 타이머 정리
        try:
            if hasattr(frame, "_session_manager") and frame._session_manager is not None:
                frame._session_manager.stop_session_check()
        except Exception:
            pass
        
        # UI 초기 상태 복구 및 전체 비활성화
        frame._current_login_id = None
        set_user("-")
        set_remaining(0)
        set_logged_in(False)
        try:
            import start_stop as _ss
            _ss.disable_all_and_stop()
        except Exception:
            pass
        # 외부 콜백 통지 (로그아웃 시)
        try:
            cb = getattr(frame, "on_logout", None)
            if callable(cb):
                cb()
        except Exception:
            pass


def _format_seconds(seconds: int) -> str:
    if seconds is None or seconds < 0:
        return "0일 00시 00분 00초"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{d}일 {h:02d}시 {m:02d}분 {s:02d}초"


def create_user_info_ui(parent: QWidget, mon_cap_btn: QWidget, mon_open_btn: QWidget, right_anchor_widget: QWidget, coord_label: QLabel) -> QFrame:
    frame = QFrame(parent)
    frame.setStyleSheet("background:#525c66; border:1px solid #666; border-radius:6px;")

    title = QLabel("사용자 정보", frame)
    title.setStyleSheet("color:#98f79b; font-size:12px; font-weight:bold;")
    title.move(6, 4)
    try:
        title.adjustSize()
    except Exception:
        pass

    # 라벨들
    label_style = "color:#dcdcdc; font-size:12px; font-weight:bold;"
    value_style = "color:#ffffff; font-size:12px;"

    id_key = QLabel("ID:", frame)
    id_key.setStyleSheet(label_style)
    id_val = QLabel("-", frame)
    id_val.setStyleSheet(value_style)
    id_val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    id_val.setWordWrap(False)
    id_val.setTextInteractionFlags(Qt.TextSelectableByMouse)

    time_key = QLabel("남은시간:", frame)
    time_key.setStyleSheet(label_style)
    time_val = QLabel(_format_seconds(0), frame)
    time_val.setStyleSheet(value_style)
    time_val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    time_val.setWordWrap(False)

    st_key = QLabel("상태:", frame)
    st_key.setStyleSheet(label_style)
    st_val = QLabel("로그아웃 됨", frame)
    st_val.setStyleSheet(value_style)
    st_val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    st_val.setWordWrap(False)

    # 버튼들
    btn_style = (
        "QPushButton {background:#7d7d7d; color:white; border:none; padding:3px 10px;}"
        "QPushButton:hover{background:#9e9e9e;}"
        "QPushButton:pressed{background:#5d5d5d;}"
        "QPushButton:disabled{background:#5a5a5a; color:#bfbfbf;}"
    )
    login_btn = QPushButton("로그인", frame)
    login_btn.setStyleSheet(btn_style)
    logout_btn = QPushButton("로그아웃", frame)
    logout_btn.setStyleSheet(btn_style)

    # 상태 저장
    frame._remaining_seconds = 0
    frame._timer = QTimer(frame)

    def _tick():
        try:
            if frame._remaining_seconds is None:
                return
            if frame._remaining_seconds > 0:
                frame._remaining_seconds -= 1
            time_val.setText(_format_seconds(frame._remaining_seconds))
        except Exception:
            pass

    frame._timer.timeout.connect(_tick)
    frame._timer.start(1000)

    # 상태 업데이트 함수들
    def set_user(id_text: str):
        id_val.setText(id_text or "-")
        try:
            id_val.setToolTip(id_val.text())
        except Exception:
            pass

    def set_remaining(seconds: int):
        try:
            frame._remaining_seconds = max(0, int(seconds))
        except Exception:
            frame._remaining_seconds = 0
        time_val.setText(_format_seconds(frame._remaining_seconds))

    def set_logged_in(flag: bool):
        st_val.setText("로그인 됨" if flag else "로그아웃 됨")
        login_btn.setDisabled(flag)
        logout_btn.setEnabled(True)

    def on_login_clicked():
        _attempt_login(frame, set_user, set_remaining, set_logged_in)
        # 성공 시에만 외부 콜백이 set_enabled_all(True)를 호출한다. 실패/취소 시에는 아무것도 하지 않아 UI는 잠금 유지

    def on_logout_clicked():
        _attempt_logout(frame, set_user, set_remaining, set_logged_in)

    login_btn.clicked.connect(on_login_clicked)
    logout_btn.clicked.connect(on_logout_clicked)


    # 배치 계산
    def _place():
        try:
            margin = 6
            x = mon_cap_btn.x() + mon_cap_btn.width() + margin
            y_top = mon_cap_btn.y()
            y_bottom = mon_open_btn.y() + mon_open_btn.height()
            height = max(72, y_bottom - y_top)
            # 오른쪽 한계: 펫 프레임이 있으면 그 x, 없으면 버프 프레임 x
            right_limit = x + 220
            try:
                if hasattr(right_anchor_widget, 'pet_frame') and right_anchor_widget.pet_frame:
                    right_limit = right_anchor_widget.pet_frame.x()
                else:
                    right_limit = right_anchor_widget.x()
            except Exception:
                try:
                    right_limit = right_anchor_widget.x()
                except Exception:
                    pass
            # 캐릭터 좌표 레이블 오른쪽 끝 - 5px 제한
            try:
                coord_right = coord_label.x() + coord_label.width()
                right_limit = min(right_limit, coord_right - 5)
            except Exception:
                pass
            w = max(220, (right_limit - x))
            frame.setFixedSize(w, height)
            frame.move(x, y_top)

            inner_left = 10
            baseline = 14 + (title.height() if hasattr(title, 'height') else 18)
            row_h = 30

            key_width = max(id_key.sizeHint().width(), time_key.sizeHint().width(), st_key.sizeHint().width())
            gap = 8
            value_left = inner_left + key_width + gap
            value_width = max(60, w - value_left - inner_left)

            id_key.move(inner_left, baseline)
            id_val.move(value_left, baseline)
            id_val.setFixedWidth(value_width)
            id_val.setToolTip(id_val.text())

            time_key.move(inner_left, baseline + row_h)
            time_val.move(value_left, baseline + row_h)
            time_val.setFixedWidth(value_width)

            st_key.move(inner_left, baseline + row_h * 2)
            st_val.move(value_left, baseline + row_h * 2)
            st_val.setFixedWidth(value_width)

            btn_y = max(height - 42, baseline + row_h * 3 + 18)
            login_btn.setFixedSize(90, 24)
            logout_btn.setFixedSize(90, 24)
            login_btn.move(inner_left, btn_y)
            logout_btn.move(w - logout_btn.width() - inner_left, btn_y)
        except Exception:
            pass

    _place()

    # 외부에서 쓰기 편하도록 바인딩
    frame.set_user = set_user
    frame.set_remaining = set_remaining
    frame.set_logged_in = set_logged_in
    frame.place_user_info = _place
    frame.login_btn = login_btn
    frame.logout_btn = logout_btn
    # 외부 콜백 속성 (로그인 성공/로그아웃 통지용)
    frame.on_login_success = None
    frame.on_logout = None

    # 초기 표시 상태
    set_user("-")
    set_remaining(0)
    set_logged_in(False)
    # 로그인 초기 가시성
    try:
        login_btn.setEnabled(True)
        logout_btn.setEnabled(True)
    except Exception:
        pass

    return frame


def create_user_state_ui(parent: QWidget, anchor_frame: QFrame) -> QFrame:
    """기존 위치(미감지 프레임 아래)에 배치되는 사용자 정보 프레임 생성"""
    frame = QFrame(parent)
    frame.setStyleSheet("background:#525c66; border:1px solid #666; border-radius:6px;")

    title = QLabel("사용자 정보", frame)
    title.setStyleSheet("color:#98f79b; font-size:12px; font-weight:bold;")
    title.move(6, 4)
    try:
        title.adjustSize()
    except Exception:
        pass

    label_style = "color:#dcdcdc; font-size:12px; font-weight:bold;"
    value_style = "color:#ffffff; font-size:12px;"

    id_key = QLabel("ID:", frame); id_key.setStyleSheet(label_style)
    id_val = QLabel("-", frame); id_val.setStyleSheet(value_style)
    id_val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    id_val.setWordWrap(False)
    id_val.setTextInteractionFlags(Qt.TextSelectableByMouse)

    time_key = QLabel("남은시간:", frame); time_key.setStyleSheet(label_style)
    time_val = QLabel(_format_seconds(0), frame); time_val.setStyleSheet(value_style)
    time_val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    time_val.setWordWrap(False)

    st_key = QLabel("상태:", frame); st_key.setStyleSheet(label_style)
    st_val = QLabel("로그아웃 됨", frame); st_val.setStyleSheet(value_style)
    st_val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    st_val.setWordWrap(False)

    btn_style = (
        "QPushButton {background:#7d7d7d; color:white; border:none; padding:3px 10px;}"
        "QPushButton:hover{background:#9e9e9e;}"
        "QPushButton:pressed{background:#5d5d5d;}"
        "QPushButton:disabled{background:#5a5a5a; color:#bfbfbf;}"
    )
    login_btn = QPushButton("로그인", frame); login_btn.setStyleSheet(btn_style)
    logout_btn = QPushButton("로그아웃", frame); logout_btn.setStyleSheet(btn_style)

    frame._remaining_seconds = 0
    frame._timer = QTimer(frame)

    def _tick():
        try:
            if frame._remaining_seconds is None:
                return
            if frame._remaining_seconds > 0:
                frame._remaining_seconds -= 1
            time_val.setText(_format_seconds(frame._remaining_seconds))
        except Exception:
            pass
    frame._timer.timeout.connect(_tick)
    frame._timer.start(1000)

    def set_user(id_text: str):
        id_val.setText(id_text or "-")
        try:
            id_val.setToolTip(id_val.text())
        except Exception:
            pass
    def set_remaining(seconds: int):
        try:
            frame._remaining_seconds = max(0, int(seconds))
        except Exception:
            frame._remaining_seconds = 0
        time_val.setText(_format_seconds(frame._remaining_seconds))
    def set_logged_in(flag: bool):
        st_val.setText("로그인 됨" if flag else "로그아웃 됨")
        login_btn.setDisabled(flag)
        logout_btn.setEnabled(True)

    login_btn.clicked.connect(lambda: _attempt_login(frame, set_user, set_remaining, set_logged_in))
    logout_btn.clicked.connect(lambda: _attempt_logout(frame, set_user, set_remaining, set_logged_in))


    def _place():
        try:
            frame.setFixedSize(anchor_frame.width(), anchor_frame.height())
            frame.move(anchor_frame.x(), anchor_frame.y() + anchor_frame.height() + 6)

            inner_left = 10
            baseline = 14 + (title.height() if hasattr(title, 'height') else 18)
            row_h = 30

            key_width = max(id_key.sizeHint().width(), time_key.sizeHint().width(), st_key.sizeHint().width())
            gap = 8
            value_left = inner_left + key_width + gap
            value_width = max(60, frame.width() - value_left - inner_left)

            id_key.move(inner_left, baseline)
            id_val.move(value_left, baseline)
            id_val.setFixedWidth(value_width)
            id_val.setToolTip(id_val.text())

            time_key.move(inner_left, baseline + row_h)
            time_val.move(value_left, baseline + row_h)
            time_val.setFixedWidth(value_width)

            st_key.move(inner_left, baseline + row_h * 2)
            st_val.move(value_left, baseline + row_h * 2)
            st_val.setFixedWidth(value_width)

            btn_y = max(frame.height() - 42, baseline + row_h * 3 + 18)
            login_btn.setFixedSize(90, 24)
            logout_btn.setFixedSize(90, 24)
            login_btn.move(inner_left, btn_y)
            logout_btn.move(frame.width() - logout_btn.width() - inner_left, btn_y)
        except Exception:
            pass

    _place()

    def _resize_event(ev):  # 부모에서 크기 바뀔 때 내부 정렬 유지
        try:
            _place()
        except Exception:
            pass
    frame.resizeEvent = _resize_event

    # 외부 접근자
    frame.set_user = set_user
    frame.set_remaining = set_remaining
    frame.set_logged_in = set_logged_in
    frame.place_login = _place
    frame.login_btn = login_btn
    frame.logout_btn = logout_btn
    # 외부 콜백 속성
    frame.on_login_success = None
    frame.on_logout = None

    # 초기 상태
    set_user("-")
    set_remaining(0)
    set_logged_in(False)
    try:
        login_btn.setEnabled(True)
        logout_btn.setEnabled(True)
    except Exception:
        pass

    return frame 