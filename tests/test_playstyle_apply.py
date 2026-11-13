"""Offline source/parser and native-widget checks; no game client is attached."""
import ast
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def real_parser():
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        assert Path(module.__file__).is_relative_to(ROOT)
        return module
    # The grammar consumes enum definitions, not game memory. Stub only the
    # Windows memory base types so the real vendored parser can run on Linux.
    memory = ModuleType('wizwalker.memory.memory_object')
    for name in ('Primitive', 'PropertyClass', 'DynamicMemoryObject'):
        setattr(memory, name, type(name, (), {}))
    sys.modules[memory.__name__] = memory
    base = ROOT / 'libs/wizwalker/wizwalker/memory/memory_objects'
    load('wizwalker.memory.memory_objects.enums', base / 'enums.py')
    load('wizwalker.memory.memory_objects.conditionals', base / 'conditionals.py')
    package = ModuleType('_apply_test_parser')
    package.__path__ = []
    sys.modules[package.__name__] = package
    base = ROOT / 'libs/wizsprinter/wizwalker/extensions/wizsprinter/combat_backends'
    api = load('_apply_test_parser.combat_api', base / 'combat_api.py')
    grammar = load('_apply_test_parser.combat_config_parser', base / 'combat_config_parser.py')
    tree = ast.parse((base / 'config_backend.py').read_text())
    expand = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_expand_config')
    ns = dict(vars(api))
    exec(compile(ast.Module(body=[expand], type_ignores=[]), 'actual_expand_config', 'exec'), ns)
    from lark import Lark
    def parse(source):
        config = grammar.TreeToConfig().transform(Lark(grammar.get_sprinty_grammar()).parse(source))
        return ns['_expand_config'](None, config)
    return parse


PARSE = real_parser()
# Import the real GUI submodules without starting upstream's Windows-only app entrypoint.
gui = ModuleType('src.gui')
gui.__path__ = [str(ROOT / 'src/gui')]
sys.modules[gui.__name__] = gui
from src.combat_sections import scan_combat_configs
from src.playstyle_validation import prepare_playstyle_application, validate_playstyle, format_playstyle_error
from src.gui.commands import GUICommand, GUICommandType
from src.gui.playstyle_apply import PlaystyleApplyFeedback
from src.lang import load_lang
from PyQt6.QtWidgets import QApplication, QTextEdit, QWidget


def dispatcher(namespace):
    tree = ast.parse((ROOT / 'Deimos.py').read_text())
    case = next(n for n in ast.walk(tree) if isinstance(n, ast.match_case)
                and ast.unparse(n.pattern) == 'deimosgui.GUICommandType.SetPlaystyles')
    wrapper = ast.parse('async def dispatch():\n pass')
    wrapper.body[0].body = case.body
    ast.fix_missing_locations(wrapper)
    exec(compile(wrapper, str(ROOT / 'Deimos.py'), 'exec'), namespace)
    return namespace['dispatch']


def original_delegate_combat_configs(input_data, fallback_clients=1, line_seperator="\n"):
    """Verbatim copy of delegate_combat_configs as it stood at original Deimos dev-main 692d909."""
    import re
    config_lines = input_data.split(line_seperator)
    client_configs = {}
    pattern = re.compile(r'###\s*p\s*(\d+)')
    client_to_match = -1
    local_configs = []
    for i, line in enumerate(config_lines):
        client_match = re.search(pattern, line)
        if client_match is not None:
            if client_to_match != -1:
                client_configs[client_to_match] = line_seperator.join(local_configs)
            client_to_match = int(client_match.group(1)) - 1
            local_configs.clear()
            continue
        local_configs.append(line)
    if client_to_match == -1:
        for i in range(fallback_clients):
            client_configs[i] = line_seperator.join(config_lines)
    else:
        client_configs[client_to_match] = line_seperator.join(local_configs)
    return client_configs


def upstream_function(name, namespace):
    tree = ast.parse((ROOT / 'Deimos.py').read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), f'actual_upstream_{name}', 'exec'), namespace)
    return namespace[name]


