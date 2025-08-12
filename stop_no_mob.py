from PyQt5.QtWidgets import QCheckBox, QWidget
import time
from typing import Optional

# 내부 상태: "몹 미감지로 인한 이동정지" 활성화 여부
_paused_by_no_mob = False


def create_checkbox(parent: QWidget) -> QCheckBox:
    chk = QCheckBox("몹 미감지시 방향키 해제", parent)
    chk.setStyleSheet("QCheckBox {color:#dcdcdc; font-size:9px;}")
    chk.setChecked(False)
    return chk


def update_pause_state(enabled: bool, in_box: Optional[bool]):
    """몹 미감지시 이동 정지/해제를 처리.
    - enabled: 체크박스 상태
    - in_box: True=공격범위 내 몹 존재, False=없음, None=판단 불가(경계/억제 등) -> 해제 우선
    """
    global _paused_by_no_mob
    try:
        import start_stop as _ss
    except Exception:
        return

    now = time.time()

    # 기능 비활성화 시 즉시 해제
    if not enabled:
        if _paused_by_no_mob or getattr(_ss, 'STOP_MOVE_UNTIL', 0.0) > 0.0:
            _ss.STOP_MOVE_UNTIL = 0.0
            _ss.STOP_REQUEST_RELEASE = False
        _paused_by_no_mob = False
        return

    # 판정 불가 상황(경계/억제 등)에서는 잠금 해제하여 경계 복귀 로직이 동작하도록 함
    if in_box is None:
        if _paused_by_no_mob or getattr(_ss, 'STOP_MOVE_UNTIL', 0.0) > 0.0:
            _ss.STOP_MOVE_UNTIL = 0.0
            _ss.STOP_REQUEST_RELEASE = False
        _paused_by_no_mob = False
        return

    # 몹이 공격범위에 없음 → 이동 정지 유지/연장
    if in_box is False:
        # 최초 진입 시 현재 방향 저장 후 즉시 업 요청
        if getattr(_ss, 'STOP_MOVE_UNTIL', 0.0) <= now:
            _ss.STOP_SAVED_DIR = _ss.current_key if getattr(_ss, 'current_key', None) in ('left', 'right') else None
            _ss.STOP_REQUEST_RELEASE = True
        # 주기적으로 연장하여 지속 정지
        _ss.STOP_MOVE_UNTIL = now + 0.40
        _paused_by_no_mob = True
        return

    # 몹이 공격범위에 있음(True) → 이동 정지 해제
    if _paused_by_no_mob:
        _ss.STOP_MOVE_UNTIL = 0.0
        _ss.STOP_REQUEST_RELEASE = False
        _paused_by_no_mob = False
