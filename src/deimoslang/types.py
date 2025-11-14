from typing import Any, Optional
from enum import Enum, auto

from .tokenizer import Token, TokenKind


class CommandKind(Enum):
    invalid = auto()

    expr = auto()
    expr_gt = auto()
    expr_eq = auto()

    kill = auto()
    sleep = auto()
    log = auto()
    teleport = auto()
    goto = auto()
    sendkey = auto()
    waitfor = auto()
    usepotion = auto()
    buypotions = auto()
    relog = auto()
    click = auto()
    tozone = auto()
    load_playstyle = auto()
    set_yaw = auto() 
    setdeck = auto()
    getdeck = auto() 
    select_friend = auto()
    autopet = auto()
    compound = auto()
    set_goal = auto()
    set_quest = auto()
    set_zone = auto()
    toggle_combat = auto()
    restart_bot = auto()
    cursor = auto() 

class TeleportKind(Enum):
    position = auto()
    friend_icon = auto()
    friend_name = auto()
    entity_vague = auto()
    entity_literal = auto()
    mob = auto()
    quest = auto()
    client_num = auto()
    nav = auto()
    plusteleport = auto()
    minusteleport = auto()

class EvalKind(Enum):
    health = auto()
    max_health = auto()
    mana = auto()
    max_mana = auto()
    energy = auto()
    max_energy = auto()
    bagcount = auto()
    max_bagcount = auto()
    gold = auto()
    max_gold = auto()
    windowtext = auto()
    potioncount = auto()
    max_potioncount = auto()
    playercount = auto()
    any_player_list = auto()
    windownum = auto()
    account_level = auto()
    duel_round = auto()
    reference_counter = auto()

class WaitforKind(Enum):
    dialog = auto()
    battle = auto()
    zonechange = auto()
    free = auto()
    window = auto()

class CursorKind(Enum):
    position = auto()
    window = auto()

class ClickKind(Enum):
    window = auto()
    position = auto()

class LogKind(Enum):
    multi = auto()
    single = auto()

class ExprKind(Enum):
    window_visible = auto()
    in_zone = auto()
    same_zone = auto()
    playercount = auto()
    tracking_quest = auto()
    tracking_goal = auto()
    loading = auto()
    in_combat = auto()
    has_dialogue = auto()
    has_xyz = auto()
    has_quest = auto()
    health_below = auto()
    health_above = auto()
    health = auto()
    mana = auto()
    mana_above = auto()
    mana_below = auto()
    energy = auto()
    energy_above = auto()
    energy_below = auto()
    bag_count = auto()
    bag_count_above = auto()
    bag_count_below = auto()
    gold = auto()
    gold_above = auto()
    gold_below = auto()
    window_disabled = auto()
    same_place = auto()
    in_range = auto()
    has_yaw = auto()
    same_quest = auto()
    same_xyz = auto()
    same_yaw = auto()
    items_dropped = auto()
    duel_round = auto()
    goal_changed = auto()
    quest_changed = auto()
    zone_changed = auto()
    constant_check = auto()
    constant_reference = auto()

class TimerAction(Enum):
    start = auto()
    end = auto()

# TODO: Replace asserts

class PlayerSelector:
    def __init__(self):
        self.player_nums: list[int] = []
        self.mass = False
        self.inverted = False
        self.wildcard = False
        self.any_player = False
        self.same_any = False

    def validate(self):
        assert not (self.mass and self.inverted), "Invalid player selector: mass + except"
        assert not (self.mass and len(self.player_nums) > 0), "Invalid player selector: mass + specified players"
        assert not (self.inverted and len(self.player_nums) == 0), "Invalid player selector: inverted + 0 players"
        assert (not self.wildcard) or (self.wildcard and not (self.mass) and len(self.player_nums) == 0), "Invalid player selector: wildcard + mass or player_nums"
        assert (not self.any_player) or (self.any_player and not (self.mass) and len(self.player_nums) == 0), "Invalid player selector: any_player + mass or player_nums"
        assert (not self.same_any) or (self.same_any and not (self.mass) and len(self.player_nums) == 0), "Invalid player selector: same_any + mass or player_nums"
        self.player_nums.sort()

    def __hash__(self) -> int:
        return hash((frozenset(self.player_nums), self.mass, self.inverted))

    def __repr__(self) -> str:
        return f"PlayerSelector(nums: {self.player_nums}, mass: {self.mass}, inverted: {self.inverted}, wildcard: {self.wildcard})"

class Command:
    def __init__(self):
        self.kind = CommandKind.invalid
        self.data: list[Any] = []
        self.player_selector: PlayerSelector | None = None

    def __repr__(self) -> str:
        params_str = ", ".join([str(x) for x in self.data])
        if self.player_selector is None:
            return f"{self.kind.name}({params_str})"
        else:
            return f"{self.kind.name}({params_str}) @ {self.player_selector}"
        

