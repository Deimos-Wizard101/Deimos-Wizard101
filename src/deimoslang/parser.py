from enum import Enum, auto
from typing import Any

from .tokenizer import Token, TokenKind, LineInfo, render_tokens
from .types import *


class ParserError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0

    def _fetch_line_tokens(self, line: int) -> list[Token]:
        result = []
        for tok in self.tokens:
            if tok.line_info.line == line:
                result.append(tok)
        return result

    def err_manual(self, line_info: LineInfo, msg: str):
        line_toks = self._fetch_line_tokens(line_info.line)
        err_msg = msg
        err_msg += f"\n{render_tokens(line_toks)}"
        arrow_indent = " " * (line_info.column - 1)
        err_msg += f"\n{arrow_indent}^"
        raise ParserError(f"{err_msg}\nLine: {line_info.line}")

    def err(self, token: Token, msg: str):
        self.err_manual(token.line_info, msg)

    def skip_any(self, kinds: list[TokenKind]):
        if self.i < len(self.tokens) and self.tokens[self.i].kind in kinds:
            self.i += 1

    def skip_comma(self):
        self.skip_any([TokenKind.comma])

    def expect_consume_any(self, kinds: list[TokenKind]) -> Token:
        if self.i >= len(self.tokens):
            self.err(self.tokens[-1], f"Premature end of file, expected {kinds} before the end")
        result = self.tokens[self.i]
        if result.kind not in kinds:
            self.err(result, f"Expected token kinds {kinds} but got {result.kind}")
        self.i += 1
        return result
    def expect_consume(self, kind: TokenKind) -> Token:
        return self.expect_consume_any([kind])

    def consume_any_optional(self, kinds: list[TokenKind]) -> Token | None:
        if self.i >= len(self.tokens):
            return None
        result = self.tokens[self.i]
        if result.kind not in kinds:
            return None
        self.i += 1
        return result

    def consume_optional(self, kind: TokenKind) -> Token | None:
        return self.consume_any_optional([kind])

    def parse_atom(self) -> NumberExpression | StringExpression:
        tok = self.expect_consume_any([TokenKind.number, TokenKind.string, TokenKind.percent])
        match tok.kind:
            case TokenKind.number:
                return NumberExpression(tok.value)
            case TokenKind.percent:
                return NumberExpression(tok.value)
            case TokenKind.string:
                return StringExpression(tok.value)
            case _:
                self.err(tok, f"Invalid atom kind: {tok.kind} in {tok}")

    def parse_unary_expression(self) -> UnaryExpression | Expression:
        kinds = [TokenKind.minus]
        if self.tokens[self.i].kind in kinds:
            operator = self.expect_consume_any(kinds)
            return UnaryExpression(operator, self.parse_unary_expression())
        else:
            return self.parse_atom()

    def gen_greater_expression(self, left:Expression, right:Expression, player_selector: PlayerSelector):
        return SelectorGroup(player_selector, GreaterExpression(left, right))

    def gen_equivalent_expression(self, left:Expression, right:Expression, player_selector: PlayerSelector):
        return SelectorGroup(player_selector, EquivalentExpression(left, right))

    def parse_command_expression(self) -> Expression:
        result = Command()
        player_selector  = self.parse_player_selector()
        result.player_selector = player_selector

        match self.tokens[self.i].kind:
            case TokenKind.command_expr_window_visible:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.window_visible, self.parse_window_path()]
            case TokenKind.command_expr_in_zone:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.in_zone, self.parse_zone_path()]
            case TokenKind.command_expr_same_zone:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.same_zone]
            case TokenKind.command_expr_in_combat:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.in_combat]
            case TokenKind.command_expr_has_quest:
                result.kind = CommandKind.expr
                self.i += 1
                text: str = self.expect_consume(TokenKind.string).value # type: ignore
                result.data = [ExprKind.has_quest, text.lower()]
            case TokenKind.command_expr_has_dialogue:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.has_dialogue]
            case TokenKind.command_expr_loading:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.loading]
            case TokenKind.command_expr_has_xyz:
                result.kind = CommandKind.expr
                self.i += 1
                xyz = self.parse_xyz()
                result.data = [ExprKind.has_xyz, xyz]
            case TokenKind.command_expr_health_above:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.health), Eval(EvalKind.max_health))
                else:
                    evaluated = Eval(EvalKind.health)

                # evaluated_value > target_value
                return self.gen_greater_expression(evaluated, target, player_selector)
            case TokenKind.command_expr_health_below:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.health), Eval(EvalKind.max_health))
                else:
                    evaluated = Eval(EvalKind.health)

                # target > evaluated
                return self.gen_greater_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_health:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.health), Eval(EvalKind.max_health))
                else:
                    evaluated = Eval(EvalKind.health)

                # target == evaluated
                return self.gen_equivalent_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_mana_above:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.mana), Eval(EvalKind.max_mana))
                else:
                    evaluated = Eval(EvalKind.mana)

                # evaluated > target
                return self.gen_greater_expression(evaluated, target, player_selector)
            case TokenKind.command_expr_mana_below:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.mana), Eval(EvalKind.max_mana))
                else:
                    evaluated = Eval(EvalKind.mana)

                # target > evaluated
                return self.gen_greater_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_mana:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.mana), Eval(EvalKind.max_mana))
                else:
                    evaluated = Eval(EvalKind.mana)

            case TokenKind.command_expr_energy_above:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.energy), Eval(EvalKind.energy))
                else:
                    evaluated = Eval(EvalKind.energy)

                # evaluated > target
                return self.gen_greater_expression(evaluated, target, player_selector)
            case TokenKind.command_expr_energy_below:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.energy), Eval(EvalKind.max_energy))
                else:
                    evaluated = Eval(EvalKind.energy)

                # target > evaluated
                return self.gen_greater_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_energy:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.energy), Eval(EvalKind.max_energy))
                else:
                    evaluated = Eval(EvalKind.energy)
                    
                # target == evaluated
                return self.gen_equivalent_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_bagcount_above:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.bagcount), Eval(EvalKind.max_bagcount))
                else:
                    evaluated = Eval(EvalKind.bagcount)

                # evaluated_value > target_value
                return self.gen_greater_expression(evaluated, target, player_selector)
            case TokenKind.command_expr_bagcount_below:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.bagcount), Eval(EvalKind.max_bagcount))
                else:
                    evaluated = Eval(EvalKind.bagcount)

                # target > evaluated
                return self.gen_greater_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_bagcount:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.bagcount), Eval(EvalKind.max_bagcount))
                else:
                    evaluated = Eval(EvalKind.bagcount)

                # target == evaluated
                return self.gen_equivalent_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_gold_above:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.gold), Eval(EvalKind.max_gold))
                else:
                    evaluated = Eval(EvalKind.gold)

                # evaluated_value > target_value
                return self.gen_greater_expression(evaluated, target, player_selector)
            case TokenKind.command_expr_gold_below:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.gold), Eval(EvalKind.max_gold))
                else:
                    evaluated = Eval(EvalKind.gold)

                # target > evaluated
                return self.gen_greater_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_gold:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.gold), Eval(EvalKind.max_gold))
                else:
                    evaluated = Eval(EvalKind.gold)

                # target == evaluated
                return self.gen_equivalent_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_window_text:
                self.i += 1
                window_path = self.parse_window_path()
                contains = self.consume_optional(TokenKind.contains)
                target = self.expect_consume(TokenKind.string)
                assert(type(window_path) == list and type(target.value) == str)
                if contains:
                    return SelectorGroup(player_selector, ContainsStringExpression(Eval(EvalKind.windowtext, [window_path]), StringExpression(target.value.lower())))
                else:
                    return SelectorGroup(player_selector, EquivalentExpression(Eval(EvalKind.windowtext, [window_path]), StringExpression(target.value.lower())))
            case TokenKind.command_expr_playercount:
                self.i += 1
                num = self.expect_consume(TokenKind.number)
                assert(num.value!=None)
                target = NumberExpression(num.value)
                evaluated = Eval(EvalKind.playercount)

                # target == evaluated
                return self.gen_equivalent_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_playercountabove:
                self.i += 1
                num = self.expect_consume(TokenKind.number)
                assert(num.value!=None)
                target = NumberExpression(num.value)
                evaluated = Eval(EvalKind.playercount)

                # evaluated_value > target_value
                return self.gen_greater_expression(evaluated, target, player_selector)
            case TokenKind.command_expr_playercountbelow:
                self.i += 1
                num = self.expect_consume(TokenKind.number)
                assert(num.value!=None)
                target = NumberExpression(num.value)
                evaluated = Eval(EvalKind.playercount)

                # target > evaluated
                return self.gen_greater_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_window_disabled:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.window_disabled, self.parse_window_path()]
            case TokenKind.command_expr_in_range:
                result.kind = CommandKind.expr
                self.i += 1
                text: str = self.expect_consume(TokenKind.string).value # type: ignore
                result.data = [ExprKind.in_range, text.lower()]
            case TokenKind.command_expr_same_place:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.same_place]
            case TokenKind.command_expr_tracking_quest:
                result.kind = CommandKind.expr
                self.i += 1
                text: str = self.expect_consume(TokenKind.string).value # type: ignore
                result.data = [ExprKind.tracking_quest, text.lower()]
            case TokenKind.command_expr_tracking_goal:
                result.kind = CommandKind.expr
                self.i += 1
                text: str = self.expect_consume(TokenKind.string).value # type: ignore
                result.data = [ExprKind.tracking_goal, text.lower()]
            case TokenKind.command_expr_potion_count:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.potioncount), Eval(EvalKind.max_potioncount))
                else:
                    evaluated = Eval(EvalKind.potioncount)

                # target == evaluated
                return self.gen_equivalent_expression(target, evaluated, player_selector)
            case TokenKind.command_expr_potion_countabove:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.potioncount), Eval(EvalKind.max_potioncount))
                else:
                    evaluated = Eval(EvalKind.potioncount)

                # evaluated_value > target_value
                return self.gen_greater_expression(evaluated, target, player_selector)
            case TokenKind.command_expr_potion_countbelow:
                self.i += 1
                num = self.expect_consume_any([TokenKind.number, TokenKind.percent])
                assert(num.value!=None)
                target = NumberExpression(num.value)

                if num.kind == TokenKind.percent:
                    evaluated = DivideExpression(Eval(EvalKind.potioncount), Eval(EvalKind.max_potioncount))
                else:
                    evaluated = Eval(EvalKind.potioncount)

                # target > evaluated
                return self.gen_greater_expression(target, evaluated, player_selector)
            case _:
                return self.parse_unary_expression()

        return CommandExpression(result)

    def parse_negation_expression(self) -> Expression:
        kinds = [TokenKind.keyword_not]
        if self.tokens[self.i].kind in kinds:
            operator = self.expect_consume_any(kinds)
            return UnaryExpression(operator, self.parse_command_expression())
        else:
            return self.parse_command_expression()

    def parse_expression(self) -> Expression:
        return self.parse_negation_expression()

    def parse_player_selector(self) -> PlayerSelector:
        result = PlayerSelector()
        valid_toks = [TokenKind.keyword_mass, TokenKind.keyword_except, TokenKind.player_num, TokenKind.player_wildcard, TokenKind.colon]
        expected_toks = [TokenKind.keyword_mass, TokenKind.keyword_except, TokenKind.player_num, TokenKind.player_wildcard]
        while self.i < len(self.tokens) and self.tokens[self.i].kind in valid_toks:
            if self.tokens[self.i].kind not in expected_toks:
                self.err(self.tokens[self.i], f"Invalid player selector encountered: {self.tokens[self.i]}")
            match self.tokens[self.i].kind:
                case TokenKind.keyword_mass:
                    result.mass = True
                    expected_toks = []
                    self.i += 1
                case TokenKind.keyword_except:
                    result.inverted = True
                    expected_toks = [TokenKind.player_num]
                    self.i += 1
                case TokenKind.player_num:
                    result.player_nums.append(int(self.tokens[self.i].value))
                    expected_toks = [TokenKind.colon]
                    self.i += 1
                case TokenKind.player_wildcard:
                    result.wildcard = True
                    expected_toks = []
                    self.i += 1
                case TokenKind.colon:
                    expected_toks = [TokenKind.player_num]
                    self.i += 1
                case _:
                    assert False
        result.validate()
        if len(result.player_nums) == 0 and not result.wildcard:
            result.mass = True
        result.validate() # sanity check
        return result

    def parse_key(self) -> KeyExpression:
        # We must accept kill as well here as there is a naming collision for END
        tok = self.expect_consume_any([TokenKind.identifier, TokenKind.command_kill])
        tok.kind = TokenKind.identifier
        return KeyExpression(tok.literal)

    def parse_xyz(self) -> XYZExpression:
        start_tok = self.expect_consume(TokenKind.keyword_xyz)
        vals = []
        valid_toks = [TokenKind.paren_open, TokenKind.paren_close, TokenKind.comma, TokenKind.number, TokenKind.minus]
        expected_toks = [TokenKind.paren_open]
        found_closing = False
        while self.i < len(self.tokens) and self.tokens[self.i].kind in valid_toks:
            if self.tokens[self.i].kind not in expected_toks:
                self.err(self.tokens[self.i], f"Invalid xyz encountered")
            match self.tokens[self.i].kind:
                case TokenKind.paren_open:
                    self.i += 1
                    expected_toks = [TokenKind.comma, TokenKind.number, TokenKind.paren_close, TokenKind.minus]
                case TokenKind.paren_close:
                    self.i += 1
                    expected_toks = []
                    found_closing = True
                case TokenKind.comma | TokenKind.number | TokenKind.minus:
                    if self.tokens[self.i].kind == TokenKind.comma:
                        vals.append(NumberExpression(0.0))
                        self.i += 1
                    else:
                        vals.append(self.parse_expression())
                        if self.tokens[self.i].kind == TokenKind.comma:
                            self.i += 1
                    expected_toks = [TokenKind.comma, TokenKind.paren_close, TokenKind.number, TokenKind.minus]
        if not found_closing:
            self.err(start_tok, "Encountered unclosed XYZ")
        if len(vals) != 3:
            self.err(start_tok, f"Encountered invalid XYZ")
        return XYZExpression(*vals)

    def parse_completion_optional(self) -> bool:
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.keyword_completion:
            self.i += 1
            return True
        return False

    def parse_zone_path_optional(self) -> list[str] | None:
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.path:
            result = self.tokens[self.i]
            self.i += 1
            return result.value
        return None

    def parse_zone_path(self) -> list[str] | None:
        res = self.parse_zone_path_optional()
        if res is None:
            self.err(
                self.tokens[self.i] if self.i < len(self.tokens) else self.tokens[-1],
                "Failed to parse zone path"
            )
        return res

    def parse_list(self) -> list[Expression]:
        result = []
        self.expect_consume(TokenKind.square_open)
        while self.i < len(self.tokens) and self.tokens[self.i].kind != TokenKind.square_close:
            if self.tokens[self.i].kind != TokenKind.comma:
                result.append(self.parse_atom())
            else:
                self.i += 1
        self.expect_consume(TokenKind.square_close)
        return result

    def parse_window_path(self) -> list[str]:
        result = []
        for x in self.parse_list():
            if not isinstance(x, StringExpression):
                raise ParserError(f"Unexpected expression type: {x}")
            result.append(x.string)
        return result

    def end_line(self):
        self.expect_consume(TokenKind.END_LINE)

    def end_line_optional(self):
        if self.tokens[self.i].kind == TokenKind.END_LINE:
            self.i += 1

    def parse_command(self) -> Command:
        result = Command()
        result.player_selector = self.parse_player_selector()

        match self.tokens[self.i].kind:
            case TokenKind.command_kill:
                result.kind = CommandKind.kill
                self.i += 1
                self.end_line()
            case TokenKind.command_log:
                self.i += 1
                kind = self.tokens[self.i].kind
                result.kind = CommandKind.log
                def print_literal():
                    final_str = ""
                    while self.tokens[self.i].kind != TokenKind.END_LINE:
                        tok = self.tokens[self.i]
                        match tok.kind:
                            case TokenKind.string:
                                final_str += f"{tok.value} "
                            case _:
                                final_str += f"{tok.literal} "
                        self.i += 1
                    result.data = [LogKind.single, StringExpression(final_str)]
                match kind:
                    case TokenKind.identifier:
                        if self.tokens[self.i].literal == "window":
                            self.i += 1
                            window_path = self.parse_window_path()
                            result.data = [LogKind.multi, StrFormatExpression("windowtext: %s", Eval(EvalKind.windowtext, window_path))]
                        else:
                            print_literal()
                    case TokenKind.command_expr_bagcount:
                        self.i += 1
                        result.data = [LogKind.multi, StrFormatExpression("bagcount: %d/%d", Eval(EvalKind.bagcount),Eval(EvalKind.max_bagcount))]
                    case TokenKind.command_expr_mana:
                        self.i += 1
                        result.data = [LogKind.multi, StrFormatExpression("mana: %d/%d", Eval(EvalKind.mana), Eval(EvalKind.max_mana))]
                    case TokenKind.command_expr_energy:
                        self.i += 1
                        result.data = [LogKind.multi, StrFormatExpression("energy: %d/%d", Eval(EvalKind.energy), Eval(EvalKind.max_energy))]
                    case TokenKind.command_expr_health:
                        self.i += 1
                        result.data = [LogKind.multi, StrFormatExpression("health: %d/%d", Eval(EvalKind.health), Eval(EvalKind.max_health))]
                    case TokenKind.command_expr_gold:
                        self.i += 1
                        result.data = [LogKind.multi, StrFormatExpression("gold: %d/%d", Eval(EvalKind.gold), Eval(EvalKind.max_gold))]
                    case TokenKind.command_expr_potion_count:
                        self.i += 1
                        result.data = [LogKind.multi, StrFormatExpression("potioncount: %d/%d", Eval(EvalKind.potioncount), Eval(EvalKind.max_potioncount))]
                    case TokenKind.command_expr_playercount:
                        self.i += 1
                        result.data = [LogKind.single, StrFormatExpression("playercount: %d", Eval(EvalKind.playercount))]
                    case TokenKind.command_expr_window_text:
                        self.i += 1
                        window_path = self.parse_window_path()
                        result.data = [LogKind.multi, StrFormatExpression("windowtext: %s", Eval(EvalKind.windowtext, [window_path]))]
                    case TokenKind.string:
                        print_literal()
                    case _:
                        print_literal()
                self.end_line()
            case TokenKind.command_teleport:
                result.kind = CommandKind.teleport
                self.i += 1
                if self.consume_optional(TokenKind.keyword_mob) is not None:
                    result.data = [TeleportKind.mob]
                elif self.consume_optional(TokenKind.keyword_quest) is not None:
                    result.data = [TeleportKind.quest]
                elif num_tok := self.consume_optional(TokenKind.player_num):
                    result.data = [TeleportKind.client_num, num_tok.value]
                else:
                    result.data = [TeleportKind.position, self.parse_xyz()]
                self.end_line()
            case TokenKind.command_sleep:
                result.kind = CommandKind.sleep
                self.i += 1
                result.data = [self.parse_expression()]
                self.end_line()
            case TokenKind.command_sendkey:
                result.kind = CommandKind.sendkey
                self.i += 1
                result.data.append(self.parse_key())
                self.skip_comma()
                if self.tokens[self.i].kind != TokenKind.END_LINE:
                    result.data.append(self.parse_expression())
                else:
                    result.data.append(None)
                self.end_line()
            case TokenKind.command_waitfor_zonechange:
                result.kind = CommandKind.waitfor
                self.i += 1
                result.data = [WaitforKind.zonechange, self.parse_completion_optional()]
                self.end_line()
            case TokenKind.command_waitfor_battle:
                result.kind = CommandKind.waitfor
                self.i += 1
                result.data = [WaitforKind.battle, self.parse_completion_optional()]
                self.end_line()
            case TokenKind.command_waitfor_window:
                result.kind = CommandKind.waitfor
                self.i += 1
                result.data = [WaitforKind.window, self.parse_window_path(), self.parse_completion_optional()]
                self.end_line()
            case TokenKind.command_waitfor_free:
                result.kind = CommandKind.waitfor
                self.i += 1
                result.data = [WaitforKind.free, self.parse_completion_optional()]
                self.end_line()
            case TokenKind.command_waitfor_dialog:
                result.kind = CommandKind.waitfor
                self.i += 1
                result.data = [WaitforKind.dialog, self.parse_completion_optional()]
                self.end_line()
            case TokenKind.command_goto:
                result.kind = CommandKind.goto
                self.i += 1
                result.data = [self.parse_xyz()]
                self.end_line()
            case TokenKind.command_clickwindow:
                result.kind = CommandKind.click
                self.i += 1
                result.data = [ClickKind.window, self.parse_window_path()]
                self.end_line()
            case TokenKind.command_usepotion:
                result.kind = CommandKind.usepotion
                self.i += 1
                health_arg = self.consume_optional(TokenKind.number)
                if health_arg != None:
                    self.skip_comma()
                    mana_arg = self.expect_consume(TokenKind.number)
                    result.data = [NumberExpression(health_arg.value), NumberExpression(mana_arg.value)]
                self.end_line()
            case TokenKind.command_buypotions:
                result.kind = CommandKind.buypotions
                self.i += 1
                if_needed_arg = self.consume_optional(TokenKind.keyword_ifneeded)
                result.data = [if_needed_arg is not None]
                self.end_line()
            case TokenKind.command_relog:
                result.kind = CommandKind.relog
                self.i += 1
                self.end_line()
            case TokenKind.command_click:
                result.kind = CommandKind.click
                self.i += 1
                x = self.expect_consume(TokenKind.number)
                self.skip_comma()
                y = self.expect_consume(TokenKind.number)
                result.data = [ClickKind.position, x.value, y.value]
                self.end_line()
            case TokenKind.command_friendtp:
                result.kind = CommandKind.teleport
                self.i += 1
                x = self.expect_consume_any([TokenKind.keyword_icon, TokenKind.identifier])
                if x.kind == TokenKind.keyword_icon:
                    result.data = [TeleportKind.friend_icon]
                else:
                    name_parts = [x.literal]
                    while self.tokens[self.i].kind != TokenKind.END_LINE:
                        name_parts.append(self.tokens[self.i].literal)
                        self.i += 1
                    result.data = [TeleportKind.friend_name, " ".join(name_parts)]
                self.end_line()
            case TokenKind.command_entitytp:
                result.kind = CommandKind.teleport
                self.i += 1
                arg = self.consume_optional(TokenKind.string)
                if arg is not None:
                    result.data = [TeleportKind.entity_literal, arg.value]
                else:
                    result.data = [TeleportKind.entity_vague, self.consume_any_ident().ident]
                self.end_line()
            case TokenKind.command_tozone:
                result.kind = CommandKind.tozone
                self.i += 1
                result.data = [self.parse_zone_path()]
                self.end_line()
            case TokenKind.command_load_playstyle:
                result.kind = CommandKind.load_playstyle
                self.i += 1
                result.data = [self.expect_consume(TokenKind.string).value]
                self.end_line()
            case TokenKind.command_set_yaw:
                result.kind = CommandKind.set_yaw
                self.i += 1
                result.data = [self.expect_consume(TokenKind.number).value]
                self.end_line()
            case _:
                self.err(self.tokens[self.i], "Unhandled command token")
        return result

    def parse_block(self) -> StmtList:
        inner = []
        self.expect_consume(TokenKind.curly_open)
        self.end_line_optional()
        while self.i < len(self.tokens) and self.tokens[self.i].kind != TokenKind.curly_close:
            inner.append(self.parse_stmt())
        self.expect_consume(TokenKind.curly_close)
        self.end_line_optional()
        return StmtList(inner)

    def consume_any_ident(self) -> IdentExpression:
        result = self.tokens[self.i]
        if result.kind != TokenKind.identifier and "keyword" not in result.kind.name and "command" not in result.kind.name:
            self.err(result, "Unable to consume an identifier")
        self.i += 1
        return IdentExpression(result.literal)

    def parse_stmt(self) -> Stmt:
        match self.tokens[self.i].kind:
            case TokenKind.keyword_block:
                self.i += 1
                ident = self.consume_any_ident()
                body = self.parse_block()
                return BlockDefStmt(ident, body)
            case TokenKind.keyword_call:
                self.i += 1
                ident = self.consume_any_ident()
                self.end_line()
                return CallStmt(ident)
            case TokenKind.keyword_loop:
                self.i += 1
                body = self.parse_block()
                return LoopStmt(body)
            case TokenKind.keyword_while:
                self.i += 1
                expr = self.parse_expression()
                body = self.parse_block()
                return WhileStmt(expr, body)
            case TokenKind.keyword_until:
                self.i += 1
                expr = self.parse_expression()
                body = self.parse_block()
                return UntilStmt(expr, body)
            case TokenKind.keyword_times:
                self.i += 1
                count = int(self.expect_consume(TokenKind.number).value)
                body = self.parse_block()
                return TimesStmt(count, body)
            case TokenKind.keyword_if:
                self.i += 1
                expr = self.parse_expression()
                true_body = self.parse_block()
                elif_body_stack: list[IfStmt] = []
                else_body = StmtList([])
                while self.i < len(self.tokens) and self.tokens[self.i].kind in [TokenKind.keyword_else, TokenKind.keyword_elif]:
                    if self.tokens[self.i].kind == TokenKind.keyword_else:
                        self.i += 1
                        else_body = self.parse_block()
                        break
                    elif self.tokens[self.i].kind == TokenKind.keyword_elif:
                        self.i += 1
                        elif_expr = self.parse_expression()
                        elif_body = self.parse_block()
                        elif_stmt = IfStmt(elif_expr, elif_body, StmtList([]))
                        if len(elif_body_stack) > 0:
                            elif_body_stack[-1].branch_false = StmtList([elif_stmt])
                        elif_body_stack.append(elif_stmt)
                if len(elif_body_stack) > 0:
                    elif_body_stack[-1].branch_false = else_body
                    else_body = StmtList([elif_body_stack[0]])

                return IfStmt(expr, true_body, else_body)
            case TokenKind.keyword_break:
                self.i += 1
                self.end_line()
                return BreakStmt()
            case TokenKind.keyword_return:
                self.i += 1
                self.end_line()
                return ReturnStmt()
            case TokenKind.keyword_mixin:
                self.i += 1
                ident = self.consume_any_ident()
                self.end_line()
                return MixinStmt(ident.ident)
            case _:
                return CommandStmt(self.parse_command())

    def parse(self) -> list[Stmt]:
        result = []
        while self.i < len(self.tokens):
            stmt = self.parse_stmt()
            result.append(stmt)
        return result
