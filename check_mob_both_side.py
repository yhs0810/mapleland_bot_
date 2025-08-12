from typing import Tuple

def is_both_active(no_turn_enabled: bool, both_side_enabled: bool) -> bool:
    """방향전환X와 양방향감지가 모두 활성일 때만 True"""
    return bool(no_turn_enabled and both_side_enabled)


def adjust_detection_window(dx_lmin: int, dx_rmax: int) -> Tuple[int, int]:
    """양방향 감지 시, 좌우 모두를 감지하도록 좌/우 전체 범위를 반환.
    기존 좌측 최소~우측 최대 범위를 그대로 사용한다.
    """
    return dx_lmin, dx_rmax
