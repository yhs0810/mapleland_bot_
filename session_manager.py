from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox, QFrame
from database import fetch_one, execute
from typing import Optional


class SessionManager:
    def __init__(self, frame: QFrame):
        self.frame = frame
        self.session_check_timer: Optional[QTimer] = None
        self.login_id: Optional[str] = None
        
    def start_session_check(self, login_id: str, table_name: str) -> None:
        """60초 후 이전 세션 체크 타이머 시작"""
        self.login_id = login_id
        self.table_name = table_name
        
        # 기존 타이머 정리
        self.stop_session_check()
        
        def _check_previous_session():
            try:
                # 60초 후 다시 체크 (force_log_out 포함)
                check_row = fetch_one(
                    f"SELECT is_logined, force_log_out FROM `{self.table_name}` WHERE login_id = %s LIMIT 1",
                    (self.login_id,),
                )
                if check_row:
                    is_logined = int(check_row.get("is_logined") or 0)
                    force_log_out = int(check_row.get("force_log_out") or 0)
                    
                    if is_logined == 0 or force_log_out == 1:
                        # 이전 세션이 로그아웃되었거나 강제 로그아웃 플래그가 설정된 경우
                        reason = "강제 로그아웃이 요청되어 프로그램을 종료합니다." if force_log_out == 1 else "이전 세션이 종료되어 프로그램을 종료합니다."
                        self._force_terminate(reason)
            except Exception:
                pass
        
        # 60초 후 체크 타이머 시작
        self.session_check_timer = QTimer(self.frame)
        self.session_check_timer.setInterval(60000)  # 60초
        self.session_check_timer.timeout.connect(_check_previous_session)
        self.session_check_timer.start()
        
    def stop_session_check(self) -> None:
        """세션 체크 타이머 정리"""
        try:
            if self.session_check_timer is not None:
                self.session_check_timer.stop()
                self.session_check_timer.deleteLater()
                self.session_check_timer = None
        except Exception:
            pass
            
    def _force_terminate(self, reason: str) -> None:
        """강제 종료 처리"""
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
            self.stop_session_check()
            
            if self.login_id:
                try:
                    # GUI 종료 시 session_count를 0으로 초기화
                    execute(f"UPDATE `{self.table_name}` SET is_logined = 0, session_count = 0 WHERE login_id = %s", (self.login_id,))
                except Exception:
                    pass
                    
            try:
                QMessageBox.critical(self.frame, "강제 종료", reason)
            except Exception:
                pass
                
            try:
                from PyQt5.QtWidgets import QApplication
                QApplication.quit()
            except Exception:
                pass
        finally:
            import os
            os._exit(0) 