def add_indent(string, indent):
    for _ in range(indent):
        string += '    '
    return string

def print_cmd(input_str:str):
    final_string = ""
    indent = 0
    idx = 0

    while idx < len(input_str):
        ch = input_str[idx]
        if ch == '{':
            indent += 1
            final_string += f'{ch}\n'
            final_string = add_indent(final_string, indent)
        elif ch == '}':
            if idx < len(input_str)-1 and (ch=='}' and input_str[idx+1] == ';'):
                indent -= 1
                final_string += '\n'
                final_string = add_indent(final_string, indent)
                final_string += f'{ch}'
                final_string += f'{input_str[idx+1]}\n'
                idx+=1
                final_string = add_indent(final_string, indent)
            else:
                indent -= 1
                final_string += '\n'
                final_string = add_indent(final_string, indent)
                final_string += f'{ch}\n'
                final_string = add_indent(final_string, indent)
        elif ch == ';':
            final_string += f'{ch}\n'
            final_string = add_indent(final_string, indent)
        else:
            final_string += ch

        idx+=1
    print(final_string)

if __name__ == "__main__":
    from .tokenizer import Tokenizer
    from pathlib import Path

    toks = Tokenizer().tokenize(Path("./deimoslang/testbot.txt").read_text())
    parser = Parser(toks)
    parsed = (parser.parse())
    for parse in parsed:
        print_cmd(str(parse))
