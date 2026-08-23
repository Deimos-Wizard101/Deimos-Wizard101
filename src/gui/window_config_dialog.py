"""Per-account window size / resolution editor.

A popup opened from each launcher account row (the "proportions" icon). It shows a
mock of the current multi-monitor layout (physical screen coords) with a draggable,
resizable rectangle representing the game window, plus dimmed boxes for the OTHER
accounts' saved windows so they can be lined up (edges snap to monitor, taskbar, and
other-window edges within a small radius). Each monitor's taskbar is drawn as an amber
bar with an accent line on its inner edge — the boundary the window snaps flush against.
A preset dropdown sets a common resolution (and the
window size 1:1); a lock toggle links the render resolution to the window client
size; a borderless checkbox strips the title bar/borders. Saving stores the config
in the account's wizlaunch metadata; it is applied automatically on launch.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QSpinBox,
    QWidget, QCheckBox, QComboBox,
)
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont

import wizlaunch


# ---- physical monitor enumeration (matches SetWindowPos screen coords) ----
_user32 = ctypes.windll.user32


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


_MONENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_double
)


def enum_monitors():
    """Return [(x, y, w, h, is_primary, (wx, wy, ww, wh)), ...] in physical
    virtual-desktop coords.

    The trailing tuple is the monitor's *work area* (``rcWork``) — the screen
    minus the taskbar and any docked appbars. Windows reports this per monitor,
    so it correctly reflects a taskbar shown on all displays or only the primary.
    The taskbar region is the difference between the monitor and its work area
    (see ``_taskbar_rect``).
    """
    out = []

    def _cb(hmon, hdc, lprc, lparam):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        _user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        r, wk = mi.rcMonitor, mi.rcWork
        out.append((r.left, r.top, r.right - r.left, r.bottom - r.top, bool(mi.dwFlags & 1),
                    (wk.left, wk.top, wk.right - wk.left, wk.bottom - wk.top)))
        return 1

    _user32.EnumDisplayMonitors(None, None, _MONENUMPROC(_cb), 0)
    if not out:
        sw, sh = _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
        out.append((0, 0, sw, sh, True, (0, 0, sw, sh)))
    return out


def _taskbar_rect(mon):
    """Taskbar/appbar region of a monitor = monitor area minus work area.

    Returns ``(tx, ty, tw, th, edge)`` where ``edge`` is the monitor edge the
    taskbar is docked to (``'bottom'|'top'|'left'|'right'``), or ``None`` when
    the monitor has no taskbar (work area fills it). The reserved strip is along
    exactly one edge; we pick whichever side the work area was inset from.
    """
    mx, my, mw, mh, _p, (wx, wy, ww, wh) = mon
    mr, mb = mx + mw, my + mh
    wr, wb = wx + ww, wy + wh
    if wb < mb:                       # docked at the bottom (most common)
        return (mx, wb, mw, mb - wb, 'bottom')
    if wy > my:                       # docked at the top
        return (mx, my, mw, wy - my, 'top')
    if wx > mx:                       # docked at the left
        return (mx, my, wx - mx, mh, 'left')
    if wr < mr:                       # docked at the right
        return (wr, my, mr - wr, mh, 'right')
    return None


# ---- common resolutions for the preset dropdown (grouped by aspect ratio) ----
def _ar_label(w: int, h: int) -> str:
    from math import gcd
    g = gcd(w, h) or 1
    rw, rh = w // g, h // g
    # collapse a few near-standard ratios for readability
    pretty = {(8, 5): (16, 10), (5, 3): (15, 9),
              (64, 27): (21, 9), (43, 18): (21, 9)}
    rw, rh = pretty.get((rw, rh), (rw, rh))
    return f"{rw}:{rh}"


COMMON_RESOLUTIONS = [
    (1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160),
    (1280, 800), (1680, 1050), (1920, 1200),
    (1024, 768), (1280, 960), (1600, 1200),
    (2560, 1080), (3440, 1440),
]


_HANDLE = 9        # px hit-radius for resize handles
_SNAP_PX = 8       # px radius for edge snapping (in canvas pixels)
_MIN_W, _MIN_H = 320, 240


class _MonitorCanvas(QWidget):
    """Draws the monitor layout, other accounts' (dim) windows, and a
    draggable/resizable window rect (all in virtual-desktop coords)."""

    changed = pyqtSignal()

    def __init__(self, monitors, win_rect, others=None, parent=None):
        super().__init__(parent)
        self.monitors = monitors                       # [(x,y,w,h,primary)]
        self.others = others or []                      # [(x,y,w,h,label)]
        self.win = list(win_rect)                       # [x, y, w, h] mutable
        self.setMinimumSize(460, 280)
        self.setMouseTracking(True)
        self._drag = None                               # ('move'|edge code) or None
        self._press = None                              # (mouse virt x,y, win snapshot)
        # virtual-desktop bounds (monitor union)
        xs = [m[0] for m in monitors] + [m[0] + m[2] for m in monitors]
        ys = [m[1] for m in monitors] + [m[1] + m[3] for m in monitors]
        self.vx, self.vy = min(xs), min(ys)
        self.vw, self.vh = max(xs) - self.vx, max(ys) - self.vy
        self._clamp_size_pos()

    # --- keep the window rect inside the monitor union (its bounding box) ---
    def _clamp_pos(self):
        x, y, w, h = self.win
        x = max(self.vx, min(x, self.vx + self.vw - w))
        y = max(self.vy, min(y, self.vy + self.vh - h))
        self.win[0], self.win[1] = x, y

    def _clamp_size_pos(self):
        # The window can be at most the size of the whole monitor area.
        self.win[2] = max(_MIN_W, min(self.win[2], self.vw))
        self.win[3] = max(_MIN_H, min(self.win[3], self.vh))
        self._clamp_pos()

    # --- coordinate mapping (virtual <-> canvas pixels) ---
    def _scale(self):
        pad = 16
        w = self.width() - 2 * pad
        h = self.height() - 2 * pad
        s = min(w / max(self.vw, 1), h / max(self.vh, 1))
        ox = pad + (w - self.vw * s) / 2
        oy = pad + (h - self.vh * s) / 2
        return s, ox, oy

    def _v2c(self, x, y):
        s, ox, oy = self._scale()
        return QPoint(int(ox + (x - self.vx) * s), int(oy + (y - self.vy) * s))

    def _c2v(self, px, py):
        s, ox, oy = self._scale()
        return ((px - ox) / s + self.vx, (py - oy) / s + self.vy)

    def _rect_canvas(self, x, y, w, h):
        return QRect(self._v2c(x, y), self._v2c(x + w, y + h))

    def _win_canvas_rect(self):
        return self._rect_canvas(*self.win)

    # --- snapping: candidate edge lines from monitors, taskbars + other windows ---
    def _snap_lines(self):
        xs, ys = set(), set()
        for mon in self.monitors:
            mx, my, mw, mh = mon[0], mon[1], mon[2], mon[3]
            xs.update((mx, mx + mw)); ys.update((my, my + mh))
            tb = _taskbar_rect(mon)
            if tb:
                tx, ty, tw, th, edge = tb
                # snap to the taskbar's *inner* boundary so the window sits flush
                # against it without overlapping the taskbar.
                if edge == 'bottom': ys.add(ty)
                elif edge == 'top': ys.add(ty + th)
                elif edge == 'left': xs.add(tx + tw)
                elif edge == 'right': xs.add(tx)
        for (ox, oy, ow, oh, _l) in self.others:
            xs.update((ox, ox + ow)); ys.update((oy, oy + oh))
        return sorted(xs), sorted(ys)

    @staticmethod
    def _best_snap(edges, lines, thr):
        """Smallest delta that pulls one of `edges` onto a line within `thr`."""
        best = None
        for e in edges:
            for ln in lines:
                d = ln - e
                if abs(d) <= thr and (best is None or abs(d) < abs(best)):
                    best = d
        return best

    # --- painting ---
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        f = QFont(); f.setPointSize(8); p.setFont(f)
        # monitors (background)
        for mon in self.monitors:
            mx, my, mw, mh, primary = mon[0], mon[1], mon[2], mon[3], mon[4]
            r = self._rect_canvas(mx, my, mw, mh)
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.setBrush(QBrush(QColor(255, 255, 255, 18) if primary else QColor(255, 255, 255, 10)))
            p.drawRoundedRect(r, 4, 4)
            p.setPen(QColor(255, 255, 255, 130))
            p.drawText(r.adjusted(4, 2, -4, -2), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                       f"{mw}x{mh}" + (" ★" if primary else ""))
            # taskbar region (amber) + an accent line on its inner edge — the
            # boundary the window snaps to, so it sits flush against the taskbar.
            tb = _taskbar_rect(mon)
            if tb:
                tx, ty, tw, th, edge = tb
                tr = self._rect_canvas(tx, ty, tw, th)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(255, 184, 77, 45)))
                p.drawRect(tr)
                p.setPen(QPen(QColor(255, 184, 77, 210), 2))
                if edge == 'bottom':
                    p.drawLine(tr.left(), tr.top(), tr.right(), tr.top())
                elif edge == 'top':
                    p.drawLine(tr.left(), tr.bottom(), tr.right(), tr.bottom())
                elif edge == 'left':
                    p.drawLine(tr.right(), tr.top(), tr.right(), tr.bottom())
                elif edge == 'right':
                    p.drawLine(tr.left(), tr.top(), tr.left(), tr.bottom())
                if tr.width() > 46 and tr.height() > 11:
                    p.setPen(QColor(255, 214, 150, 200))
                    p.drawText(tr, Qt.AlignmentFlag.AlignCenter, "Taskbar")
        # other accounts' windows (dim, for alignment)
        for (ox, oy, ow, oh, label) in self.others:
            r = self._rect_canvas(ox, oy, ow, oh)
            p.setPen(QPen(QColor(150, 200, 255, 70), 1, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(150, 200, 255, 24)))
            p.drawRect(r)
            p.setPen(QColor(200, 220, 255, 110))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
        # active window rect
        wr = self._win_canvas_rect()
        p.setPen(QPen(QColor(120, 170, 255), 2))
        p.setBrush(QBrush(QColor(120, 170, 255, 70)))
        p.drawRect(wr)
        p.setPen(QColor(255, 255, 255))
        p.drawText(wr, Qt.AlignmentFlag.AlignCenter, f"{self.win[2]}x{self.win[3]}")
        # corner handles
        p.setBrush(QBrush(QColor(120, 170, 255)))
        p.setPen(QPen(QColor(255, 255, 255), 1))
        for cx, cy in self._handle_points(wr):
            p.drawRect(cx - 3, cy - 3, 6, 6)
        p.end()

    def _handle_points(self, wr):
        return [(wr.left(), wr.top()), (wr.right(), wr.top()),
                (wr.left(), wr.bottom()), (wr.right(), wr.bottom())]

    # --- interaction ---
    def _hit_handle(self, pos):
        wr = self._win_canvas_rect()
        names = ['tl', 'tr', 'bl', 'br']
        for (cx, cy), name in zip(self._handle_points(wr), names):
            if abs(pos.x() - cx) <= _HANDLE and abs(pos.y() - cy) <= _HANDLE:
                return name
        if wr.contains(pos):
            return 'move'
        return None

    def mouseMoveEvent(self, e):
        if self._drag is None:
            h = self._hit_handle(e.position().toPoint())
            cur = {'tl': Qt.CursorShape.SizeFDiagCursor, 'br': Qt.CursorShape.SizeFDiagCursor,
                   'tr': Qt.CursorShape.SizeBDiagCursor, 'bl': Qt.CursorShape.SizeBDiagCursor,
                   'move': Qt.CursorShape.SizeAllCursor}.get(h, Qt.CursorShape.ArrowCursor)
            self.setCursor(cur)
            return
        s = self._scale()[0]
        thr = _SNAP_PX / max(s, 1e-6)                   # snap radius in virtual units
        xs, ys = self._snap_lines()
        vx, vy = self._c2v(e.position().x(), e.position().y())
        px, py, snap = self._press
        ox, oy, ow, oh = snap
        dx, dy = int(vx - px), int(vy - py)
        bx0, by0 = self.vx, self.vy
        bx1, by1 = self.vx + self.vw, self.vy + self.vh
        if self._drag == 'move':
            nx = min(max(ox + dx, bx0), bx1 - ow)
            ny = min(max(oy + dy, by0), by1 - oh)
            sdx = self._best_snap([nx, nx + ow], xs, thr)
            if sdx is not None:
                nx = min(max(nx + sdx, bx0), bx1 - ow)
            sdy = self._best_snap([ny, ny + oh], ys, thr)
            if sdy is not None:
                ny = min(max(ny + sdy, by0), by1 - oh)
            self.win[0], self.win[1] = nx, ny
        else:
            # Resize: clamp the dragged edge to bounds, snap it, keep opposite edge.
            x, y, w, h = ox, oy, ow, oh
            right, bottom = ox + ow, oy + oh
            if 'l' in self._drag:
                x = min(max(ox + dx, bx0), right - _MIN_W)
                sd = self._best_snap([x], xs, thr)
                if sd is not None:
                    x = min(max(x + sd, bx0), right - _MIN_W)
                w = right - x
            if 'r' in self._drag:
                w = min(max(ow + dx, _MIN_W), bx1 - x)
                sd = self._best_snap([x + w], xs, thr)
                if sd is not None:
                    w = min(max(w + sd, _MIN_W), bx1 - x)
            if 't' in self._drag:
                y = min(max(oy + dy, by0), bottom - _MIN_H)
                sd = self._best_snap([y], ys, thr)
                if sd is not None:
                    y = min(max(y + sd, by0), bottom - _MIN_H)
                h = bottom - y
            if 'b' in self._drag:
                h = min(max(oh + dy, _MIN_H), by1 - y)
                sd = self._best_snap([y + h], ys, thr)
                if sd is not None:
                    h = min(max(h + sd, _MIN_H), by1 - y)
            self.win = [x, y, w, h]
        self.update()
        self.changed.emit()

    def mousePressEvent(self, e):
        h = self._hit_handle(e.position().toPoint())
        if h is None:
            return
        vx, vy = self._c2v(e.position().x(), e.position().y())
        self._drag = h
        self._press = (vx, vy, tuple(self.win))

    def mouseReleaseEvent(self, _):
        self._drag = None

    def set_win(self, x, y, w, h):
        self.win = [int(x), int(y), int(w), int(h)]
        self._clamp_size_pos()
        self.update()
        self.changed.emit()


def show_window_config_dialog(ctx, nickname: str):
    has_tl = hasattr(ctx, 'tl')
    tl = ctx.tl if has_tl else (lambda s: s)
    monitors = enum_monitors()

    # Other accounts' saved windows (dimmed, for alignment).
    others = []
    try:
        for nick in wizlaunch.list_accounts():
            if nick == nickname:
                continue
            c = wizlaunch.get_window_config(nick)
            if c:
                others.append((c[0], c[1], c[2], c[3], nick))
    except Exception:
        others = []

    existing = None
    try:
        existing = wizlaunch.get_window_config(nickname)
    except Exception:
        existing = None

    if existing:
        x, y, w, h, res_w, res_h, locked, borderless = existing
    else:
        # default: 1280x720 centered on the primary monitor
        prim = next((m for m in monitors if m[4]), monitors[0])
        w, h = 1280, 720
        x = prim[0] + (prim[2] - w) // 2
        y = prim[1] + (prim[3] - h) // 2
        res_w, res_h, locked, borderless = w, h, True, False

    dlg = QDialog(ctx.window)
    dlg.setWindowTitle(tl('window_config_title').format(nickname) if has_tl else f"Window — {nickname}")
    dlg.setModal(True)
    dlg.setStyleSheet(f"QWidget {{ background-color: {ctx.bg_color}; color: {ctx.text_color}; }}")
    layout = QVBoxLayout(dlg)

    canvas = _MonitorCanvas(monitors, [x, y, w, h], others)
    layout.addWidget(canvas, 1)
    # The canvas clamps the rect into the monitor union on construction; mirror it.
    w, h = canvas.win[2], canvas.win[3]
    if locked:
        res_w, res_h = w, h

    state = {'sync': False}

    def _spin(val, mx=32000):
        s = QSpinBox(); s.setRange(1, mx); s.setValue(int(val))
        s.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)   # no up/down arrows
        s.setFixedWidth(88); s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return s

    win_w = _spin(w); win_h = _spin(h)
    res_w_s = _spin(res_w); res_h_s = _spin(res_h)

    # ---- preset dropdown (common resolutions + aspect ratios) ----
    preset = QComboBox()
    preset.setMinimumWidth(190)        # fit "1920 × 1080  (16:9)" without clipping
    preset.setCursor(Qt.CursorShape.PointingHandCursor)
    if getattr(ctx, 'alt_bg', None):
        preset.setStyleSheet(
            f"QComboBox {{ background-color: {ctx.alt_bg}; color: {ctx.text_color};"
            f" border: 1px solid {getattr(ctx, 'stroke_color', '#555')}; border-radius: 4px;"
            f" padding: 3px 6px; }}"
            f" QComboBox QAbstractItemView {{ background-color: {ctx.alt_bg};"
            f" color: {ctx.text_color}; selection-background-color: {ctx.bg_color}; }}")
    preset.addItem(tl('custom') if has_tl else "Custom", None)
    for pw, ph in COMMON_RESOLUTIONS:
        preset.addItem(f"{pw} × {ph}  ({_ar_label(pw, ph)})", (pw, ph))

    def _preset_index(pw, ph):
        # findData() is unreliable for Python-tuple userData; scan explicitly.
        for i in range(preset.count()):
            if preset.itemData(i) == (pw, ph):
                return i
        return 0

    def _select_preset_for(pw, ph):
        idx = _preset_index(pw, ph)
        state['sync'] = True
        preset.setCurrentIndex(idx)
        state['sync'] = False

    # ---- lock toggle (render resolution == window size) ----
    lock_btn = QPushButton(); lock_btn.setFixedSize(24, 24); lock_btn.setCheckable(True)
    lock_btn.setStyleSheet(ctx.icon_btn_style); lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _update_lock_icon():
        ic = ctx.svgs['lock'] if lock_btn.isChecked() else ctx.svgs['lock_open']
        lock_btn.setIcon(ctx.titlebar_svg_icon(ic, 16))
        lock_btn.setToolTip((tl('lock_res_to_window') if has_tl else
                             "Lock render resolution to window size (crisp 1:1)"))

    def _apply_lock():
        locked_now = lock_btn.isChecked()
        res_w_s.setEnabled(not locked_now)
        res_h_s.setEnabled(not locked_now)
        if locked_now:
            res_w_s.setValue(win_w.value()); res_h_s.setValue(win_h.value())
        _update_lock_icon()

    # ---- compact, centered size/resolution grid ----
    grid = QGridLayout()
    grid.setHorizontalSpacing(6); grid.setVerticalSpacing(8)
    cross1 = QLabel("×"); cross1.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cross2 = QLabel("×"); cross2.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl_size = QLabel(tl('window_size') if has_tl else "Window size")
    lbl_res = QLabel(tl('resolution') if has_tl else "Resolution")
    lbl_size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lbl_res.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    grid.addWidget(lbl_size, 0, 0)
    grid.addWidget(win_w, 0, 1); grid.addWidget(cross1, 0, 2); grid.addWidget(win_h, 0, 3)
    grid.addWidget(lbl_res, 1, 0)
    grid.addWidget(res_w_s, 1, 1); grid.addWidget(cross2, 1, 2); grid.addWidget(res_h_s, 1, 3)
    # Lock spans both rows so it sits vertically centered against the size+res group.
    grid.addWidget(lock_btn, 0, 4, 2, 1,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
    grid_wrap = QHBoxLayout(); grid_wrap.addStretch(); grid_wrap.addLayout(grid); grid_wrap.addStretch()

    # preset row (centered)
    preset_row = QHBoxLayout()
    preset_row.addStretch()
    preset_row.addWidget(QLabel(tl('preset') if has_tl else "Preset"))
    preset_row.addWidget(preset)
    preset_row.addStretch()

    # borderless checkbox (centered)
    borderless_cb = QCheckBox(tl('borderless') if has_tl else "Borderless (no title bar / borders)")
    borderless_cb.setChecked(bool(borderless))
    borderless_cb.setCursor(Qt.CursorShape.PointingHandCursor)
    bl_row = QHBoxLayout(); bl_row.addStretch(); bl_row.addWidget(borderless_cb); bl_row.addStretch()

    layout.addLayout(preset_row)
    layout.addLayout(grid_wrap)
    layout.addLayout(bl_row)

    # ---- wiring (guarded against feedback loops via state['sync']) ----
    def _refresh_preset_combo():
        _select_preset_for(win_w.value(), win_h.value())

    def _on_canvas_change():
        state['sync'] = True
        win_w.setValue(canvas.win[2]); win_h.setValue(canvas.win[3])
        if lock_btn.isChecked():
            res_w_s.setValue(canvas.win[2]); res_h_s.setValue(canvas.win[3])
        state['sync'] = False
        _refresh_preset_combo()

    def _on_fields_change():
        if state['sync']:
            return
        canvas.set_win(canvas.win[0], canvas.win[1], win_w.value(), win_h.value())
        if lock_btn.isChecked():
            res_w_s.setValue(win_w.value()); res_h_s.setValue(win_h.value())
        _refresh_preset_combo()

    def _on_preset(idx):
        if state['sync']:
            return
        data = preset.itemData(idx)
        if not data:
            return
        pw, ph = data
        # Auto-set window size AND resolution 1:1 to the preset, and lock them.
        state['sync'] = True
        lock_btn.setChecked(True)
        win_w.setValue(pw); win_h.setValue(ph)
        res_w_s.setValue(pw); res_h_s.setValue(ph)
        res_w_s.setEnabled(False); res_h_s.setEnabled(False)
        _update_lock_icon()
        state['sync'] = False
        canvas.set_win(canvas.win[0], canvas.win[1], pw, ph)  # re-emits -> resyncs spinboxes

    lock_btn.setChecked(bool(locked))
    lock_btn.toggled.connect(_apply_lock)
    canvas.changed.connect(_on_canvas_change)
    win_w.valueChanged.connect(_on_fields_change)
    win_h.valueChanged.connect(_on_fields_change)
    preset.currentIndexChanged.connect(_on_preset)
    _apply_lock()
    _refresh_preset_combo()

    # ---- buttons ----
    btn_row = QHBoxLayout(); btn_row.addStretch()
    clear_btn = QPushButton(tl('clear') if has_tl else "Clear")
    clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    save_btn = QPushButton(tl('settings_save') if has_tl else "Save")
    save_btn.setStyleSheet(ctx.btn_style); save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_row.addWidget(clear_btn); btn_row.addWidget(save_btn)
    layout.addLayout(btn_row)

    def _save():
        cx, cy = canvas.win[0], canvas.win[1]
        ww, wh = win_w.value(), win_h.value()
        if lock_btn.isChecked():
            rw, rh = ww, wh
        else:
            rw, rh = res_w_s.value(), res_h_s.value()
        try:
            wizlaunch.set_window_config(nickname, int(cx), int(cy), int(ww), int(wh),
                                        int(rw), int(rh), bool(lock_btn.isChecked()),
                                        bool(borderless_cb.isChecked()))
        except Exception:
            pass
        dlg.accept()

    def _clear():
        try:
            wizlaunch.clear_window_config(nickname)
        except Exception:
            pass
        dlg.accept()

    save_btn.clicked.connect(_save)
    clear_btn.clicked.connect(_clear)

    dlg.resize(540, 480)
    dlg.exec()
