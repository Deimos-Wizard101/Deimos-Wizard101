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
    
    def parse_numeric_comparison(self, evaluated, player_selector):
        if self.i < len(self.tokens) and self.tokens[self.i].kind in [TokenKind.greater, TokenKind.less, TokenKind.equals]:
            operator = self.tokens[self.i]
            self.i += 1

            target = self.parse_expression()
            
            if operator.kind == TokenKind.greater:
                return self.gen_greater_expression(evaluated, target, player_selector)
            elif operator.kind == TokenKind.less:
                return self.gen_greater_expression(target, evaluated, player_selector)
            elif operator.kind == TokenKind.equals:
                return self.gen_equivalent_expression(evaluated, target, player_selector)
        
        elif self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.keyword_isbetween:
            self.i += 1

            if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.identifier:
                range_ident = self.tokens[self.i].literal
                self.i += 1

                range_expr = IdentExpression(range_ident)

                min_expr = self.gen_greater_expression(evaluated, 
                            IndexAccessExpression(range_expr, NumberExpression(0)), player_selector)
                max_expr = self.gen_greater_expression(
                            IndexAccessExpression(range_expr, NumberExpression(1)), evaluated, player_selector)
                
                return AndExpression([min_expr, max_expr])
            else:
                range_str = self.expect_consume(TokenKind.string).value
                
                try:
                    min_val, max_val = map(float, range_str.split('-'))
                    
                    min_expr = self.gen_greater_expression(evaluated, NumberExpression(min_val), player_selector)
                    max_expr = self.gen_greater_expression(NumberExpression(max_val), evaluated, player_selector)
                    
                    return AndExpression([min_expr, max_expr])
                except ValueError:
                    self.err(self.tokens[self.i-1], f"Invalid range format: {range_str}. Expected format like '1-100'")
        else:
            return SelectorGroup(player_selector, evaluated)
        
        return SelectorGroup(player_selector, evaluated)

    def parse_indexed_numeric_comparison(self, evaluated, player_selector):
        # Important for the windownum case when checking paths that contains "36/100" (seperated numbers)
        # This also works for single numbers
        # TODO: Maybe refactor this and parse_numeric_comparison to condense code?
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.square_open:
            self.i += 1 
            
            expressions = []
            index = 0
            
            while self.i < len(self.tokens) and self.tokens[self.i].kind != TokenKind.square_close:
                if self.tokens[self.i].kind == TokenKind.comma:
                    self.i += 1
                    continue
                    
                indexed_eval = IndexAccessExpression(evaluated, NumberExpression(index))
                
                if self.tokens[self.i].kind in [TokenKind.greater, TokenKind.less, TokenKind.equals]:
                    operator = self.tokens[self.i]
                    self.i += 1
                    target = self.parse_expression()
                    
                    if operator.kind == TokenKind.greater:
                        expressions.append(self.gen_greater_expression(indexed_eval, target, player_selector))
                    elif operator.kind == TokenKind.less:
                        expressions.append(self.gen_greater_expression(target, indexed_eval, player_selector))
                    else:  # equals
                        expressions.append(self.gen_equivalent_expression(indexed_eval, target, player_selector))
                        
                elif self.tokens[self.i].kind == TokenKind.keyword_isbetween:
                    self.i += 1
    
                    if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.identifier:
                        range_ident = self.tokens[self.i].literal
                        self.i += 1
    
                        range_expr = IdentExpression(range_ident)
    
                        # For a variable reference like BetweenVal, we need to:
                        # 1. Parse the string at runtime (e.g., "99-101")
                        # 2. Extract min and max values
                        # 3. Compare with the indexed value
                        
                        # Create a special expression for range checking with a variable
                        min_expr = self.gen_greater_expression(indexed_eval, 
                                    RangeMinExpression(range_expr), player_selector)
                        max_expr = self.gen_greater_expression(
                                    RangeMaxExpression(range_expr), indexed_eval, player_selector)
                        
                        expressions.append(AndExpression([min_expr, max_expr]))
                    else:
                        range_str = self.expect_consume(TokenKind.string).value
                        
                        try:
                            min_val, max_val = map(float, range_str.split('-'))
                            min_expr = self.gen_greater_expression(indexed_eval, NumberExpression(min_val), player_selector)
                            max_expr = self.gen_greater_expression(NumberExpression(max_val), indexed_eval, player_selector)
                            expressions.append(AndExpression([min_expr, max_expr]))
                        except ValueError:
                            self.err(self.tokens[self.i-1], f"Invalid range format: {range_str}. Expected format like '1-100'")
                else:
                    expressions.append(self.gen_equivalent_expression(indexed_eval, self.parse_expression(), player_selector))
                    
                index += 1
                
                # Check for comma after each comparison
                if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.comma:
                    self.i += 1
            
            self.expect_consume(TokenKind.square_close)
            
            # For multiple expressions, we need ALL of them to be true (AND)
            if len(expressions) == 1:
                return expressions[0]
            return AndExpression(expressions)
        
        return self.parse_numeric_comparison(IndexAccessExpression(evaluated, NumberExpression(0)), player_selector)
    
    def gen_range_check_expression(self, value: Expression, range_ident: IdentExpression, player_selector: PlayerSelector) -> Expression:
        return SelectorGroup(player_selector, 
                            ContainsStringExpression(range_ident, value))
    
    def get_stat_eval_expression(self, token_kind: TokenKind, is_percent: bool) -> Expression:
        if token_kind in [TokenKind.command_expr_health, TokenKind.command_expr_health_above, TokenKind.command_expr_health_below]:
            if is_percent:
                return DivideExpression(Eval(EvalKind.health), Eval(EvalKind.max_health))
            else:
                return Eval(EvalKind.health)
        elif token_kind in [TokenKind.command_expr_mana, TokenKind.command_expr_mana_above, TokenKind.command_expr_mana_below]:
            if is_percent:
                return DivideExpression(Eval(EvalKind.mana), Eval(EvalKind.max_mana))
            else:
                return Eval(EvalKind.mana)
        elif token_kind in [TokenKind.command_expr_energy, TokenKind.command_expr_energy_above, TokenKind.command_expr_energy_below]:
            if is_percent:
                return DivideExpression(Eval(EvalKind.energy), Eval(EvalKind.max_energy))
            else:
                return Eval(EvalKind.energy)
        elif token_kind in [TokenKind.command_expr_bagcount, TokenKind.command_expr_bagcount_above, TokenKind.command_expr_bagcount_below]:
            if is_percent:
                return DivideExpression(Eval(EvalKind.bagcount), Eval(EvalKind.max_bagcount))
            else:
                return Eval(EvalKind.bagcount)
        elif token_kind in [TokenKind.command_expr_gold, TokenKind.command_expr_gold_above, TokenKind.command_expr_gold_below]:
            if is_percent:
                return DivideExpression(Eval(EvalKind.gold), Eval(EvalKind.max_gold))
            else:
                return Eval(EvalKind.gold)
        elif token_kind == TokenKind.command_expr_account_level:
            return Eval(EvalKind.account_level)
        elif token_kind in [TokenKind.command_expr_potion_count, TokenKind.command_expr_potion_countbelow, TokenKind.command_expr_potion_countabove]:
            if is_percent:
                return DivideExpression(Eval(EvalKind.potioncount), Eval(EvalKind.max_potioncount))
            else:
                return Eval(EvalKind.potioncount)
        elif token_kind == TokenKind.command_expr_playercount:
            return Eval(EvalKind.playercount)
        elif token_kind == TokenKind.command_expr_window_text:
            return Eval(EvalKind.windowtext, self.parse_value(['window_path']))
        elif token_kind == TokenKind.command_expr_window_num:
            return Eval(EvalKind.windownum, self.parse_value(['window_path']))
        elif token_kind == TokenKind.command_expr_duel_round:
            return Eval(EvalKind.duel_round)
        else:
            self.err(self.tokens[self.i-1], f"Unexpected token kind: {token_kind}")
            return Eval(EvalKind.health)

    def parse_atom(self) -> NumberExpression | StringExpression | ListExpression | IdentExpression:
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.identifier and self.tokens[self.i].literal.startswith('$'):
            constant_name = self.tokens[self.i].literal[1:]
            self.i += 1
            return ConstantReferenceExpression(constant_name)
        
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.boolean_true:
            token = self.tokens[self.i]
            self.i += 1
            return ConstantExpression(token.literal, StringExpression("true"))
        
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.boolean_false:
            token = self.tokens[self.i]
            self.i += 1
            return ConstantExpression(token.literal, StringExpression("false"))

        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.square_open:
            return self.parse_list()
        
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.path:
            return self.parse_zone_path_expression()

        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.keyword_xyz:
            return self.parse_xyz()

        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.identifier:
            tok = self.tokens[self.i]
            self.i += 1
            return IdentExpression(tok.literal)
        
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
    
    def parse_value(self, expected_types=None) -> Expression:
        if expected_types is None:
            expected_types = [TokenKind.number, TokenKind.string, TokenKind.percent, TokenKind.identifier]

        if TokenKind.identifier in expected_types or 'window_path' in expected_types:
            if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.identifier:
                ident = self.tokens[self.i].literal
                self.i += 1
                return IdentExpression(ident)
        
        if 'window_path' in expected_types and self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.square_open:
            return self.parse_list()

        # Special handling for zone paths - accept both path tokens and identifiers
        if TokenKind.path in expected_types:
            if self.i < len(self.tokens):
                if self.tokens[self.i].kind == TokenKind.path:
                    return self.parse_zone_path_expression()
                elif self.tokens[self.i].kind == TokenKind.identifier:
                    # For zone names as identifiers
                    ident = self.tokens[self.i].literal
                    self.i += 1
                    return StringExpression(ident)

        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.keyword_xyz:
            return self.parse_xyz()

        valid_types = [t for t in expected_types if t in [TokenKind.number, TokenKind.string, TokenKind.percent]]
        if not valid_types:
            self.err(self.tokens[self.i], f"Expected one of {expected_types} but none are basic token types")
        
        tok = self.expect_consume_any(valid_types)
        match tok.kind:
            case TokenKind.number:
                return NumberExpression(tok.value)
            case TokenKind.percent:
                return NumberExpression(tok.value)
            case TokenKind.string:
                return StringExpression(tok.value)
            case _:
                self.err(tok, f"Invalid value kind: {tok.kind} in {tok}")

    def parse_numeric_stat_expression(self, token_kind: TokenKind, player_selector: PlayerSelector) -> Expression:
        self.i += 1
        
        # Handle "is between" case
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.keyword_isbetween:
            return self._handle_between_comparison(token_kind, player_selector)
        
        # Handle explicit comparison operators
        if self.i < len(self.tokens) and self.tokens[self.i].kind in [TokenKind.greater, TokenKind.less, TokenKind.equals]:
            return self._handle_explicit_comparison(token_kind, player_selector)
        
        # Handle implicit comparison based on token type
        return self._handle_implicit_comparison(token_kind, player_selector)
    
    def _handle_between_comparison(self, token_kind: TokenKind, player_selector: PlayerSelector) -> Expression:
        self.i += 1
        
        min_value = self.parse_value([TokenKind.number, TokenKind.percent, TokenKind.identifier])
        max_value = self.parse_value([TokenKind.number, TokenKind.percent, TokenKind.identifier])
        
        is_percent = (isinstance(min_value, NumberExpression) and self.tokens[self.i-2].kind == TokenKind.percent) or \
                     (isinstance(max_value, NumberExpression) and self.tokens[self.i-1].kind == TokenKind.percent)
        
        evaluated = self.get_stat_eval_expression(token_kind, is_percent)
        
        min_expr = self.gen_greater_expression(evaluated, min_value, player_selector)
        max_expr = self.gen_greater_expression(max_value, evaluated, player_selector)
        
        return AndExpression([min_expr, max_expr])
    
    def _handle_explicit_comparison(self, token_kind: TokenKind, player_selector: PlayerSelector) -> Expression:
        operator = self.tokens[self.i]
        self.i += 1
        
        target = self.parse_value([TokenKind.number, TokenKind.percent, TokenKind.identifier])
        evaluated = self.get_stat_eval_expression(token_kind, False)
        
        if operator.kind == TokenKind.greater:
            return self.gen_greater_expression(evaluated, target, player_selector)
        elif operator.kind == TokenKind.less:
            return self.gen_greater_expression(target, evaluated, player_selector)
        else:  # equals
            return self.gen_equivalent_expression(evaluated, target, player_selector)
    
    def _handle_implicit_comparison(self, token_kind: TokenKind, player_selector: PlayerSelector) -> Expression:
        value_expr = self.parse_value([TokenKind.number, TokenKind.percent])
        
        if not isinstance(value_expr, NumberExpression):
            self.err(self.tokens[self.i-1], f"Expected number or percent, got {value_expr}")
            
        is_percent = self.tokens[self.i-1].kind == TokenKind.percent
        evaluated = self.get_stat_eval_expression(token_kind, is_percent)
        
        # Define token groups for comparison types
        above_tokens = [
            TokenKind.command_expr_health_above, 
            TokenKind.command_expr_mana_above, 
            TokenKind.command_expr_energy_above, 
            TokenKind.command_expr_bagcount_above, 
            TokenKind.command_expr_gold_above, 
            TokenKind.command_expr_potion_countabove
        ]
        
        below_tokens = [
            TokenKind.command_expr_health_below, 
            TokenKind.command_expr_mana_below, 
            TokenKind.command_expr_energy_below, 
            TokenKind.command_expr_bagcount_below, 
            TokenKind.command_expr_gold_below, 
            TokenKind.command_expr_potion_countbelow
        ]
        
        if token_kind in above_tokens:
            return self.gen_greater_expression(evaluated, value_expr, player_selector)
        elif token_kind in below_tokens:
            return self.gen_greater_expression(value_expr, evaluated, player_selector)
        else:
            return self.gen_equivalent_expression(evaluated, value_expr, player_selector)

    def parse_command_expression(self) -> Expression:
        result = Command()
        player_selector  = self.parse_player_selector()
        result.player_selector = player_selector

        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.identifier:
            ident = self.tokens[self.i].literal
            self.i += 1
            
            if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.equals:
                self.i += 1
                
                # Check for boolean literals first
                if self.i < len(self.tokens):
                    if self.tokens[self.i].kind == TokenKind.boolean_true:
                        token = self.tokens[self.i]
                        self.i += 1
                        return ConstantCheckExpression(ident, ConstantExpression(token.literal, StringExpression("true")))
                    elif self.tokens[self.i].kind == TokenKind.boolean_false:
                        token = self.tokens[self.i]
                        self.i += 1
                        return ConstantCheckExpression(ident, ConstantExpression(token.literal, StringExpression("false")))
                
                # Otherwise parse as normal expression
                value = self.parse_expression()
                return ConstantCheckExpression(ident, value)
            else:
                # Revert if this isn't a constant check
                self.i -= 1
        match self.tokens[self.i].kind:
            case TokenKind.command_expr_account_level:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_account_level, player_selector)
            case TokenKind.command_expr_zone_changed:
                result.kind = CommandKind.expr
                self.i += 1

                if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.logical_to:
                    self.i += 1
                    text = self.parse_value([TokenKind.path, TokenKind.identifier]) # type: ignore
                    if isinstance(text, StringExpression):
                        result.data = [ExprKind.zone_changed, text.string.lower()]
                    elif isinstance(text, IdentExpression):
                        result.data = [ExprKind.zone_changed, text]
                    else:
                        result.data = [ExprKind.zone_changed, text]
                else:
                    result.data = [ExprKind.zone_changed]
            case TokenKind.command_expr_goal_changed:
                result.kind = CommandKind.expr
                self.i += 1

                if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.logical_to:
                    self.i += 1
                    text = self.parse_value([TokenKind.string, TokenKind.identifier]) # type: ignore
                    if isinstance(text, StringExpression):
                        result.data = [ExprKind.goal_changed, text.string.lower()]
                    elif isinstance(text, IdentExpression):
                        result.data = [ExprKind.goal_changed, text]
                    else:
                        result.data = [ExprKind.goal_changed, text]
                else:
                    result.data = [ExprKind.goal_changed]
            case TokenKind.command_expr_quest_changed:
                result.kind = CommandKind.expr
                self.i += 1

                if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.logical_to:
                    self.i += 1
                    text = self.parse_value([TokenKind.string, TokenKind.identifier]) # type: ignore
                    if isinstance(text, StringExpression):
                        result.data = [ExprKind.quest_changed, text.string.lower()]
                    elif isinstance(text, IdentExpression):
                        result.data = [ExprKind.quest_changed, text]
                    else:
                        result.data = [ExprKind.quest_changed, text]
                else:
                    result.data = [ExprKind.quest_changed]
            case TokenKind.command_expr_duel_round:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_duel_round, player_selector)
            case TokenKind.command_expr_item_dropped:
                result.kind = CommandKind.expr
                self.i += 1

                if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.square_open:
                    item_list = self.parse_list()

                    items = []
                    for item_expr in item_list:
                        if isinstance(item_expr, StringExpression):
                            items.append(item_expr.string.lower())
                        else:
                            self.err(self.tokens[self.i-1], f"Expected string in item list, got {item_expr}")

                    result.data = [ExprKind.items_dropped, items]
                else:
                    item = self.parse_value([TokenKind.string, TokenKind.identifier]) # type: ignore
                    if isinstance(item, StringExpression):
                        result.data = [ExprKind.items_dropped, item.string.lower()]
                    elif isinstance(item, IdentExpression):
                        result.data = [ExprKind.items_dropped, item]
                    else:
                        result.data = [ExprKind.items_dropped, item]
            case TokenKind.command_expr_window_visible:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.window_visible, self.parse_value(['window_path'])]  # type: ignore
            case TokenKind.command_expr_in_zone:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.in_zone, self.parse_value([TokenKind.path, TokenKind.identifier])]
            case TokenKind.command_expr_same_zone:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.same_zone]
            case TokenKind.command_expr_same_quest:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.same_quest]
            case TokenKind.command_expr_same_xyz:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.same_xyz]
            case TokenKind.command_expr_same_yaw:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.same_yaw]
            case TokenKind.command_expr_in_combat:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.in_combat]
            case TokenKind.command_expr_has_quest:
                result.kind = CommandKind.expr
                self.i += 1
                text = self.parse_value([TokenKind.string, TokenKind.identifier]) # type: ignore
                if isinstance(text, StringExpression):
                    result.data = [ExprKind.has_quest, text.string.lower()]
                elif isinstance(text, IdentExpression):
                    result.data = [ExprKind.has_quest, text]
                else:
                    result.data = [ExprKind.has_quest, text]
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
                xyz = self.parse_value([TokenKind.keyword_xyz, TokenKind.identifier])
                result.data = [ExprKind.has_xyz, xyz]
            case TokenKind.command_expr_has_yaw:
                result.kind = CommandKind.expr
                self.i += 1
                yaw = self.parse_value([TokenKind.number, TokenKind.identifier])
                result.data = [ExprKind.has_yaw, yaw]
            case TokenKind.command_expr_health_above:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_health_above, player_selector)
            case TokenKind.command_expr_health_below:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_health_below, player_selector)
            case TokenKind.command_expr_health:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_health, player_selector)
            case TokenKind.command_expr_mana_above:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_mana_above, player_selector)
            case TokenKind.command_expr_mana_below:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_mana_below, player_selector)
            case TokenKind.command_expr_mana:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_mana, player_selector)
            case TokenKind.command_expr_energy_above:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_energy_above, player_selector)
            case TokenKind.command_expr_energy_below:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_energy_below, player_selector)
            case TokenKind.command_expr_energy:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_energy, player_selector)
            case TokenKind.command_expr_bagcount_above:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_bagcount_above, player_selector)
            case TokenKind.command_expr_bagcount_below:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_bagcount_below, player_selector)
            case TokenKind.command_expr_bagcount:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_bagcount, player_selector)
            case TokenKind.command_expr_gold_above:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_gold_above, player_selector)
            case TokenKind.command_expr_gold_below:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_gold_below, player_selector)
            case TokenKind.command_expr_gold:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_gold, player_selector)
            case TokenKind.command_expr_window_text:
                self.i += 1
                window_path = self.parse_window_path()
                contains = self.consume_optional(TokenKind.contains)
            
                if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.square_open:
                    string_list = self.parse_list()
            
                    if contains:
                        return SelectorGroup(player_selector, ContainsStringExpression(
                            Eval(EvalKind.windowtext, [window_path]), 
                            ListExpression(string_list)
                        ))
                    else:
                        or_expressions = []
                        window_text_eval = Eval(EvalKind.windowtext, [window_path])
                        
                        if isinstance(string_list, ListExpression):
                            items_to_iterate = string_list.items
                        else:
                            items_to_iterate = string_list
                            
                        for string_expr in items_to_iterate:
                            if isinstance(string_expr, StringExpression):
                                or_expressions.append(EquivalentExpression(
                                    window_text_eval, 
                                    StringExpression(string_expr.string.lower())
                                ))
                            elif isinstance(string_expr, IdentExpression):
                                or_expressions.append(EquivalentExpression(
                                    window_text_eval, 
                                    string_expr
                                ))
                        
                        if len(or_expressions) == 1:
                            return SelectorGroup(player_selector, or_expressions[0])
                        
                        return SelectorGroup(player_selector, OrExpression(or_expressions))
                else:
                    target_expr = self.parse_value([TokenKind.string, TokenKind.identifier])
            
                    if isinstance(target_expr, StringExpression):
                        string_value = target_expr.string.lower()
                    elif isinstance(target_expr, IdentExpression):
                        if contains:
                            return SelectorGroup(player_selector, ContainsStringExpression(Eval(EvalKind.windowtext, [window_path]), target_expr))
                        else:
                            return SelectorGroup(player_selector, EquivalentExpression(Eval(EvalKind.windowtext, [window_path]), target_expr))
                    else:
                        self.err(self.tokens[self.i-1], f"Expected string or identifier, got {target_expr}")
                        string_value = ""  # Default value in case of error
                        
                    assert(type(window_path) == list)
                    
                    if contains:
                        return SelectorGroup(player_selector, ContainsStringExpression(Eval(EvalKind.windowtext, [window_path]), StringExpression(string_value)))
                    else:
                        return SelectorGroup(player_selector, EquivalentExpression(Eval(EvalKind.windowtext, [window_path]), StringExpression(string_value)))
            case TokenKind.command_expr_window_num:
                self.i += 1
                window_path = self.parse_window_path()
                evaluated = Eval(EvalKind.windownum, [window_path])

                return self.parse_indexed_numeric_comparison(evaluated, player_selector)
            case TokenKind.command_expr_playercount:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_playercount, player_selector)
            case TokenKind.command_expr_playercountabove:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_playercountabove, player_selector)
            case TokenKind.command_expr_playercountbelow:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_playercountbelow, player_selector)
            case TokenKind.command_expr_window_disabled:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.window_disabled, self.parse_value(['window_path'])]  # type: ignore
            case TokenKind.command_expr_in_range:
                result.kind = CommandKind.expr
                self.i += 1
                text = self.parse_value([TokenKind.string, TokenKind.identifier]) # type: ignore
                if isinstance(text, StringExpression):
                    result.data = [ExprKind.in_range, text.string.lower()]
                elif isinstance(text, IdentExpression):
                    result.data = [ExprKind.in_range, text]
                else:
                    result.data = [ExprKind.in_range, text]
            case TokenKind.command_expr_same_place:
                result.kind = CommandKind.expr
                self.i += 1
                result.data = [ExprKind.same_place]
            case TokenKind.command_expr_tracking_quest:
                result.kind = CommandKind.expr
                self.i += 1
                text = self.parse_value([TokenKind.string]) # type: ignore
                if isinstance(text, StringExpression):
                    result.data = [ExprKind.tracking_quest, text.string.lower()]
                elif isinstance(text, IdentExpression):
                    result.data = [ExprKind.tracking_quest, text]
                else:
                    result.data = [ExprKind.tracking_quest, text]
            case TokenKind.command_expr_tracking_goal:
                result.kind = CommandKind.expr
                self.i += 1
                text = self.parse_value([TokenKind.string]) # type: ignore
                if isinstance(text, StringExpression):
                    result.data = [ExprKind.tracking_goal, text.string.lower()]
                elif isinstance(text, IdentExpression):
                    result.data = [ExprKind.tracking_goal, text]
                else:
                    result.data = [ExprKind.tracking_goal, text]
            case TokenKind.command_expr_potion_count:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_potion_count, player_selector)
            case TokenKind.command_expr_potion_countabove:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_potion_countabove, player_selector)
            case TokenKind.command_expr_potion_countbelow:
                return self.parse_numeric_stat_expression(TokenKind.command_expr_potion_countbelow, player_selector)
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

    def parse_logical_expression(self) -> Expression:
        expr = self.parse_negation_expression()

        while self.i < len(self.tokens) and self.tokens[self.i].kind in [TokenKind.keyword_and, TokenKind.keyword_or]:
            operator = self.tokens[self.i]
            self.i += 1
            # Parse the right-hand side expression
            right = self.parse_negation_expression()
            
            if operator.kind == TokenKind.keyword_and:
                expr = AndExpression([expr, right])
            else:  # TokenKind.keyword_or
                expr = OrExpression([expr, right])
        
        return expr

    def parse_expression(self) -> Expression:
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.logical_and:
            self.err(self.tokens[self.i], "Expected an expression before &&")
            
        return self.parse_logical_expression()

    def parse_player_selector(self) -> PlayerSelector:
        result = PlayerSelector()
        valid_toks = [TokenKind.keyword_same_any, TokenKind.keyword_any_player, TokenKind.keyword_mass, TokenKind.keyword_except, TokenKind.player_num, TokenKind.player_wildcard, TokenKind.colon]
        expected_toks = [TokenKind.keyword_same_any, TokenKind.keyword_any_player, TokenKind.keyword_mass, TokenKind.keyword_except, TokenKind.player_num, TokenKind.player_wildcard]
        while self.i < len(self.tokens) and self.tokens[self.i].kind in valid_toks:
            if self.tokens[self.i].kind not in expected_toks:
                self.err(self.tokens[self.i], f"Invalid player selector encountered: {self.tokens[self.i]}")
            match self.tokens[self.i].kind:
                case TokenKind.keyword_same_any:
                    result.same_any = True
                    expected_toks = []
                    self.i += 1
                case TokenKind.keyword_any_player:
                    result.any_player = True
                    expected_toks = []
                    self.i += 1
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
        if len(result.player_nums) == 0 and not result.wildcard and not result.any_player and not result.same_any:
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
    
    def parse_zone_path_expression(self) -> Expression:
        self.i += 1  # Consume the path token
        path_str = self.tokens[self.i-1].literal
        return StringExpression(path_str)

    def parse_list(self) -> ListExpression:
        self.expect_consume(TokenKind.square_open)
        
        items = []
        while self.i < len(self.tokens) and self.tokens[self.i].kind != TokenKind.square_close:
            if self.tokens[self.i].kind == TokenKind.comma:
                self.i += 1
                continue
                
            items.append(self.parse_expression())
            
            if self.i < len(self.tokens) and self.tokens[self.i].kind != TokenKind.square_close:
                self.expect_consume(TokenKind.comma)
        
        self.expect_consume(TokenKind.square_close)
        return ListExpression(items)

    def parse_window_path(self) -> list[str] | Expression:
        # Check if this is a variable reference with $ prefix
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.identifier and self.tokens[self.i].literal.startswith('$'):
            ident = self.tokens[self.i].literal
            self.i += 1
            const_name = ident[1:]  # Remove the $ prefix
            return IdentExpression(const_name)
        
        # Original list parsing logic
        list_expr = self.parse_list()
        result = []
        for x in list_expr.items:  # Access the items attribute of ListExpression
            if not isinstance(x, StringExpression):
                raise ParserError(f"Unexpected expression type in window path: {x}")
            result.append(x.string)
        return result

    def end_line(self):
        if self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.logical_and:
            return
        self.expect_consume(TokenKind.END_LINE)

    def end_line_optional(self):
        if self.tokens[self.i].kind == TokenKind.END_LINE:
            self.i += 1

    def parse_command(self):
        commands = []
        commands.append(self._parse_simple_command())
        
        while self.i < len(self.tokens) and self.tokens[self.i].kind == TokenKind.logical_and:
            self.i += 1 
            commands.append(self._parse_simple_command())

        if len(commands) == 1:
            return commands[0]
        
        return ParallelCommandStmt(commands)

    def _parse_simple_command(self) -> Command:
        result = Command()
        result.player_selector = self.parse_player_selector()

        match self.tokens[self.i].kind:
            case TokenKind.command_restart_bot:
                result.kind = CommandKind.restart_bot
                self.i += 1
                self.end_line()
            case TokenKind.command_toggle_combat:
                result.kind = CommandKind.toggle_combat
                self.i += 1
                if self.tokens[self.i].kind in [TokenKind.logical_on, TokenKind.logical_off]:
                    result.data = [self.expect_consume_any([TokenKind.logical_on, TokenKind.logical_off]).literal]
                else:
                    result.data = []
                self.end_line()
            case TokenKind.command_set_zone:
                result.kind = CommandKind.set_zone
                self.i += 1
                self.end_line()
            case TokenKind.command_set_goal:
                result.kind = CommandKind.set_goal
                self.i += 1
                self.end_line()
            case TokenKind.command_set_quest:
                result.kind = CommandKind.set_quest
                self.i += 1
                self.end_line()
            case TokenKind.command_autopet:
                result.kind = CommandKind.autopet
                self.i += 1
                self.end_line()
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
                            # Check if it's a variable reference with $ prefix
                            if self.tokens[self.i].literal.startswith('$'):
                                ident = self.tokens[self.i].literal
                                self.i += 1
                                const_name = ident[1:]  # Remove the $ prefix
                                result.data = [LogKind.single, IdentExpression(const_name)]
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
                    case TokenKind.command_expr_any_player_list:
                        self.i += 1
                        result.data = [LogKind.single, StrFormatExpression("clients using anyplayer: %s", Eval(EvalKind.any_player_list))]
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
                    if self.tokens[self.i].kind == TokenKind.string:
                        result.data = [TeleportKind.position, self.parse_xyz()]
                    else:
                        result.data = [TeleportKind.position, self.parse_expression()]
                self.end_line()
            case TokenKind.command_plus_teleport:
                result.kind = CommandKind.teleport
                self.i += 1
                if self.tokens[self.i].kind == TokenKind.string:
                    result.data = [TeleportKind.plusteleport, self.parse_xyz()]
                else:
                    result.data = [TeleportKind.plusteleport, self.parse_expression()]
                self.end_line()
            case TokenKind.command_minus_teleport:
                result.kind = CommandKind.teleport
                self.i += 1
                if self.tokens[self.i].kind == TokenKind.string:
                    result.data = [TeleportKind.minusteleport, self.parse_xyz()]
                else:
                    result.data = [TeleportKind.minusteleport, self.parse_expression()]
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
                if self.tokens[self.i].kind == TokenKind.string:
                    result.data = [self.parse_xyz()]
                else:
                    result.data = [self.parse_expression()]
                self.end_line()
            case TokenKind.command_move_cursor_window:
                result.kind = CommandKind.cursor
                self.i += 1
                if self.tokens[self.i].kind == TokenKind.string:
                    result.data = [CursorKind.window, self.parse_window_path()]
                else:
                    result.data = [CursorKind.window, self.parse_expression()]
                self.end_line()
            case TokenKind.command_clickwindow:
                result.kind = CommandKind.click
                self.i += 1
                if self.tokens[self.i].kind == TokenKind.string:
                    result.data = [ClickKind.window, self.parse_window_path()]
                else:
                    result.data = [ClickKind.window, self.parse_expression()]
                self.end_line()
            case TokenKind.command_usepotion:
                result.kind = CommandKind.usepotion
                self.i += 1

                health_arg = None
                if self.tokens[self.i].kind == TokenKind.number:
                    health_arg = self.consume_optional(TokenKind.number)
                    health_expr = NumberExpression(health_arg.value)
                elif self.tokens[self.i].kind == TokenKind.identifier:
                    health_ident = self.consume_optional(TokenKind.identifier)
                    health_expr = IdentExpression(health_ident.literal)
                else:
                    health_arg = None
                
                if health_arg is not None:
                    self.skip_comma()

                    if self.tokens[self.i].kind == TokenKind.number:
                        mana_arg = self.expect_consume(TokenKind.number)
                        mana_expr = NumberExpression(mana_arg.value)
                    elif self.tokens[self.i].kind == TokenKind.identifier:
                        mana_ident = self.expect_consume(TokenKind.identifier)
                        mana_expr = IdentExpression(mana_ident.literal)
                    
                    result.data = [health_expr, mana_expr]
                
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
            case TokenKind.command_move_cursor:
                result.kind = CommandKind.cursor
                self.i += 1
                x_expr = None
                if self.tokens[self.i].kind == TokenKind.number:
                    x = self.expect_consume(TokenKind.number)
                    x_expr = NumberExpression(x.value)
                elif self.tokens[self.i].kind == TokenKind.identifier:
                    x = self.expect_consume(TokenKind.identifier)
                    x_expr = IdentExpression(x.literal)  

                if x_expr is not None:                  
                    self.skip_comma()

                    if self.tokens[self.i].kind == TokenKind.number:
                        y = self.expect_consume(TokenKind.number)
                        y_expr = NumberExpression(y.value)
                    elif self.tokens[self.i].kind == TokenKind.identifier:
                        y = self.expect_consume(TokenKind.identifier)
                        y_expr = IdentExpression(y.literal)

                    result.data = [CursorKind.position, x_expr, y_expr]
                self.end_line()
            case TokenKind.command_click:
                result.kind = CommandKind.click
                self.i += 1

                x_expr = None
                if self.tokens[self.i].kind == TokenKind.number:
                    x = self.expect_consume(TokenKind.number)
                    x_expr = NumberExpression(x.value)
                elif self.tokens[self.i].kind == TokenKind.identifier:
                    x = self.expect_consume(TokenKind.identifier)
                    x_expr = IdentExpression(x.literal)  

                if x_expr is not None:                  
                    self.skip_comma()

                    if self.tokens[self.i].kind == TokenKind.number:
                        y = self.expect_consume(TokenKind.number)
                        y_expr = NumberExpression(y.value)
                    elif self.tokens[self.i].kind == TokenKind.identifier:
                        y = self.expect_consume(TokenKind.identifier)
                        y_expr = IdentExpression(y.literal)

                    result.data = [ClickKind.position, x_expr, y_expr]
                self.end_line()
            case TokenKind.command_friendtp:
                result.kind = CommandKind.teleport
                self.i += 1
                x = self.expect_consume_any([TokenKind.keyword_icon, TokenKind.identifier])
                if x.kind == TokenKind.keyword_icon:
                    result.data = [TeleportKind.friend_icon]
                elif self.tokens[self.i].kind == TokenKind.END_LINE:
                    result.data = [TeleportKind.friend_name, IdentExpression(x.literal)]
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
                
                # Check for optional 'nav' parameter
                nav_mode = False
                if self.tokens[self.i].kind == TokenKind.command_nav:
                    self.i += 1 
                    nav_mode = True
                
                arg = self.consume_optional(TokenKind.string)
                if arg is not None:
                    result.data = [TeleportKind.entity_literal, arg.value]
                    if nav_mode:
                        result.data.insert(1, TeleportKind.nav)
                elif self.tokens[self.i].kind == TokenKind.identifier:
                    ident = self.expect_consume(TokenKind.identifier)
                    result.data = [TeleportKind.entity_vague, ident.literal]
                    if nav_mode:
                        result.data.insert(1, TeleportKind.nav)
                else:
                    token = self.tokens[self.i]
                    self.i += 1
                    result.data = [TeleportKind.entity_vague, token.literal]
                    if nav_mode:
                        result.data.insert(1, TeleportKind.nav)
                self.end_line()
            case TokenKind.command_tozone:
                result.kind = CommandKind.tozone
                self.i += 1
                if self.tokens[self.i].kind == TokenKind.path:
                    result.data = [self.parse_zone_path()]
                elif self.tokens[self.i].kind == TokenKind.identifier:
                    ident = self.expect_consume(TokenKind.identifier)
                    result.data = [IdentExpression(ident.literal)]
                else:
                    result.data = [self.parse_expression()]
                self.end_line()
            case TokenKind.command_load_playstyle:
                result.kind = CommandKind.load_playstyle
                self.i += 1
                if self.tokens[self.i].kind == TokenKind.string:
                    result.data = [self.expect_consume(TokenKind.string).value]
                elif self.tokens[self.i].kind == TokenKind.identifier:
                    ident = self.expect_consume(TokenKind.identifier)
                    result.data = [IdentExpression(ident.literal)]
                else:
                    result.data = [self.parse_expression()]
                self.end_line()
            case TokenKind.command_set_yaw:
                result.kind = CommandKind.set_yaw
                self.i += 1
                if self.tokens[self.i].kind == TokenKind.number:
                    result.data = [self.expect_consume(TokenKind.number).value]
                elif self.tokens[self.i].kind == TokenKind.identifier:
                    ident = self.expect_consume(TokenKind.identifier)
                    result.data = [IdentExpression(ident.literal)]
                else:
                    result.data = [self.parse_expression()]
                self.end_line()
            case TokenKind.command_select_friend:
                result.kind = CommandKind.select_friend
                self.i += 1
                if self.tokens[self.i].kind == TokenKind.identifier and self.i + 1 < len(self.tokens) and self.tokens[self.i + 1].kind == TokenKind.END_LINE:
                    ident = self.expect_consume(TokenKind.identifier)
                    result.data = [ident.literal]  
                else:
                    name_parts = []
                    while self.i < len(self.tokens) and self.tokens[self.i].kind != TokenKind.END_LINE:
                        name_parts.append(self.tokens[self.i].literal)
                        self.i += 1
                    result.data = [" ".join(name_parts)]
                self.end_line()
            case TokenKind.command_setdeck:
                result.kind = CommandKind.setdeck
                self.i += 1
                token = self.expect_consume(TokenKind.string)
                result.data = [token.value]
                self.end_line()
            case TokenKind.command_getdeck:
                result.kind = CommandKind.getdeck
                self.i += 1
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
            case TokenKind.keyword_con:
                self.i += 1
                var_name = self.expect_consume(TokenKind.identifier).literal
                self.expect_consume(TokenKind.equals)
                expr = self.parse_expression()
                self.end_line()
                return ConstantDeclStmt(var_name, expr)
            case TokenKind.keyword_settimer:
                self.i += 1
                timer_name = self.consume_any_ident()
                self.end_line()
                return TimerStmt(TimerAction.start, timer_name.ident)
            case TokenKind.keyword_endtimer:
                self.i += 1
                timer_name = self.consume_any_ident()
                self.end_line()
                return TimerStmt(TimerAction.end, timer_name.ident)
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
            if stmt:
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