class Expression:
    def __init__(self):
        pass

class ConstantExpression(Expression):
    def __init__(self, name: str, value: Expression):
        self.name = name
        self.value = value

    def __repr__(self) -> str:
        return f"ConstE({self.name}, {self.value})"

class ListExpression(Expression):
    def __init__(self, items: list[Expression]):
        self.items = items

    def __repr__(self) -> str:
        return f"ListE({self.items})"

class NumberExpression(Expression):
    def __init__(self, number: float | int):
        self.number = number

    def __repr__(self) -> str:
        return f"Number({self.number})"

class StringExpression(Expression):
    def __init__(self, string: str):
        self.string = string

    def __repr__(self) -> str:
        return f"String({self.string})"

class StrFormatExpression(Expression):
    def __init__(self, format_str: str, *args):
        self.format_str = format_str
        self.values = args

    def __repr__(self) -> str:
        return f"StrFormat({self.format_str}, {self.values})"

class UnaryExpression(Expression):
    def __init__(self, operator: Token, expr: Expression):
        self.operator = operator
        self.expr = expr

    def __repr__(self) -> str:
        return f"Unary({self.operator.kind}, {self.expr})"

class KeyExpression(Expression):
    def __init__(self, key: str):
        self.key = key

    def __repr__(self) -> str:
        return f"Key({self.key})"

class CommandExpression(Expression):
    def __init__(self, command: Command):
        self.command = command

    def __repr__(self) -> str:
        return f"ComE({self.command})"

class XYZExpression(Expression):
    def __init__(self, x: Expression, y: Expression, z: Expression):
        self.x = x
        self.y = y
        self.z = z

    def __repr__(self) -> str:
        return f"XYZE({self.x}, {self.y}, {self.z})"

class BinaryExpression(Expression):
    def __init__(self, lhs: Expression, rhs: Expression):
        self.lhs = lhs
        self.rhs = rhs

class SubExpression(BinaryExpression):
    def __repr__(self) -> str:
        return f"SubE({self.lhs}, {self.rhs})"

class DivideExpression(BinaryExpression):
    def __repr__(self) -> str:
        return f"DivideE({self.lhs}, {self.rhs})"

class EquivalentExpression(BinaryExpression):
    def __repr__(self) -> str:
        return f"EquivalentE({self.lhs}, {self.rhs})"

class ContainsStringExpression(BinaryExpression):
    def __repr__(self) -> str:
        return f"ContainsStrE({self.lhs}, {self.rhs})"

class GreaterExpression(BinaryExpression):
    def __repr__(self) -> str:
        return f"GreaterE({self.lhs}, {self.rhs})"

class AndExpression(Expression):
    def __init__(self, expressions: list[Expression]):
        self.expressions = expressions

    def __repr__(self) -> str:
        return f"AndE({', '.join(str(expr) for expr in self.expressions)})"

class OrExpression(Expression):
    def __init__(self, expressions: list[Expression]):
        self.expressions = expressions

    def __repr__(self) -> str:
        return f"OrE({', '.join(str(expr) for expr in self.expressions)})"

class ConstantReferenceExpression(Expression):
    def __init__(self, name: str):
        self.name = name
        
    def __repr__(self) -> str:
        return f"ConstRef(${self.name})"

class ConstantCheckExpression(Expression):
    def __init__(self, name: str, value: Expression):
        self.name = name
        self.value = value

    def __repr__(self) -> str:
        return f"ConstCheck({self.name}, {self.value})"
    
class RangeMinExpression(Expression):
    def __init__(self, range_expr: Expression):
        self.range_expr = range_expr

    def __repr__(self) -> str:
        return f"RangeMin({self.range_expr})"

class RangeMaxExpression(Expression):
    def __init__(self, range_expr: Expression):
        self.range_expr = range_expr

    def __repr__(self) -> str:
        return f"RangeMax({self.range_expr})"
    
class IndexAccessExpression(Expression):
    def __init__(self, expr: Expression, index: Expression):
        self.expr = expr
        self.index = index

    def __repr__(self) -> str:
        return f"IndexAccess({self.expr}[{self.index}])"

class SelectorGroup(Expression):
    def __init__(self, players: PlayerSelector, expr: Expression):
        self.players = players
        self.expr = expr

    def __repr__(self) -> str:
        return f"SelectorG({self.players}, {self.expr})"

class IdentExpression(Expression):
    def __init__(self, ident: str):
        self.ident = ident

    def __repr__(self) -> str:
        return f"IdentE({self.ident})"

class SymExpression(Expression):
    def __init__(self, sym: "Symbol"):
        self.sym = sym

    def __repr__(self) -> str:
        return f"SymE({self.sym})"

class StackLocExpression(Expression):
    def __init__(self, offset: int):
        self.offset = offset

    def __repr__(self) -> str:
        return f"StackLocE({self.offset})"

