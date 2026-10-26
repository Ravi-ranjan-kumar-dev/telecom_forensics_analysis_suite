# Safe Main-Thread GUI Dispatcher & QPlainTextEdit / QFontEngineFT Crash Guard
from __future__ import annotations
import threading
from typing import Callable, Any
from PySide6.QtCore import QObject, Signal, Slot, Qt, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollBar,
    QTextEdit,
    QWidget,
)


class _MainThreadInvoker(QObject):
    invoke_signal = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.invoke_signal.connect(self._execute, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def _execute(self, fn: Callable[[], Any]) -> None:
        try:
            fn()
        except Exception as exc:
            import traceback
            print(f'[!] GUI Main-Thread Callback Error: {exc}', flush=True)
            traceback.print_exc()


_GLOBAL_INVOKER: _MainThreadInvoker | None = None
_GUARDS_INSTALLED: bool = False


def _is_main_thread() -> bool:
    if threading.current_thread() is not threading.main_thread():
        return False
    app = QApplication.instance()
    if app is not None and QThread.currentThread() != app.thread():
        return False
    return True


def _sanitize_text(text: Any) -> str:
    if text is None:
        return ''
    s = str(text)
    out = []
    for ch in s:
        code = ord(ch)
        if ch in ('\n', '\r', '\t') or (32 <= code <= 126):
            out.append(ch)
        elif code > 126:
            out.append(' ')
    return ''.join(out)


def _ensure_safe_editor_font(widget: QWidget) -> None:
    try:
        if getattr(widget, '_ea_font_locked', False):
            return
        f = QFont('DejaVu Sans Mono', 10)
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setFixedPitch(True)
        f.setStyleStrategy(
            QFont.StyleStrategy.NoFontMerging | QFont.StyleStrategy.PreferAntialias
        )
        widget.setFont(f)
        setattr(widget, '_ea_font_locked', True)
    except Exception:
        pass


def init_main_thread_dispatcher() -> None:
    global _GLOBAL_INVOKER
    app = QApplication.instance()
    if app is None:
        return
    if _GLOBAL_INVOKER is None:
        _GLOBAL_INVOKER = _MainThreadInvoker(None)
    if _GLOBAL_INVOKER.thread() != app.thread():
        _GLOBAL_INVOKER.moveToThread(app.thread())


def run_on_main_thread(fn: Callable[[], Any]) -> None:
    global _GLOBAL_INVOKER
    app = QApplication.instance()
    if app is None:
        return
    if _GLOBAL_INVOKER is None:
        _GLOBAL_INVOKER = _MainThreadInvoker(None)
        _GLOBAL_INVOKER.moveToThread(app.thread())
    _GLOBAL_INVOKER.invoke_signal.emit(fn)


def install_qt_thread_and_font_guards() -> None:
    global _GUARDS_INSTALLED
    if _GUARDS_INSTALLED:
        return
    _GUARDS_INSTALLED = True

    _orig_qapp_init = QApplication.__init__
    def _hooked_qapp_init(self: QApplication, *args: Any, **kwargs: Any) -> None:
        _orig_qapp_init(self, *args, **kwargs)
        init_main_thread_dispatcher()
        try:
            base_font = QFont('DejaVu Sans', 10)
            base_font.setStyleStrategy(
                QFont.StyleStrategy.NoFontMerging | QFont.StyleStrategy.PreferAntialias
            )
            self.setFont(base_font)
        except Exception:
            pass
    QApplication.__init__ = _hooked_qapp_init  # type: ignore[assignment]

    _pte_init = QPlainTextEdit.__init__
    _pte_append = QPlainTextEdit.appendPlainText
    _pte_insert = QPlainTextEdit.insertPlainText
    _pte_set = QPlainTextEdit.setPlainText
    _pte_html = QPlainTextEdit.appendHtml
    _pte_clear = QPlainTextEdit.clear
    _pte_move = QPlainTextEdit.moveCursor
    _pte_ensure = QPlainTextEdit.ensureCursorVisible

    def _safe_pte_init(self: QPlainTextEdit, *args: Any, **kwargs: Any) -> None:
        _pte_init(self, *args, **kwargs)
        _ensure_safe_editor_font(self)

    def _safe_pte_append(self: QPlainTextEdit, text: str) -> None:
        clean = _sanitize_text(text)
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, t=clean: _safe_pte_append(w, t))
            return
        _ensure_safe_editor_font(self)
        _pte_append(self, clean)

    def _safe_pte_insert(self: QPlainTextEdit, text: str) -> None:
        clean = _sanitize_text(text)
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, t=clean: _safe_pte_insert(w, t))
            return
        _ensure_safe_editor_font(self)
        _pte_insert(self, clean)

    def _safe_pte_set(self: QPlainTextEdit, text: str) -> None:
        clean = _sanitize_text(text)
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, t=clean: _safe_pte_set(w, t))
            return
        _ensure_safe_editor_font(self)
        _pte_set(self, clean)

    def _safe_pte_html(self: QPlainTextEdit, html: str) -> None:
        clean = _sanitize_text(html)
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, t=clean: _safe_pte_html(w, t))
            return
        _ensure_safe_editor_font(self)
        _pte_html(self, clean)

    def _safe_pte_clear(self: QPlainTextEdit) -> None:
        if not _is_main_thread():
            run_on_main_thread(lambda w=self: _safe_pte_clear(w))
            return
        _pte_clear(self)

    def _safe_pte_move(self: QPlainTextEdit, *args: Any, **kwargs: Any) -> None:
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, a=args, k=kwargs: _safe_pte_move(w, *a, **k))
            return
        _pte_move(self, *args, **kwargs)

    def _safe_pte_ensure(self: QPlainTextEdit) -> None:
        if not _is_main_thread():
            run_on_main_thread(lambda w=self: _safe_pte_ensure(w))
            return
        _pte_ensure(self)

    QPlainTextEdit.__init__ = _safe_pte_init                  # type: ignore[assignment]
    QPlainTextEdit.appendPlainText = _safe_pte_append         # type: ignore[assignment]
    QPlainTextEdit.insertPlainText = _safe_pte_insert         # type: ignore[assignment]
    QPlainTextEdit.setPlainText = _safe_pte_set               # type: ignore[assignment]
    QPlainTextEdit.appendHtml = _safe_pte_html                # type: ignore[assignment]
    QPlainTextEdit.clear = _safe_pte_clear                    # type: ignore[assignment]
    QPlainTextEdit.moveCursor = _safe_pte_move                # type: ignore[assignment]
    QPlainTextEdit.ensureCursorVisible = _safe_pte_ensure     # type: ignore[assignment]

    _te_append = QTextEdit.append
    _te_insert = QTextEdit.insertPlainText
    _te_set = QTextEdit.setPlainText
    _te_clear = QTextEdit.clear

    def _safe_te_append(self: QTextEdit, text: str) -> None:
        clean = _sanitize_text(text)
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, t=clean: _safe_te_append(w, t))
            return
        _ensure_safe_editor_font(self)
        _te_append(self, clean)

    def _safe_te_insert(self: QTextEdit, text: str) -> None:
        clean = _sanitize_text(text)
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, t=clean: _safe_te_insert(w, t))
            return
        _ensure_safe_editor_font(self)
        _te_insert(self, clean)

    def _safe_te_set(self: QTextEdit, text: str) -> None:
        clean = _sanitize_text(text)
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, t=clean: _safe_te_set(w, t))
            return
        _ensure_safe_editor_font(self)
        _te_set(self, clean)

    def _safe_te_clear(self: QTextEdit) -> None:
        if not _is_main_thread():
            run_on_main_thread(lambda w=self: _safe_te_clear(w))
            return
        _te_clear(self)

    QTextEdit.append = _safe_te_append                        # type: ignore[assignment]
    QTextEdit.insertPlainText = _safe_te_insert               # type: ignore[assignment]
    QTextEdit.setPlainText = _safe_te_set                     # type: ignore[assignment]
    QTextEdit.clear = _safe_te_clear                          # type: ignore[assignment]

    _lbl_set = QLabel.setText
    def _safe_lbl_set(self: QLabel, text: str) -> None:
        clean = _sanitize_text(text)
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, t=clean: _safe_lbl_set(w, t))
            return
        _lbl_set(self, clean)
    QLabel.setText = _safe_lbl_set                            # type: ignore[assignment]

    _pb_set = QProgressBar.setValue
    def _safe_pb_set(self: QProgressBar, val: int) -> None:
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, v=val: _safe_pb_set(w, v))
            return
        _pb_set(self, val)
    QProgressBar.setValue = _safe_pb_set                      # type: ignore[assignment]

    _btn_en = QPushButton.setEnabled
    def _safe_btn_en(self: QPushButton, enabled: bool) -> None:
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, e=enabled: _safe_btn_en(w, e))
            return
        _btn_en(self, enabled)
    QPushButton.setEnabled = _safe_btn_en                     # type: ignore[assignment]

    _sb_set = QScrollBar.setValue
    def _safe_sb_set(self: QScrollBar, val: int) -> None:
        if not _is_main_thread():
            run_on_main_thread(lambda w=self, v=val: _safe_sb_set(w, v))
            return
        _sb_set(self, val)
    QScrollBar.setValue = _safe_sb_set                        # type: ignore[assignment]