def run_with_production_modules(script):
    """Run `script` in a fresh interpreter where the real game-hook modules import; skip where they cannot.

    This process replaces some wizwalker modules with stubs so the grammar can run
    anywhere, so the unstubbed entrypoint has to be exercised in its own process."""
    if subprocess.run([sys.executable, '-c', 'import src.config_combat'], cwd=ROOT, capture_output=True).returncode:
        raise unittest.SkipTest('game-hook imports are unavailable off Windows')
    run = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=180)
    if run.returncode:
        raise AssertionError(run.stderr[-2000:])
    return json.loads(run.stdout.splitlines()[-1])


class ParserTests(unittest.TestCase):
    def test_original_coordinates_and_source_line(self):
        result = validate_playstyle('###p1\npass\n###p2\nany<damage', parser=PARSE)
        self.assertFalse(result.valid)
        self.assertEqual((result.error.player, result.error.line), (2, 4))
        self.assertIn('any<damage', format_playstyle_error(result))

    def test_no_mutation_defaults_blank_and_all_sections(self):
        configs, result = prepare_playstyle_application('###p2\npass', 3, 'default', parser=PARSE)
        self.assertTrue(result.valid)
        self.assertEqual(configs, ['default', 'pass', 'default'])
        configs, result = prepare_playstyle_application('###p7\nany<bad>', 1, 'default', parser=PARSE)
        self.assertIsNone(configs)
        self.assertFalse(result.valid)
        self.assertTrue(prepare_playstyle_application(' \n', 0, 'default', parser=PARSE)[1].no_op)

    def test_default_and_real_grammar_are_unchanged(self):
        tree = ast.parse((ROOT / 'src/config_combat.py').read_text())
        default = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'default_config' for t in n.targets))
        self.assertTrue(validate_playstyle(default, parser=PARSE).valid)
        for source in ('pass', 'any<damage&aoe> @ aoe | pass', '{1} pass\npass'):
            self.assertTrue(validate_playstyle(source, parser=PARSE).valid, source)


class DelegationCompatibilityTests(unittest.TestCase):
    """Apply must accept and assign exactly what original Deimos delegation does."""
    CORPUS = [
        '###p1 storm\npass', '###p1\npass\n###p1\nany<damage&aoe> @ aoe | pass',
        'preamble line\n###p1\npass', '###P1\npass', '### p 2\npass', '###p1\npass\n###p2\nany<damage>|pass',
        '###p2\npass', 'pass', 'pass\r\n', '###p1\r\npass\r\n###p2\r\npass', '#### p1 // note\npass',
        '###p0\npass', '###p1\npass\n###p0\npass', '###p3\npass\n###p1\n{1} pass\npass', '###p1\n###p2\npass',
    ]

    def test_sections_match_original_delegation(self):
        for source in self.CORPUS:
            for clients in (1, 2, 3):
                with self.subTest(source=source, clients=clients):
                    self.assertEqual(scan_combat_configs(source, clients)[0],
                                     original_delegate_combat_configs(source, clients))

    def test_accepted_forms_are_assigned_like_original_delegation(self):
        for source in self.CORPUS:
            for clients in (1, 2, 3):
                configs, result = prepare_playstyle_application(source, clients, 'default', parser=PARSE)
                if configs is None:
                    continue
                original = original_delegate_combat_configs(source, clients)
                self.assertEqual(configs, [original.get(i, 'default') for i in range(clients)], (source, clients))

    def test_header_with_trailing_text_and_repeated_headers_are_accepted(self):
        configs, result = prepare_playstyle_application('###p1 storm\npass', 1, 'default', parser=PARSE)
        self.assertTrue(result.valid)
        self.assertEqual(configs, ['pass'])
        configs, result = prepare_playstyle_application('###p1\nany<bad>\n###p1\npass', 1, 'default', parser=PARSE)
        self.assertTrue(result.valid, 'the discarded earlier section is never applied')
        self.assertEqual(configs, ['pass'])

    def test_errors_are_reported_in_editor_coordinates(self):
        result = validate_playstyle('preamble\n###p1 storm\npass\n###p2\n\nany<damage', parser=PARSE)
        self.assertEqual((result.error.player, result.error.line), (2, 6))

    def test_config_combat_delegates_to_the_same_scan(self):
        script = ('import json; from src.config_combat import delegate_combat_configs as d; '
                  f'print(json.dumps([{{str(k): v for k, v in d(s, 2).items()}} for s in {self.CORPUS!r}]))')
        actual = run_with_production_modules(script)
        expected = [{str(k): v for k, v in original_delegate_combat_configs(s, 2).items()} for s in self.CORPUS]
        self.assertEqual(actual, expected)


