from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor

from src.gui.helpers import build_shared_svgs


def compute_styles(theme: dict, font: str = None, font_size: int = None) -> dict:
    """Pure function: from a 6-color theme dict, compute all stylesheet strings."""

    bg = theme["bg_color"]
    alt = theme["alt_bg"]
    tc = theme["text_color"]
    sc = theme["stroke_color"]
    bc = theme["button_color"]
    tb = theme["titlebar_bg"]

    def _rgba(color_value, alpha: int, fallback: str = "#ffffff") -> str:
        qcolor = QColor(str(color_value))

        if not qcolor.isValid():
            qcolor = QColor(fallback)

        return f"rgba({qcolor.red()},{qcolor.green()},{qcolor.blue()},{alpha})"

    tc_rgba_25 = _rgba(tc, 25)
    tc_rgba_40 = _rgba(tc, 40)

    font_css = (f" font-family: '{font}';" if font else "") + (
        f" font-size: {font_size}pt;" if font_size else ""
    )

    app_style = (
        f"QWidget {{ background-color: {bg}; color: {tc};{font_css} }}"
        f"QComboBox {{ background-color: {alt}; color: {tc}; padding-left: 4px; }}"
        f"QComboBox QAbstractItemView {{ background-color: {alt}; color: {tc}; selection-background-color: {tc_rgba_25}; }}"
        f"QLineEdit {{ background-color: {alt}; color: {tc}; }}"
        f"QTextEdit {{ background-color: {alt}; color: {tc}; }}"
        f"QPlainTextEdit {{ background-color: {alt}; color: {tc}; }}"
        f"QListWidget {{ background-color: {alt}; color: {tc}; }}"
        # Fix top tab text color.
        # Without this block, QTabBar can keep the system/default black text.
        f"QTabWidget::pane {{ border: none; background-color: {bg}; }}"
        f"QTabBar {{ background-color: {bg}; color: {tc}; }}"
        f"QTabBar::tab {{"
        f"  background-color: transparent;"
        f"  color: {tc};"
        f"  border: none;"
        f"  padding: 6px 14px;"
        f"  margin: 0 2px;"
        f"  font-weight: normal;"
        f"}}"
        f"QTabBar::tab:hover {{"
        f"  background-color: {tc_rgba_25};"
        f"  color: {tc};"
        f"}}"
        f"QTabBar::tab:selected {{"
        f"  background-color: {tc_rgba_40};"
        f"  color: {tc};"
        f"  border-bottom: 2px solid {tc};"
        f"  font-weight: bold;"
        f"}}"
        f"QTabBar::tab:!selected {{"
        f"  color: {tc};"
        f"}}"
    )

    groupbox_style = (
        "QGroupBox {"
        "  border: none;"
        "  margin-top: 6px;"
        "  padding-top: 2px;"
        "}"
        "QGroupBox::title {"
        "  subcontrol-origin: margin;"
        "  subcontrol-position: top left;"
        "  padding: 0 4px;"
        "  font-weight: bold;"
        "}"
    )

    _hex = bc.lstrip("#") if isinstance(bc, str) else "4a019e"

    if len(_hex) < 6:
        _hex = "4a019e"

    btn_r, btn_g, btn_b = int(_hex[0:2], 16), int(_hex[2:4], 16), int(_hex[4:6], 16)

    btn_style = (
        f"QPushButton {{"
        f"  background-color: rgb({btn_r},{btn_g},{btn_b});"
        f"  color: white;"
        f"  border: none;"
        f"  padding: 4px 8px;"
        f"  border-radius: 4px;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background-color: rgb({min(btn_r + 30, 255)},{min(btn_g + 30, 255)},{min(btn_b + 30, 255)});"
        f"}}"
        f"QPushButton:pressed {{"
        f"  background-color: rgb({max(btn_r - 20, 0)},{max(btn_g - 20, 0)},{max(btn_b - 20, 0)});"
        f"}}"
    )

    icon_btn_style = (
        "QPushButton {"
        "  background-color: transparent;"
        "  border: none;"
        "  padding: 2px;"
        "}"
        "QPushButton:hover {"
        f"  background-color: {tc_rgba_25};"
        "  border-radius: 4px;"
        "}"
    )

    titlebar_style = f"QWidget {{ background-color: {tb}; }}"

    return {
        "app_style": app_style,
        "groupbox_style": groupbox_style,
        "btn_style": btn_style,
        "icon_btn_style": icon_btn_style,
        "titlebar_style": titlebar_style,
    }


