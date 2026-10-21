"""Non-executing validation and atomic preparation of Combat editor text."""
from dataclasses import dataclass
import re

from lark.exceptions import UnexpectedEOF

from src.combat_sections import scan_combat_configs


@dataclass(frozen=True)
class PlaystyleError:
    message: str
    line: int | None = 1
    column: int | None = 1
    player: int | None = None


@dataclass(frozen=True)
class PlaystyleValidation:
    source: str
    sections: tuple[tuple[int | None, str], ...] = ()
    error: PlaystyleError | None = None
    warnings: tuple[str, ...] = ()

    @property
    def valid(self):
        return self.error is None

    @property
    def no_op(self):
        return self.valid and not self.source.strip()

    def message(self):
        if self.error:
            e = self.error
            player = f' (p{e.player})' if e.player else ''
            location = f'line {e.line}, column {e.column}: ' if e.line is not None else ''
            return f'Invalid{player}: {location}{e.message}'
        if self.no_op:
            return 'Valid: no playstyle changes.'
        return 'Valid syntax. ' + ' '.join(self.warnings)


def _runtime_parse(text):
    # Lazy import: GUI construction does not require client hooks or runtime imports.
    from src.config_combat import StrCombatConfigProvider
    return StrCombatConfigProvider(text).config


def _parse_error(exc, text):
    """Return (message, line, column) for a parser failure, in coordinates local to `text`."""
    original = getattr(exc, 'orig_exc', exc)
    metadata = getattr(getattr(exc, 'obj', None), 'meta', None)
    line = column = None
    if isinstance(original, UnexpectedEOF):
        text_lines = text.split('\n')
        line = len(text_lines)
        column = len(text_lines[-1].removesuffix('\r')) + 1
    else:
        for location in (original, exc, metadata):
            candidate_line = getattr(location, 'line', None)
            candidate_column = getattr(location, 'column', None)
            if (isinstance(candidate_line, int) and candidate_line > 0
                    and isinstance(candidate_column, int) and candidate_column > 0):
                line, column = candidate_line, candidate_column
                break
    message = str(original).split('\n')[0] or type(original).__name__
    # Lark's message can repeat section-local coordinates. Callers report the
    # original editor coordinates instead.
    message = re.sub(r',? at line \d+ col(?:umn)? \d+\s*$', '', message)
    return message, line, column


def validate_playstyle(source, *, parser=None):
    """Parse every player section with original file coordinates; never mutate clients."""
    parser = parser or _runtime_parse
    if not isinstance(source, str):
        return PlaystyleValidation('', error=PlaystyleError('Expected text'))
    if not source.strip():
        return PlaystyleValidation(source)
    # Sections come from the same scan that assigns them to clients at Apply, so
    # what is validated is exactly what each client receives.
    configs, first_lines, explicit = scan_combat_configs(source)
    sections = sorted(((index + 1 if explicit else None, first_lines[index], text)
                       for index, text in configs.items()), key=lambda section: section[1])
    warnings = []
    for player, line_start, text in sections:
        if not text.strip():
            return PlaystyleValidation(source, error=PlaystyleError('Empty playstyle section', line_start, player=player))
        try:
            config = parser(text)
        except Exception as exc:
            message, line, column = _parse_error(exc, text)
            return PlaystyleValidation(source, error=PlaystyleError(
                message, line_start + line - 1 if line is not None else None,
                column if line is not None else None, player,
            ))
        if not config.infinite_rounds and not config.specific_rounds:
            return PlaystyleValidation(source, error=PlaystyleError('No executable rounds', line_start, player=player))
        if not config.infinite_rounds:
            warnings.append(f'{"p" + str(player) + ": " if player else ""}Only explicit rounds; add a fallback round to avoid exhaustion.')
    return PlaystyleValidation(source, tuple((p, text) for p, _, text in sections), warnings=tuple(warnings))


def prepare_playstyle_application(source, client_count, default_config, *, parser=None):
    """Return all assignments only after every section passes validation."""
    result = validate_playstyle(source, parser=parser)
    if not result.valid:
        return None, result
    if result.no_op:
        return [], result
    sections = dict(result.sections)
    if None in sections:
        return [sections[None]] * client_count, result
    return [sections.get(index + 1, default_config) for index in range(client_count)], result


def format_playstyle_error(result):
    message = result.message()
    if result.error and result.error.line is not None:
        lines = result.source.split('\n')
        if 1 <= result.error.line <= len(lines):
            message += '\n' + lines[result.error.line - 1].removesuffix('\r')
    return message