class ReadVarExpr(Expression):
    def __init__(self, loc: Expression) -> None:
        self.loc = loc

    def __repr__(self) -> str:
        return f"ReadVarE {self.loc}"

class Eval(Expression):
    def __init__(self, eval_kind: EvalKind, args=[]):
        self.kind = eval_kind
        self.args = args

    def __repr__(self) -> str:
        return f"Eval({self.kind})"

class Stmt:
    def __init__(self) -> None:
        pass

class ConstantDeclStmt(Stmt):
    def __init__(self, name: str, value: Expression):
        self.name = name
        self.value = value

    def __repr__(self) -> str:
        return f"ConstDeclS({self.name}, {self.value})"

class ParallelCommandStmt(Stmt):
    def __init__(self, commands: list[Command]) -> None:
        self.commands = commands
    
    def __repr__(self) -> str:
        return f"ParallelCommandStmt({self.commands})"

class StmtList(Stmt):
    def __init__(self, stmts: list[Stmt]):
        self.stmts = stmts

    def __repr__(self) -> str:
        return "StmtList{" + "; ".join([str(x) for x in self.stmts]) + "}"

class TimerStmt(Stmt):
    def __init__(self, action: TimerAction, timer_name: str):
        self.action = action
        self.timer_name = timer_name
        
    def __str__(self):
        action_str = "settimer" if self.action == TimerAction.start else "endtimer"
        return f"{action_str} {self.timer_name};"

class CommandStmt(Stmt):
    def __init__(self, command: Command):
        self.command = command

    def __repr__(self) -> str:
        return f"ComS({self.command})"

class IfStmt(Stmt):
    def __init__(self, expr: Expression, branch_true: StmtList, branch_false: StmtList):
        self.expr = expr
        self.branch_true = branch_true
        self.branch_false = branch_false

    def __repr__(self) -> str:
        return f"IfS {self.expr} {{ {self.branch_true} }} else {{ {self.branch_false} }}"

class BreakStmt(Stmt):
    def __init__(self):
        pass

    def __repr__(self) -> str:
        return f"BreakS"

class ReturnStmt(Stmt):
    def __init__(self):
        pass

    def __repr__(self) -> str:
        return f"ReturnS"

class MixinStmt(Stmt):
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"MixinS {self.name}"

class LoopStmt(Stmt):
    def __init__(self, body: StmtList):
        self.body = body

    def __repr__(self) -> str:
        return f"LoopS {{ {self.body} }}"

class WhileStmt(Stmt):
    def __init__(self, expr: Expression, body: StmtList):
        self.expr = expr
        self.body = body

    def __repr__(self) -> str:
        return f"WhileS {self.expr} {{ {self.body} }}"

class UntilStmt(Stmt):
    def __init__(self, expr: Expression, body: StmtList):
        self.expr = expr
        self.body = body

    def __repr__(self) -> str:
        return f"UntilS {self.expr} {{ {self.body} }}"

class TimesStmt(Stmt):
    def __init__(self, num: int, body: StmtList):
        self.num = num
        self.body = body

    def __repr__(self) -> str:
        return f"TimesS {self.num} {{ {self.body} }}"

class BlockDefStmt(Stmt):
    def __init__(self, name: Expression, body: StmtList) -> None:
        self.name = name
        self.body = body
        self.mixins: set[str] = set()

    def __repr__(self) -> str:
        return f"BlockDefS {self.name} {{ {self.body} }}"

class CallStmt(Stmt):
    def __init__(self, name: Expression) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"CallS {self.name}"


class DefVarStmt(Stmt):
    def __init__(self, sym: "Symbol") -> None:
        self.sym = sym

    def __repr__(self) -> str:
        return f"DefVarS {self.sym}"

class WriteVarStmt(Stmt):
    def __init__(self, sym: "Symbol", expr: Expression) -> None:
        self.sym = sym
        self.expr = expr

    def __repr__(self) -> str:
        return f"WriteVarS {self.sym} = {self.expr}"

class KillVarStmt(Stmt):
    def __init__(self, sym: "Symbol") -> None:
        self.sym = sym

    def __repr__(self) -> str:
        return f"KillVarS {self.sym}"

class UntilRegion(Stmt):
    def __init__(self, expr: Expression, body: Stmt) -> None:
        self.expr = expr
        self.body = body

    def __repr__(self) -> str:
        return f"UntilRegionS ({self.expr}) {self.body}"


class SymbolKind(Enum):
    variable = auto()
    block = auto()
    label = auto()


class Symbol:
    def __init__(self, literal: str, id: int, kind: SymbolKind):
        self.literal = literal
        self.id = id
        self.kind = kind
        self.defnode: Optional[Stmt] = None

    def __repr__(self) -> str:
        return f"{self.literal}:{self.id}_{self.kind.name}"
