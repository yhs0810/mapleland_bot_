from __future__ import annotations

import os
import configparser
from typing import Optional, Tuple
from PyQt5.QtWidgets import (
    QWidget,
    QPushButton,
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
    QMessageBox,
    QLabel,
)
from PyQt5.QtCore import Qt
import threading


CONFIG_DIR = "config"
CONFIG_PATH = os.path.join(CONFIG_DIR, "telegram_info.ini")


class TelegramConfigDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, api_key: str = "", chat_id: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("텔레그램 연동 설정")
        self.setModal(True)
        self.setFixedSize(360, 160)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.api_edit = QLineEdit(self)
        self.api_edit.setPlaceholderText("Telegram Bot API Key")
        self.api_edit.setText(api_key)
        self.chat_edit = QLineEdit(self)
        self.chat_edit.setPlaceholderText("Chat ID")
        self.chat_edit.setText(chat_id)
        form.addRow("API Key:", self.api_edit)
        form.addRow("Chat ID:", self.chat_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self) -> tuple[str, str]:
        return self.api_edit.text().strip(), self.chat_edit.text().strip()


def _load_existing() -> tuple[str, str]:
    if not os.path.isfile(CONFIG_PATH):
        return "", ""
    cfg = configparser.ConfigParser()
    try:
        # 엄격 모드 완화: 잘못된 포맷도 최대한 읽기
        with open(CONFIG_PATH, 'r', encoding='utf-8', errors='ignore') as fp:
            cfg.read_file(fp)
        if not cfg.has_section('Telegram'):
            return "", ""
        api_key = cfg.get("Telegram", "api_key", fallback="").strip()
        chat_id = cfg.get("Telegram", "chat_id", fallback="").strip()
        return api_key, chat_id
    except Exception:
        return "", ""


def _save_config(api_key: str, chat_id: str) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    cfg = configparser.ConfigParser()
    if not cfg.has_section('Telegram'):
        cfg.add_section('Telegram')
    cfg.set('Telegram', 'api_key', api_key)
    cfg.set('Telegram', 'chat_id', chat_id)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fp:
        cfg.write(fp)


def create_telegram_button(parent_widget: QWidget, anchor_btn: QPushButton) -> QPushButton:
    btn = QPushButton("텔레그램", parent_widget)
    btn.setFixedSize(80, 28)
    btn.setStyleSheet(
        "QPushButton {background:#16a085; color:white; border:none; font-size:10px;} "
        "QPushButton:hover{background:#1abc9c;} "
        "QPushButton:pressed{background:#0e7a66;}"
    )

    def _place():
        try:
            x = anchor_btn.x() + anchor_btn.width() + 5
            y = anchor_btn.y()
            btn.move(x, y)
        except Exception:
            pass

    _place()

    # 부모 리사이즈에서도 따라가게 함
    try:
        orig_resize = getattr(parent_widget, "resizeEvent", None)
        def _on_resize(ev):
            if orig_resize:
                orig_resize(ev)
            _place()
        parent_widget.resizeEvent = _on_resize
    except Exception:
        pass

    def _on_clicked():
        api_key, chat_id = _load_existing()
        dlg = TelegramConfigDialog(parent_widget.window(), api_key=api_key, chat_id=chat_id)
        if dlg.exec_() == QDialog.Accepted:
            new_api, new_chat = dlg.get_values()
            if not new_api or not new_chat:
                QMessageBox.warning(parent_widget.window(), "텔레그램", "API Key와 Chat ID를 모두 입력하세요.")
                return
            try:
                _save_config(new_api, new_chat)
                QMessageBox.information(parent_widget.window(), "텔레그램", "텔레그램 정보가 저장되었습니다.")
            except Exception as e:
                QMessageBox.critical(parent_widget.window(), "텔레그램", f"저장 중 오류가 발생했습니다.\n{e}")

    btn.clicked.connect(_on_clicked)
    return btn


# ===== 공개 유틸 =====

def load_config() -> tuple[str, str]:
    return _load_existing()


def is_configured() -> bool:
    api, chat = _load_existing()
    return bool(api and chat)


def send_message(text: str) -> bool:
    try:
        api_key, chat_id = _load_existing()
        if not api_key or not chat_id:
            return False
        # 표준 라이브러리로 요청
        from urllib.parse import quote_plus
        from urllib.request import urlopen, Request
        base = f"https://api.telegram.org/bot{api_key}/sendMessage"
        req = Request(
            url=f"{base}?chat_id={quote_plus(chat_id)}&text={quote_plus(text)}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urlopen(req, timeout=8) as resp:  # nosec - controlled URL
            return 200 <= getattr(resp, 'status', 200) < 300
    except Exception:
        return False


def send_message_async(text: str) -> None:
    def _run():
        try:
            send_message(text)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