def apply_theme(ctx, theme: dict):
    """Apply a theme dict to the running GUI at runtime."""

    styles = compute_styles(theme, ctx.gui_font, ctx.gui_font_size)

    bg = theme["bg_color"]
    tc = theme["text_color"]
    sc = theme["stroke_color"]
    bc = theme["button_color"]

    # Determine light/dark
    _hex = bg.lstrip("#")
    r, g, b = int(_hex[0:2], 16), int(_hex[2:4], 16), int(_hex[4:6], 16)
    is_dark = (r + g + b) < 384

    old_stroke = ctx.stroke_color

    # Update ctx properties
    ctx.bg_color = bg
    ctx.text_color = tc
    ctx.stroke_color = sc
    ctx.btn_color_hex = bc
    ctx.theme = "dark" if is_dark else "light"
    ctx.btn_style = styles["btn_style"]
    ctx.icon_btn_style = styles["icon_btn_style"]

    # Apply stylesheets
    app = QApplication.instance()

    if app:
        app.setStyleSheet(styles["app_style"])

    ctx.window.setStyleSheet(styles["groupbox_style"])
    ctx.titlebar.setStyleSheet(styles["titlebar_style"])

    # Update title label color
    ctx.title_label.setStyleSheet(
        f"QLabel {{ color: {tc}; font-weight: bold; background: transparent; }}"
    )

    # Rebuild shared SVGs
    ctx.svgs = build_shared_svgs(sc)

    # Re-style tracked buttons via registry
    ctx.registry.restyle_all(
        styles["btn_style"],
        styles["icon_btn_style"],
        ctx.titlebar_svg_icon,
        old_stroke,
        sc,
    )

    # Re-style helper-created tracked icon buttons
    from src.gui.helpers import restyle_tracked_buttons

    restyle_tracked_buttons(
        ctx,
        styles["icon_btn_style"],
        ctx.titlebar_svg_icon,
        old_stroke,
        sc,
    )

    # Re-render titlebar SVG buttons
    for btn, svg_str in ctx.titlebar_buttons:
        new_svg = svg_str.replace(old_stroke, sc)
        btn.setIcon(ctx.titlebar_svg_icon(new_svg))

    # Update pin SVGs
    old_pin, old_unpin = ctx.pin_svgs
    new_pin = old_pin.replace(old_stroke, sc)
    new_unpin = old_unpin.replace(old_stroke, sc)
    ctx.pin_svgs = (new_pin, new_unpin)

    # Update pin button icon to match current state
    pin_btn = ctx.titlebar_buttons[0][0]
    pin_btn.setIcon(ctx.titlebar_svg_icon(new_pin if ctx.is_pinned[0] else new_unpin))

    # Update stored SVG strings for titlebar buttons
    ctx.titlebar_buttons = [
        (ctx.titlebar_buttons[0][0], new_pin),
        (
            ctx.titlebar_buttons[1][0],
            ctx.titlebar_buttons[1][1].replace(old_stroke, sc),
        ),
        (
            ctx.titlebar_buttons[2][0],
            ctx.titlebar_buttons[2][1].replace(old_stroke, sc),
        ),
        (
            ctx.titlebar_buttons[3][0],
            ctx.titlebar_buttons[3][1].replace(old_stroke, sc),
        ),
    ]

    # Re-render tracked SVG labels
    updated_labels = []

    for entry in ctx.tracked_svg_labels:
        widget, svg_str, size, mode = entry

        try:
            new_svg = svg_str.replace(old_stroke, sc)
            rendered = ctx.titlebar_svg_icon(new_svg, size)

            if mode == "pixmap":
                widget.setPixmap(rendered.pixmap(size, size))
            else:
                widget.setIcon(rendered)

            updated_labels.append([widget, new_svg, size, mode])
        except RuntimeError:
            pass

    ctx.tracked_svg_labels = updated_labels

    # Re-render play/kill toggle buttons
    for btn, running_ref, size in ctx.tracked_toggle_btns:
        try:
            svg = ctx.svgs["kill"] if running_ref[0] else ctx.svgs["play"]
            btn.setIcon(ctx.titlebar_svg_icon(svg, size))
        except RuntimeError:
            pass

    # Re-theme tab exports
    for export_key in ("dev_utils", "hotkeys", "launcher"):
        retheme = ctx.exports.get(export_key, {}).get("retheme")

        if retheme:
            retheme()

    # Update DuelCircleWidget colors
    duel_circle = ctx.duel_circle

    if duel_circle:
        duel_circle.set_theme_colors(sc, tc, bg, bc)

    # Update ToggleSwitch button colors
    btn_qcolor = QColor(bc)

    for ts in ctx.toggle_switches:
        ts.set_button_color(btn_qcolor)
