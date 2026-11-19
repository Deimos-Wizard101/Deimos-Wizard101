"""Apply-time feedback for the existing raw playstyle editor."""
from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtWidgets import QLabel

APPLY_ACK_TIMEOUT_MS = 15000


class PlaystyleApplyFeedback(QObject):
    def __init__(self, editor, translate, parent, context=None):
        super().__init__(parent)
        self.editor, self.tl = editor, translate
        self.context, self.state = context, 'neutral'
        self.sequence, self.pending = 0, None
        self.label = QLabel(parent)
        self.label.setObjectName('playstyleApplyStatus')
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(APPLY_ACK_TIMEOUT_MS)
        self.timer.timeout.connect(self.timeout)
        editor.textChanged.connect(self.edited)

    def show(self, text, state='neutral'):
        self.state = state
        colors = ({'error': '#b3261e', 'success': '#246b40'}
                  if getattr(self.context, 'theme', 'dark') == 'light' else
                  {'error': '#e06c6c', 'success': '#7fcf9c'})
        color = colors.get(state)
        self.label.setStyleSheet(f'color: {color};' if color else '')
        self.label.setText(text)

    def retheme(self):
        self.show(self.label.text(), self.state)

    def request(self):
        self.sequence += 1
        self.pending = {'source': self.editor.toPlainText(), 'request_id': self.sequence}
        self.timer.start()
        self.show(self.tl('playstyle_applying'))
        return dict(self.pending)

    def edited(self):
        self.pending = None
        self.timer.stop()
        self.show('')

    def timeout(self):
        if self.pending is None:
            return
        self.timer.stop()
        self.show(self.tl('playstyle_apply_unconfirmed'))

    def receive(self, result):
        if (not isinstance(result, dict) or self.pending is None
                or result.get('request_id') != self.pending['request_id']
                or result.get('source') != self.pending['source']
                or result.get('source') != self.editor.toPlainText()):
            return
        self.timer.stop()
        self.pending = None
        state = result.get('state')
        if state == 'applied':
            count = result['applied_clients']
            key = 'playstyle_applied_one' if count == 1 else 'playstyle_applied_many'
            self.show(self.tl(key).replace('{count}', str(count)), 'success')
        elif state == 'invalid':
            self.show(result['message'] + '\n' + self.tl('playstyle_active_unchanged'), 'error')
        elif state == 'no_clients':
            self.show(self.tl('playstyle_no_clients'))
        elif state == 'no_op':
            self.show(self.tl('playstyle_no_changes'))
        elif state == 'hooking':
            self.show(self.tl('playstyle_hooking'))
        else:
            key = 'playstyle_active_unchanged' if result.get('configs_restored') else 'playstyle_rollback_failed'
            lines = [self.tl('playstyle_apply_failed'), self.tl(key)]
            if not result.get('combat_restored', True):
                lines.append(self.tl('playstyle_combat_unconfirmed'))
            self.show('\n'.join(lines), 'error')
