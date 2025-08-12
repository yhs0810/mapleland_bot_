from __future__ import annotations

import os
import ctypes
from ctypes import wintypes
from typing import Optional

from PyQt5.QtWidgets import QWidget, QPushButton, QMessageBox
from PyQt5.QtCore import QObject, QEvent


# ===== Windows API 바인딩 =====
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

# 타입 설정
HWND = wintypes.HWND
LPARAM = wintypes.LPARAM
BOOL = wintypes.BOOL
DWORD = wintypes.DWORD
UINT = wintypes.UINT
LPWSTR = wintypes.LPWSTR

# 상수들
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


# 함수 시그니처
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM), LPARAM]
user32.EnumWindows.restype = BOOL
user32.IsWindowVisible.argtypes = [HWND]
user32.IsWindowVisible.restype = BOOL
user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(DWORD)]
user32.GetWindowThreadProcessId.restype = DWORD
user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
user32.ShowWindow.restype = BOOL
user32.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, UINT]
user32.SetWindowPos.restype = BOOL

kernel32.OpenProcess.argtypes = [DWORD, BOOL, DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = BOOL

# QueryFullProcessImageNameW (Vista+)
try:
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, DWORD, LPWSTR, ctypes.POINTER(DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = BOOL
    _HAS_QFPN = True
except Exception:
    _HAS_QFPN = False

# Psapi GetModuleFileNameExW (fallback)
psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, LPWSTR, DWORD]
psapi.GetModuleFileNameExW.restype = DWORD


def _get_process_image_path(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not handle:
            return ""
    try:
        buf_len = DWORD(1024)
        buf = ctypes.create_unicode_buffer(buf_len.value)
        ok = False
        if _HAS_QFPN:
            ok = bool(kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(buf_len)))
        if not ok:
            # fallback to psapi
            got = psapi.GetModuleFileNameExW(handle, None, buf, buf_len.value)
            ok = bool(got)
        return buf.value if ok else ""
    finally:
        kernel32.CloseHandle(handle)


def _iter_top_level_windows():
    handles = []

    @ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM)
    def _enum_cb(hwnd: int, lparam: int) -> int:
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                handles.append((hwnd, pid.value))
        except Exception:
            pass
        return True

    user32.EnumWindows(_enum_cb, 0)
    return handles


def pin_msw_to_left_top() -> bool:
    """msw.exe의 최상위 창을 찾아 화면의 가장 왼쪽-최상단으로 이동."""
    targets = []
    for hwnd, pid in _iter_top_level_windows():
        exe = _get_process_image_path(pid)
        if not exe:
            continue
        if os.path.basename(exe).lower() == "msw.exe":
            targets.append(hwnd)

    if not targets:
        return False

    # 가상 스크린 좌표
    x0 = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    y0 = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN

    moved = False
    for hwnd in targets:
        try:
            user32.ShowWindow(hwnd, SW_RESTORE)
            # 왼쪽으로 조금 더: x0 - 10, Y는 최상단 정렬
            user32.SetWindowPos(hwnd, None, int(x0 - 10), int(y0), 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW)
            moved = True
        except Exception:
            pass
    return moved


class _PlaceFilter(QObject):
    def __init__(self, place_fn):
        super().__init__()
        self._place = place_fn

    def eventFilter(self, obj, ev):
        et = ev.type()
        if et in (QEvent.Resize, QEvent.Move, QEvent.Show):
            try:
                self._place()
            except Exception:
                pass
        return False


def create_fix_msw_button(parent_widget: QWidget, anchor_btn: QPushButton) -> QPushButton:
    btn = QPushButton("창고정", parent_widget)
    btn.setFixedSize(80, 28)
    btn.setStyleSheet(
        "QPushButton {background:#8e44ad; color:white; border:none; font-size:10px;} "
        "QPushButton:hover{background:#9b59b6;} "
        "QPushButton:pressed{background:#6c3483;}"
    )

    def _place():
        try:
            x = anchor_btn.x() + anchor_btn.width() + 5
            y = anchor_btn.y()
            btn.move(x, y)
        except Exception:
            pass

    _place()

    # 이벤트 필터로 항상 앵커 옆에 유지
    try:
        pf = _PlaceFilter(_place)
        parent_widget.installEventFilter(pf)
        anchor_btn.installEventFilter(pf)
        btn._place_filter_ref = pf  # GC 방지 참조 유지
    except Exception:
        pass

    def _on_clicked():
        ok = False
        try:
            ok = pin_msw_to_left_top()
        except Exception:
            ok = False
        if not ok:
            try:
                QMessageBox.warning(parent_widget.window(), "창고정", "msw.exe 창을 찾지 못했습니다.")
            except Exception:
                pass

    btn.clicked.connect(_on_clicked)
    return btn