class ProductionParserTests(unittest.TestCase):
    """Runs the real StrCombatConfigProvider entrypoint, with no stubs, where the Windows hooks import."""
    def test_apply_accepts_what_the_production_provider_parses(self):
        script = (
            'import json\n'
            'from src.config_combat import default_config\n'
            'from src.playstyle_validation import prepare_playstyle_application, validate_playstyle\n'
            'two = "###p1 storm\\nany<damage> @ enemy | pass\\n###p2\\npass"\n'
            'checks = [validate_playstyle(s).valid for s in ("pass", default_config, two)]\n'
            'configs, _ = prepare_playstyle_application(two, 3, default_config)\n'
            'bad = validate_playstyle("###p1\\nany<damage")\n'
            'print(json.dumps(dict(checks=checks, configs=configs, default=default_config, bad=bad.valid, line=bad.error.line)))\n')
        result = run_with_production_modules(script)
        self.assertEqual(result['checks'], [True, True, True])
        self.assertEqual(result['configs'], ['any<damage> @ enemy | pass', 'pass', result['default']])
        self.assertEqual((result['bad'], result['line']), (False, 2))


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    def context(self, source, clients, running=False):
        queue = Queue()
        ns = dict(com=SimpleNamespace(data={'source': source, 'request_id': 1}),
                  walker=SimpleNamespace(clients=clients), default_config='default',
                  combat_task=SimpleNamespace(done=lambda: False) if running else None,
                  freecam_status=False, gui_send_queue=queue, logger=Mock(),
                  toggle_combat_hotkey=AsyncMock(),
                  prepare_playstyle_application=lambda *a: prepare_playstyle_application(*a, parser=PARSE),
                  format_playstyle_error=format_playstyle_error,
                  deimosgui=SimpleNamespace(GUICommand=GUICommand, GUICommandType=GUICommandType),
                  _hooking_in_progress=set())
        upstream_function('_client_ready', ns)
        return ns, queue

    async def test_invalid_and_no_clients_do_not_toggle_or_retain_text(self):
        client = SimpleNamespace(combat_config='old', window_handle=1)
        for source, clients, state in [('any<bad>', [client], 'invalid'), ('pass', [], 'no_clients'), ('', [client], 'no_op')]:
            with self.subTest(state=state):
                ns, queue = self.context(source, clients, True)
                await dispatcher(ns)()
                self.assertEqual(queue.get_nowait().data['state'], state)
                self.assertEqual(client.combat_config, 'old')
                ns['toggle_combat_hotkey'].assert_not_awaited()

    async def test_success_preserves_off_on_and_freecam(self):
        for running, freecam, calls in [(False, False, 0), (True, False, 2), (True, True, 0)]:
            with self.subTest(running=running, freecam=freecam):
                clients = [SimpleNamespace(combat_config='old', window_handle=i) for i in range(2)]
                ns, queue = self.context('pass', clients, running)
                ns['freecam_status'] = freecam
                await dispatcher(ns)()
                result = queue.get_nowait().data
                self.assertEqual((result['state'], result['applied_clients']), ('applied', 2))
                self.assertEqual([c.combat_config for c in clients], ['pass', 'pass'])
                self.assertEqual(ns['toggle_combat_hotkey'].await_count, calls)

    async def test_success_uses_the_actual_upstream_toggle(self):
        clients = [SimpleNamespace(combat_config='old', combat_status=True, window_handle=1)]
        ns, queue = self.context('pass', clients, True)
        old = asyncio.create_task(asyncio.Event().wait())
        ns.update(combat_task=old, asyncio=asyncio, combat_loop=object(),
                  try_task_coro=lambda *args: asyncio.Event().wait())
        tree = ast.parse((ROOT / 'Deimos.py').read_text())
        toggle = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                      and n.name == 'toggle_combat_hotkey')
        # The current upstream toggle contains no await; this Apply transaction
        # cannot interleave another user toggle halfway through its two calls.
        self.assertFalse(any(isinstance(n, ast.Await) for n in ast.walk(toggle)))
        exec(compile(ast.Module(body=[toggle], type_ignores=[]), 'actual_upstream_toggle', 'exec'), ns)
        try:
            await dispatcher(ns)()
            messages = []
            while not queue.empty(): messages.append(queue.get_nowait())
            result = messages[-1].data
            self.assertEqual(result['state'], 'applied')
            self.assertTrue(clients[0].combat_status)
            self.assertIsNot(ns['combat_task'], old)
            self.assertFalse(ns['combat_task'].done())
        finally:
            old.cancel(); ns['combat_task'].cancel()
            await asyncio.gather(old, ns['combat_task'], return_exceptions=True)

    async def test_partial_rollback_continues_and_never_auto_recovers(self):
        class Stubborn:
            value = 'old'
            @property
            def combat_config(self): return self.value
            @combat_config.setter
            def combat_config(self, value):
                if value == 'old': raise RuntimeError('rollback refused')
                self.value = value
        bad, good = Stubborn(), SimpleNamespace(combat_config='old', window_handle=2)
        bad.window_handle = 1
        ns, queue = self.context('pass', [bad, good], True)
        ns['toggle_combat_hotkey'].side_effect = RuntimeError('restart failed')
        await dispatcher(ns)()
        result = queue.get_nowait().data
        self.assertEqual(result['state'], 'failed')
        self.assertFalse(result['configs_restored'])
        self.assertEqual(good.combat_config, 'old')
        self.assertEqual(ns['toggle_combat_hotkey'].await_count, 1)

    async def test_clients_still_hooking_are_rejected_without_mutation(self):
        ready = SimpleNamespace(combat_config='old', window_handle=1)
        uninitialized = SimpleNamespace(window_handle=2)
        mid_hook = SimpleNamespace(combat_config='old', window_handle=3)
        for pending in (uninitialized, mid_hook):
            with self.subTest(pending=pending.window_handle):
                ns, queue = self.context('pass', [ready, pending], True)
                ns['_hooking_in_progress'].add(3)
                await dispatcher(ns)()
                result = queue.get_nowait().data
                self.assertEqual(result['state'], 'hooking')
                self.assertEqual(ready.combat_config, 'old')
                self.assertEqual(len(ns['_hooking_in_progress']), 1)
                ns['toggle_combat_hotkey'].assert_not_awaited()

    async def test_failed_recovery_reports_combat_state(self):
        for ends_running, expected in [(True, True), (False, False)]:
            with self.subTest(ends_running=ends_running):
                ns, queue = self.context('pass', [SimpleNamespace(combat_config='old', window_handle=1)], True)
                async def stop_then_fail(*args):
                    if not ends_running: ns['combat_task'] = None
                    raise RuntimeError('restart failed')
                ns['toggle_combat_hotkey'].side_effect = stop_then_fail
                await dispatcher(ns)()
                result = queue.get_nowait().data
                self.assertEqual((result['state'], result['configs_restored'], result['combat_restored']),
                                 ('failed', True, expected))


class FeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.owner = QWidget()
        self.editor = QTextEdit(self.owner)
        self.editor.setPlainText('pass')
        self.feedback = PlaystyleApplyFeedback(self.editor, load_lang('en'), self.owner)
    def tearDown(self): self.owner.deleteLater(); self.app.processEvents()

    def test_no_live_validation_and_timeout_accepts_late_current_reply(self):
        self.editor.insertPlainText('more')
        self.assertIsNone(self.feedback.pending)
        self.assertEqual(self.feedback.label.text(), '')
        request = self.feedback.request()
        self.assertTrue(self.feedback.timer.isSingleShot())
        self.assertEqual(self.feedback.timer.interval(), 15000)
        self.feedback.timeout()
        self.assertEqual(self.feedback.label.text(), load_lang('en')('playstyle_apply_unconfirmed'))
        self.feedback.receive({**request, 'state': 'applied', 'applied_clients': 2})
        self.assertEqual(self.feedback.label.text(), 'Applied to 2 clients.')
        self.assertFalse(self.feedback.timer.isActive())

    def test_stale_and_same_text_older_replies_are_ignored(self):
        first = self.feedback.request(); second = self.feedback.request()
        self.feedback.receive({**first, 'state': 'applied', 'applied_clients': 1})
        self.assertEqual(self.feedback.label.text(), 'Applying playstyle...')
        self.feedback.receive({**second, 'state': 'applied', 'applied_clients': 1})
        self.assertEqual(self.feedback.label.text(), 'Applied to 1 client.')
        old = self.feedback.request(); self.editor.setPlainText('draw')
        self.feedback.receive({**old, 'state': 'applied', 'applied_clients': 1})
        self.assertEqual(self.feedback.label.text(), '')
        self.assertFalse(self.feedback.timer.isActive())

    def test_feedback_tracks_theme_without_losing_the_result(self):
        context = SimpleNamespace(theme='dark')
        self.feedback.context = context
        request = self.feedback.request()
        self.feedback.receive({**request, 'state': 'applied', 'applied_clients': 1})
        text = self.feedback.label.text()
        dark = self.feedback.label.styleSheet()
        context.theme = 'light'
        self.feedback.retheme()
        self.assertEqual(self.feedback.label.text(), text)
        self.assertNotEqual(self.feedback.label.styleSheet(), dark)

    def test_actual_tab_and_gui_queue_route_the_result(self):
        from PyQt6.QtWidgets import QPushButton
        from src.gui.tab_actions import build_combat_tab
        callbacks = []
        def action_button(svg, tooltip, callback):
            button = QPushButton(tooltip)
            button.clicked.connect(callback)
            callbacks.append(callback)
            return button
        queue = Queue()
        ctx = SimpleNamespace(window=self.owner, widget_tags={}, exports={}, tl=load_lang('en'),
                              svgs={key: '' for key in ('readme', 'recent', 'import', 'export', 'refresh')},
                              wiki_base='https://example.invalid', icon_btn_style='', send_queue=queue,
                              registry=SimpleNamespace(action_icon_btn=action_button))
        tab = build_combat_tab(ctx)
        ctx.widget_tags['combat_config'].setPlainText('pass')
        callbacks[-1]()
        command = queue.get_nowait()
        self.assertIs(command.com_type, GUICommandType.SetPlaystyles)
        result = {**command.data, 'state': 'applied', 'applied_clients': 1}
        source = ast.parse((ROOT / 'src/gui/main.py').read_text())
        case = next(n for n in ast.walk(source) if isinstance(n, ast.match_case)
                    and ast.unparse(n.pattern) == 'GUICommandType.PlaystyleValidationResult')
        ns = {'ctx': ctx, 'com': SimpleNamespace(data=result)}
        exec(compile(ast.Module(body=case.body, type_ignores=[]), 'actual_gui_result_case', 'exec'), ns)
        self.assertEqual(tab.findChild(type(self.feedback.label), 'playstyleApplyStatus').text(), 'Applied to 1 client.')
        tab.deleteLater()

    def test_failure_is_plain_text_localized_and_accurate(self):
        for lang in ('en', 'zh'):
            with self.subTest(lang=lang):
                self.feedback.tl = load_lang(lang)
                request = self.feedback.request()
                self.feedback.receive({**request, 'state': 'failed', 'configs_restored': False})
                self.assertIn(load_lang(lang)('playstyle_rollback_failed'), self.feedback.label.text())
                self.assertNotIn(load_lang(lang)('playstyle_active_unchanged'), self.feedback.label.text())

    def test_hooking_and_unconfirmed_combat_are_reported_plainly(self):
        for lang in ('en', 'zh'):
            with self.subTest(lang=lang):
                tl = load_lang(lang)
                self.feedback.tl = tl
                request = self.feedback.request()
                self.feedback.receive({**request, 'state': 'hooking'})
                self.assertEqual(self.feedback.label.text(), tl('playstyle_hooking'))
                self.assertEqual(self.feedback.state, 'neutral')
                request = self.feedback.request()
                self.feedback.receive({**request, 'state': 'failed', 'configs_restored': True, 'combat_restored': False})
                self.assertIn(tl('playstyle_active_unchanged'), self.feedback.label.text())
                self.assertIn(tl('playstyle_combat_unconfirmed'), self.feedback.label.text())
                request = self.feedback.request()
                self.feedback.receive({**request, 'state': 'failed', 'configs_restored': True})
                self.assertNotIn(tl('playstyle_combat_unconfirmed'), self.feedback.label.text())


if __name__ == '__main__': unittest.main()
