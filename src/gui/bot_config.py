from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QCheckBox, QComboBox, QLineEdit,
    QSpinBox, QScrollArea, QLabel,
)
from PyQt6.QtCore import Qt, QTimer

from src.deimoslang.ir import Compiler
from src.deimoslang.types import (
    ConfigDeclStmt, ConfigFieldKind, ConfigFieldSelectionInfo, ConfigFieldNumboxInfo,
)


class _NoScrollComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class _NoScrollSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


def _field_signature(decl: ConfigDeclStmt):
    sig = []
    for name, field in decl.fields:
        info = None
        if isinstance(field.info, ConfigFieldSelectionInfo):
            info = tuple(field.info.options)
        elif isinstance(field.info, ConfigFieldNumboxInfo):
            info = (field.info.range.lo, field.info.range.hi)
        sig.append((name, field.kind, field.disp_name, field.tooltip, field.default, info))
    return tuple(sig)


def generate_config_form(decl: ConfigDeclStmt, values: dict | None = None, parent=None):
    """Build a widget from a bot config declaration. Returns (widget, get_values)."""
    values = dict(values or {})
    root = QWidget(parent)
    form = QFormLayout(root)
    form.setContentsMargins(4, 4, 4, 4)
    form.setSpacing(4)
    widgets = {}

    for name, field in decl.fields:
        current = values.get(name, field.default)
        tooltip = field.tooltip or ""
        match field.kind:
            case ConfigFieldKind.checkbox:
                w = QCheckBox(field.disp_name)
                w.setChecked(bool(current))
                if tooltip:
                    w.setToolTip(tooltip)
                form.addRow(w)
            case ConfigFieldKind.selection:
                w = _NoScrollComboBox()
                options = field.info.options if isinstance(field.info, ConfigFieldSelectionInfo) else []
                w.addItems(options)
                text = current if isinstance(current, str) else field.default
                if text in options:
                    w.setCurrentText(text)
                elif options:
                    w.setCurrentIndex(0)
                if tooltip:
                    w.setToolTip(tooltip)
                form.addRow(QLabel(field.disp_name), w)
            case ConfigFieldKind.textbox:
                w = QLineEdit("" if current is None else str(current))
                if tooltip:
                    w.setToolTip(tooltip)
                form.addRow(QLabel(field.disp_name), w)
            case ConfigFieldKind.numbox:
                w = _NoScrollSpinBox()
                lo, hi = 0, 99
                if isinstance(field.info, ConfigFieldNumboxInfo):
                    lo, hi = field.info.range.lo, field.info.range.hi
                w.setRange(lo, hi)
                try:
                    w.setValue(int(current))
                except (TypeError, ValueError):
                    w.setValue(int(field.default))
                if tooltip:
                    w.setToolTip(tooltip)
                form.addRow(QLabel(field.disp_name), w)
            case _:
                continue
        widgets[name] = (field.kind, w)

    def get_values() -> dict:
        result = {}
        for name, (kind, w) in widgets.items():
            match kind:
                case ConfigFieldKind.checkbox:
                    result[name] = w.isChecked()
                case ConfigFieldKind.selection:
                    result[name] = w.currentText()
                case ConfigFieldKind.textbox:
                    result[name] = w.text()
                case ConfigFieldKind.numbox:
                    result[name] = w.value()
        return result

    return root, get_values


class BotConfigPanel(QWidget):
    """Live-updating config form generated from the bot editor source."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self._ctx = ctx
        self._pending_text = ""
        self._signature = None
        self._get_values = lambda: {}
        self._form = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._rebuild)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self._scroll, 1)
        self._show_empty()

    def schedule_update(self, text: str):
        self._pending_text = text
        self._timer.start()

    def flush(self, text: str | None = None):
        if text is not None:
            self._pending_text = text
        self._timer.stop()
        self._rebuild()

    def values(self) -> dict:
        return self._get_values()

    def _rebuild(self):
        try:
            decl = Compiler.config_decl_from_text(self._pending_text)
        except Exception:
            return

        if decl is None or len(decl.fields) == 0:
            self._signature = None
            self._get_values = lambda: {}
            self._form = None
            self._show_empty()
            return

        sig = _field_signature(decl)
        preserved = self._get_values()
        if sig == self._signature and self._form is not None:
            return

        form, get_values = generate_config_form(decl, preserved)
        self._signature = sig
        self._form = form
        self._get_values = get_values
        self._scroll.setWidget(form)

    def _show_empty(self):
        empty = QLabel(self._ctx.tl("bot_config_empty"))
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setWordWrap(True)
        self._scroll.setWidget(empty)
