from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QPushButton, QScrollArea, QFrame

from PyQt6.QtCore import Qt

from src.gui.commands import GUICommand, GUICommandType, GUIKeys
from src.gui.helpers import centered_label, repo_icon_btn, copy_callback


def build_camera_tab(ctx):
    tab = QWidget()
    outer = QVBoxLayout(tab)
    outer.setContentsMargins(4, 2, 4, 2)
    outer.setSpacing(2)

    cam_header = QHBoxLayout()
    cam_header.addWidget(centered_label(ctx.tl('advanced_warning')), 1)
    cam_header.addWidget(repo_icon_btn(ctx, ctx.svgs['readme'], ctx.tl('tooltip_wiki_camera'), f"{ctx.wiki_base}/Camera"))
    outer.addLayout(cam_header)

    tab_layout = QHBoxLayout()
    tab_layout.setSpacing(4)
    outer.addLayout(tab_layout, 1)

    cam_inputs = {}
    sc = ctx.stroke_color

    _cam_icons = {
        'axis':    f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13.5 10.5 15 9"/><path d="M4 4v15a1 1 0 0 0 1 1h15"/><path d="M4.293 19.707 6 18"/><path d="m9 15 1.5-1.5"/></svg>',
        'rotate':  f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16.466 7.5C15.643 4.237 13.952 2 12 2 9.239 2 7 6.477 7 12s2.239 10 5 10c.342 0 .677-.069 1-.2"/><path d="m15.194 13.707 3.814 1.86-1.86 3.814"/><path d="M19 15.57c-1.804.885-4.274 1.43-7 1.43-5.523 0-10-2.239-10-5s4.477-5 10-5c4.838 0 8.873 1.718 9.8 4"/></svg>',
        'person':  f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="1"/><path d="m9 20 3-6 3 6"/><path d="m6 8 6 2 6-2"/><path d="M12 10v4"/></svg>',
        'gid':     f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 10a2 2 0 0 0-2 2c0 1.02-.1 2.51-.26 4"/><path d="M14 13.12c0 2.38 0 6.38-1 8.88"/><path d="M17.29 21.02c.12-.6.43-2.3.5-3.02"/><path d="M2 12a10 10 0 0 1 18-6"/><path d="M2 16h.01"/><path d="M21.8 16c.2-2 .131-5.354 0-6"/><path d="M5 19.5C5.5 18 6 15 6 12a6 6 0 0 1 .34-2"/><path d="M8.65 22c.21-.66.45-1.32.57-2"/><path d="M9 6.8a6 6 0 0 1 9 5.2v2"/></svg>',
        'dist':    f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="1"/><path d="M18.944 12.33a1 1 0 0 0 0-.66 7.5 7.5 0 0 0-13.888 0 1 1 0 0 0 0 .66 7.5 7.5 0 0 0 13.888 0"/></svg>',
        'focus':   f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/></svg>',
        'full':    f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{sc}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><rect width="10" height="8" x="7" y="8" rx="1"/></svg>',
    }

    # (placeholder, tag, icon, default_value)
    # default_value=None means no reset button, 'gid' is special-cased
    _cam_fields = [
        ('X',                    'CamXInput',         _cam_icons['axis'],   None),
        ('Y',                    'CamYInput',         _cam_icons['axis'],   None),
        ('Z',                    'CamZInput',         _cam_icons['axis'],   None),
        (ctx.tl('yaw'),          'CamYawInput',       _cam_icons['rotate'], None),
        (ctx.tl('pitch'),        'CamPitchInput',     _cam_icons['rotate'], None),
        (ctx.tl('roll'),         'CamRollInput',      _cam_icons['rotate'], '0'),
        (ctx.tl('entity'),       'CamEntityInput',    _cam_icons['person'], 'Player Object'),
        ('GID',                  'CamEntityGIDInput', _cam_icons['gid'],    'gid'),
        (ctx.tl('distance'),     'CamDistanceInput',  _cam_icons['dist'],   '300'),
        (ctx.tl('dist_min'),     'CamMinInput',       _cam_icons['focus'],  '150'),
        (ctx.tl('dist_max'),     'CamMaxInput',       _cam_icons['full'],   '450'),
    ]

    # --- Left panel: Camera fields + Update ---
    left_panel = QWidget()
    left_panel.setFixedWidth(310)
    left_layout = QVBoxLayout(left_panel)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(4)

    cam_scroll = QScrollArea()
    cam_scroll.setWidgetResizable(True)
    cam_scroll.setFrameShape(QFrame.Shape.NoFrame)
    cam_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    cam_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    cam_scroll_widget = QWidget()
    cam_scroll_layout = QVBoxLayout(cam_scroll_widget)
    cam_scroll_layout.setContentsMargins(0, 2, 0, 2)
    cam_scroll_layout.setSpacing(2)

    reset_svg = ctx.svgs['reset']

    for placeholder, tag, icon_svg, default in _cam_fields:
        row = QHBoxLayout()
        row.setSpacing(2)
        row.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()
        icon_label.setFixedSize(20, 20)
        icon_label.setPixmap(ctx.titlebar_svg_icon(icon_svg, 16).pixmap(16, 16))
        ctx.tracked_svg_labels.append([icon_label, icon_svg, 16, 'pixmap'])
        row.addWidget(icon_label)

        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        cam_inputs[tag] = inp
        ctx.widget_tags[tag] = inp
        row.addWidget(inp, 1)

        if default is not None:
            reset_btn = QPushButton()
            reset_btn.setIcon(ctx.titlebar_svg_icon(reset_svg, 14))
            reset_btn.setFixedSize(20, 20)
            reset_btn.setStyleSheet(ctx.icon_btn_style)
            ctx.tracked_svg_labels.append([reset_btn, reset_svg, 14, 'icon'])
            reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if default == 'gid':
                reset_btn.setToolTip(ctx.tl('fetch_player_gid'))
                reset_btn.clicked.connect(lambda checked: ctx.send_queue.put(GUICommand(GUICommandType.PopulatePlayerGID)))
            else:
                reset_btn.setToolTip(ctx.tl('reset_to_default').format(default))
                reset_btn.clicked.connect(lambda checked, i=inp, d=default: i.setText(d))
            row.addWidget(reset_btn)
        else:
            spacer = QLabel()
            spacer.setFixedSize(20, 20)
            row.addWidget(spacer)

        cam_scroll_layout.addLayout(row)

    cam_scroll_layout.addStretch()
    cam_scroll.setWidget(cam_scroll_widget)
    left_layout.addWidget(cam_scroll, 1)

    def update_camera_callback():
        pos_vals = [cam_inputs['CamXInput'].text(), cam_inputs['CamYInput'].text(), cam_inputs['CamZInput'].text(),
                    cam_inputs['CamYawInput'].text(), cam_inputs['CamRollInput'].text(), cam_inputs['CamPitchInput'].text()]
        if any(pos_vals):
            ctx.send_queue.put(GUICommand(GUICommandType.SetCamPosition, {
                'X': pos_vals[0], 'Y': pos_vals[1], 'Z': pos_vals[2],
                'Yaw': pos_vals[3], 'Roll': pos_vals[4], 'Pitch': pos_vals[5],
            }))
        anchor_name = cam_inputs['CamEntityInput'].text()
        anchor_gid = cam_inputs['CamEntityGIDInput'].text()
        if anchor_name or anchor_gid:
            ctx.send_queue.put(GUICommand(GUICommandType.AnchorCam, {'name': anchor_name, 'gid': anchor_gid}))
        dist_vals = [cam_inputs['CamDistanceInput'].text(), cam_inputs['CamMinInput'].text(), cam_inputs['CamMaxInput'].text()]
        if any(dist_vals):
            ctx.send_queue.put(GUICommand(GUICommandType.SetCamDistance, {
                "Distance": dist_vals[0], "Min": dist_vals[1], "Max": dist_vals[2],
            }))

    left_layout.addWidget(ctx.registry.styled_btn(ctx.tl('set_camera_position'), update_camera_callback))
    tab_layout.addWidget(left_panel)

    # --- Right panel: Utils (centered) ---
    right_panel = QWidget()
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(4, 4, 4, 4)

    right_layout.addStretch()

    def populate_camera_callback():
        ctx.send_queue.put(GUICommand(GUICommandType.PopulateCamera))

    utils_col = QVBoxLayout()
    utils_col.setSpacing(4)
    utils_col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    utils_col.addWidget(ctx.registry.styled_btn(ctx.tl('populate_camera'), populate_camera_callback))
    utils_col.addWidget(ctx.registry.styled_btn(ctx.tl('copy_camera_position'), copy_callback(ctx.send_queue, GUIKeys.copy_camera_position)))
    utils_col.addWidget(ctx.registry.styled_btn(ctx.tl('toggle_camera_collision'), lambda: ctx.send_queue.put(GUICommand(GUICommandType.ToggleOption, GUIKeys.toggle_camera_collision))))
    right_layout.addLayout(utils_col)

    right_layout.addStretch()
    tab_layout.addWidget(right_panel)

    return tab
