from PyQt5.QtWidgets import QPushButton, QWidget
from PyQt5.QtCore import Qt

# 미니맵 차단영역 편집 오버레이
class _BlockOverlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # 로컬/글로벌 좌표 모두 유지
        self.start_local = None
        self.end_local = None
        self.start_global = None
        self.end_global = None
        self.is_dragging = False

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QColor, QPen
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0,0,0,40))
        if self.start_local and self.end_local:
            x = min(self.start_local.x(), self.end_local.x())
            y = min(self.start_local.y(), self.end_local.y())
            w = abs(self.end_local.x() - self.start_local.x())
            h = abs(self.end_local.y() - self.start_local.y())
            painter.setPen(QPen(QColor(255,0,255), 2))
            painter.drawRect(x, y, w, h)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.start_local = ev.pos(); self.end_local = ev.pos()
            self.start_global = ev.globalPos(); self.end_global = ev.globalPos()
            self.is_dragging = True; self.update()

    def mouseMoveEvent(self, ev):
        if self.is_dragging:
            self.end_local = ev.pos(); self.end_global = ev.globalPos(); self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.is_dragging:
            self.end_local = ev.pos(); self.end_global = ev.globalPos(); self.is_dragging = False; self.update()
            # 전역 좌표 → 미니맵 캔버스(300x150) 기준으로 변환해 저장
            try:
                import minimap
                if hasattr(minimap, 'canvas_widget') and minimap.canvas_widget:
                    cw = minimap.canvas_widget
                    # 캔버스의 전역 좌표/크기
                    gtl = cw.mapToGlobal(cw.rect().topLeft())
                    gx = gtl.x(); gy = gtl.y()
                    gw = cw.width(); gh = cw.height()
                    x0g = min(self.start_global.x(), self.end_global.x())
                    y0g = min(self.start_global.y(), self.end_global.y())
                    w = abs(self.end_global.x() - self.start_global.x())
                    h = abs(self.end_global.y() - self.start_global.y())
                    # 전역 → 캔버스 상대 좌표
                    rx0 = x0g - gx; ry0 = y0g - gy
                    # 캔버스 범위 클리핑
                    rx0 = max(0, min(gw, rx0)); ry0 = max(0, min(gh, ry0))
                    rw = max(0, min(gw - rx0, w))
                    rh = max(0, min(gh - ry0, h))
                    # 저장
                    if rw > 0 and rh > 0:
                        minimap.RED_BLOCKS.append((int(rx0), int(ry0), int(rw), int(rh)))
                        try:
                            cw.update()
                        except Exception:
                            pass
            except Exception:
                pass
            self.close()


def create_minimap_edit_button(parent_widget: QWidget, anchor_btn: QPushButton) -> QPushButton:
    """창고정 버튼(anchor_btn) 오른쪽에 '미니맵수정' 버튼 생성. 클릭 시 드래그로 차단영역 추가"""
    btn = QPushButton("미니맵수정", parent_widget)
    btn.setFixedSize(80, 28)
    btn.setStyleSheet(
        "QPushButton {background:#2980b9; color:white; border:none; font-size:10px;} "
        "QPushButton:hover{background:#5dade2;} "
        "QPushButton:pressed{background:#1f618d;}"
    )

    # 초기화 버튼
    reset_btn = QPushButton("미니맵수정 초기화", parent_widget)
    reset_btn.setFixedSize(110, 28)
    reset_btn.setStyleSheet(
        "QPushButton {background:#7f8c8d; color:white; border:none; font-size:10px;} "
        "QPushButton:hover{background:#95a5a6;} "
        "QPushButton:pressed{background:#566573;}"
    )

    def _place():
        try:
            x = anchor_btn.x() + anchor_btn.width() + 5
            y = anchor_btn.y()
            btn.move(x, y)
            reset_btn.move(btn.x() + btn.width() + 5, y)
        except Exception:
            pass

    _place()
    try:
        # 위치 유지: anchor/parent 리사이즈 시 재배치
        from PyQt5.QtCore import QObject, QEvent
        class _Filter(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
                    _place()
                return False
        f = _Filter()
        parent_widget.installEventFilter(f)
        anchor_btn.installEventFilter(f)
        btn._pl = f; reset_btn._pl = f
    except Exception:
        pass

    def _on_click():
        # 미니맵 캡처 영역이 지정되어 있거나, 이미 캔버스 텍스처가 표시 중일 때만 작동
        try:
            import minimap
            cw = getattr(minimap, 'canvas_widget', None)
            if not cw:
                return
        except Exception:
            return
        # 전체 화면 오버레이
        ov = _BlockOverlay()
        try:
            from PyQt5.QtWidgets import QApplication
            desk_geo = QApplication.desktop().geometry()  # 가상 데스크톱 전체
            ov.setGeometry(desk_geo)
            ov.show()
        except Exception:
            ov.setGeometry(0, 0, parent_widget.width(), parent_widget.height())
            ov.show()
        ov.raise_(); ov.activateWindow(); ov.setFocus()
        # 전역 참조 유지 (GC 방지)
        try:
            import minimap as _mm
            refs = getattr(_mm, '_overlay_refs', None)
            if refs is None:
                refs = []
                setattr(_mm, '_overlay_refs', refs)
            refs.append(ov)
            try:
                ov.destroyed.connect(lambda *_: refs.remove(ov) if ov in refs else None)
            except Exception:
                pass
        except Exception:
            pass

    def _on_reset():
        try:
            import minimap
            minimap.RED_BLOCKS = []
            cw = getattr(minimap, 'canvas_widget', None)
            if cw:
                try: cw.update()
                except Exception: pass
        except Exception:
            pass

    btn.clicked.connect(_on_click)
    reset_btn.clicked.connect(_on_reset)
    return btn
