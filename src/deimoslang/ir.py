import copy
from enum import Enum, auto
from typing import Any

from .tokenizer import *
from .parser import *
from .sem import *


class CompilerError(Exception):
    pass



class InstructionKind(Enum):
    kill = auto()
    sleep = auto()
    restart_bot = auto()

    log_single = auto()
    log_multi = auto()

    jump = auto()
    jump_if = auto()
    jump_ifn = auto()

    enter_until = auto()
    exit_until = auto()

    label = auto()
    ret = auto()
    call = auto()
    deimos_call = auto()

    load_playstyle = auto()
    set_yaw = auto()
    setdeck = auto()
    getdeck = auto()

    push_stack = auto()
    pop_stack = auto()
    write_stack = auto()

    set_timer = auto()
    end_timer = auto()

    declare_constant = auto()

    compound_deimos_call = auto()

    nop = auto()

class Instruction:
    def __init__(self, kind: InstructionKind, data: Any | None = None) -> None:
        self.kind = kind
        self.data = data

    def __repr__(self) -> str:
        if self.data is not None:
            return f"{self.kind.name} {self.data}"
        return f"{self.kind.name}"


class StackInfo:
    def __init__(self):
        self.offset = 0
        self.slots: dict[Symbol, int] = {}

    def push(self, sym: Symbol):
        self.slots[sym] = self.offset
        self.offset += 1

    def pop(self, sym: Symbol):
        self.offset -= 1
        # mostly here for debugging
        if self.slots[sym] != self.offset:
            raise CompilerError(f"Attempted to pop a stack value that is not placed at the top: {sym}\n{self.slots}")
        del self.slots[sym]

    def loc(self, sym: Symbol) -> int:
        return self.slots[sym] - self.offset


class Compiler:
    def __init__(self, analyzer: Analyzer):
        self.analyzer = analyzer
        self._program: list[Instruction] = []

        self._stacks = [StackInfo()]

        self._loop_label_stack = []

        # until is a bit too special and has dangerous interactions with user specified returns because of it
        self._outermost_until: Optional[int] = None

    @staticmethod
    def from_text(code: str) -> "Compiler":
        tokenizer = Tokenizer()
        parser = Parser(tokenizer.tokenize(code))
        analyzer = Analyzer(parser.parse())
        analyzer.analyze_program()
        return Compiler(analyzer=analyzer)

    # a branch may clean up variables that must continue to exist in the next segment
    def enter_branch(self):
        top = self._stacks[-1]
        new_top = StackInfo()
        new_top.offset = top.offset
        new_top.slots = top.slots.copy()
        self._stacks.append(new_top)

    def exit_branch(self):
        self._stacks.pop()

    def stack_loc(self, sym: Symbol) -> int:
        for info in self._stacks:
            if sym in info.slots:
                return info.loc(sym)
        raise CompilerError(f"Failed to determine the stack location for symbol {sym}")

    def emit(self, kind: InstructionKind, data: Any | None = None):
        self._program.append(Instruction(kind, data))

    def gen_label(self, name="anonymous") -> Symbol:
        return self.analyzer.gen_label_sym(name)

    def emit_deimos_call(self, com: Command):
        self.emit(InstructionKind.deimos_call, [com.player_selector, com.kind.name, com.data])

    def compile_command(self, com: Command):
        if isinstance(com, ParallelCommandStmt):
                # Compile each command in the parallel statement
                for cmd in com.commands:
                    self.compile_command(cmd)
                return

        match com.kind: 
            case CommandKind.restart_bot:
                self.emit(InstructionKind.restart_bot)
            case CommandKind.toggle_combat:
                self.emit(InstructionKind.deimos_call, [com.player_selector, com.kind.name, com.data])
            case CommandKind.set_zone:
                self.emit(InstructionKind.deimos_call, [com.player_selector, com.kind.name, com.data])
            case CommandKind.set_goal:
                self.emit(InstructionKind.deimos_call, [com.player_selector, com.kind.name, com.data])
            case CommandKind.set_quest:
                self.emit(InstructionKind.deimos_call, [com.player_selector, com.kind.name, com.data])
            case CommandKind.compound:
                command_entries = []
                for sub_command in com.data:
                    command_entries.append([
                        sub_command.player_selector,
                        sub_command.kind.name,
                        sub_command.data
                    ])
                self.emit(InstructionKind.compound_deimos_call, command_entries)
            case CommandKind.autopet:
                self.emit(InstructionKind.deimos_call, [com.player_selector, com.kind.name, com.data])
            case CommandKind.kill:
                self.emit(InstructionKind.kill)
            case CommandKind.sleep:
                self.emit(InstructionKind.sleep, com.data[0])
            case CommandKind.log:
                kind = com.data[0]
                match kind:
                    case LogKind.multi:
                        self.emit(InstructionKind.log_multi, [com.player_selector, com.data[1]])
                    case LogKind.single:
                        self.emit(InstructionKind.log_single, com.data[1])
                    case _:
                        raise CompilerError(f"Unimplemented log kind: {com}")

            case CommandKind.sendkey | CommandKind.click | CommandKind.teleport \
                | CommandKind.goto | CommandKind.usepotion | CommandKind.buypotions \
                | CommandKind.relog | CommandKind.tozone | CommandKind.cursor:
                self.emit_deimos_call(com)

            case CommandKind.select_friend:
                self.emit_deimos_call(com)
            case CommandKind.waitfor:
                # copy the original data to split inverted waitfor in two
                non_inverted_com = copy.copy(com)
                data1 = com.data[:]
                data1[-1] = False
                non_inverted_com.data = data1
                self.emit_deimos_call(non_inverted_com)
                if com.data[-1] == True:
                    self.emit_deimos_call(com)

            case CommandKind.set_yaw:
                self.emit(InstructionKind.set_yaw, [com.player_selector, com.data[0]])
            case CommandKind.load_playstyle:
                self.emit(InstructionKind.load_playstyle, com.data[0])
            case CommandKind.setdeck:
                self.emit(InstructionKind.setdeck, [com.player_selector, com.data[0]])
            case CommandKind.getdeck:
                self.emit(InstructionKind.getdeck, [com.player_selector])
            case _:
                raise CompilerError(f"Unimplemented command: {com}")

    def process_labels(self, program: list[Instruction]):
        new_program: list[Instruction] = []
        offsets = {}
    
        # discover labels
        for idx, instr in enumerate(program):
            match instr.kind:
                case InstructionKind.label:
                    sym = instr.data
                    offsets[sym] = len(new_program)
                    if idx + 1 == len(program):
                        # special case, jumping to the end may need padding
                        new_program.append(Instruction(InstructionKind.nop))
                case _:
                    new_program.append(instr)
    
        program = new_program
    
        # resolve labels
        for idx, instr in enumerate(program):
            match instr.kind:
                case InstructionKind.call | InstructionKind.jump:
                    sym = instr.data
                    offset = offsets[sym]
                    instr.data = offset - idx
                case InstructionKind.jump_if | InstructionKind.jump_ifn:
                    assert(type(instr.data) == list)
                    sym = instr.data[1]
                    offset = offsets[sym]
                    instr.data[1] = offset - idx
                case InstructionKind.enter_until:
                    assert(type(instr.data) == list)
                    sym = instr.data[2]
                    offset = offsets[sym]
                    instr.data[2] = offset - idx
                case _:
                    pass
    
        return program

    def compile_block_def(self, block_def: BlockDefStmt):
        if isinstance(block_def.name, SymExpression):
            # This is only safe because the sem stage ensures there's no nested blocks
            enter_block_label = block_def.name.sym
            self.emit(InstructionKind.label, enter_block_label)
            prev_until = self._outermost_until
            self._outermost_until = None
            self._compile(block_def.body)
            self._outermost_until = prev_until
        elif isinstance(block_def.name, IdentExpression):
            raise CompilerError(f"Encountered an unresolved block sym during compilation: {block_def}")
        else:
            raise CompilerError(f"Encountered a malformed block sym during compilation: {block_def}")

    def compile_call(self, call: CallStmt):
        if isinstance(call.name, SymExpression):
            self.emit(InstructionKind.call, call.name.sym)
        elif isinstance(call.name, IdentExpression):
            raise CompilerError(f"Encountered an unresolved call during compilation: {call}")
        else:
            raise CompilerError(f"Encountered a malformed call during compilation: {call}")

    def prep_expression(self, expr: Expression):
        match expr:
            case ConstantCheckExpression():
                self.prep_expression(expr.value)
            case AndExpression() | OrExpression():
                for sub_expr in expr.expressions:
                    self.prep_expression(sub_expr)
            case BinaryExpression():
                self.prep_expression(expr.lhs)
                self.prep_expression(expr.rhs)
            case ReadVarExpr():
                if isinstance(expr.loc, SymExpression):
                    expr.loc = StackLocExpression(self.stack_loc(expr.loc.sym))
                else:
                    raise CompilerError(f"Malformed ReadVarExpr: {expr}")
            case SelectorGroup() | UnaryExpression():
                self.prep_expression(expr.expr)
            case ListExpression():
                if hasattr(expr, 'items'):
                    if isinstance(expr.items, list):
                        if len(expr.items) == 1 and isinstance(expr.items[0], ListExpression):
                            self.prep_expression(expr.items[0])
                        else:
                            for item in expr.items:
                                self.prep_expression(item)
                    elif isinstance(expr.items, ListExpression):
                        self.prep_expression(expr.items)
                    else:
                        raise CompilerError(f"Unexpected type for ListExpression.items: {type(expr.items)}")
                else:
                    raise CompilerError(f"ListExpression missing 'items' attribute: {expr}")
            case RangeMinExpression() | RangeMaxExpression():
                self.prep_expression(expr.range_expr)
            case IndexAccessExpression():
                self.prep_expression(expr.expr)
                self.prep_expression(expr.index)
            case ConstantExpression() |NumberExpression() | StringExpression() | KeyExpression() | CommandExpression() | XYZExpression() | IdentExpression() | StackLocExpression() | Eval():
                pass
            case _:
                raise CompilerError(f"Unhandled expression type: {expr}")

    def compile_if_stmt(self, stmt: IfStmt):
        after_if_label = self.gen_label("after_if")
        branch_true_label = self.gen_label("branch_true")
        self.prep_expression(stmt.expr)
        self.emit(InstructionKind.jump_if, [stmt.expr, branch_true_label])
        self.enter_branch()
        self._compile(stmt.branch_false)
        self.exit_branch()
        self.emit(InstructionKind.jump, after_if_label)
        self.emit(InstructionKind.label, branch_true_label)
        self.enter_branch()
        self._compile(stmt.branch_true)
        self.exit_branch()
        self.emit(InstructionKind.label, after_if_label)

    def compile_loop_stmt(self, stmt: LoopStmt):
        start_loop_label = self.gen_label("start_loop")
        end_loop_label = self.gen_label("end_loop")
        self._loop_label_stack.append(end_loop_label)
        self.emit(InstructionKind.label, start_loop_label)
        self.enter_branch()
        self._compile(stmt.body)
        self.exit_branch()
        self.emit(InstructionKind.jump, start_loop_label)
        self.emit(InstructionKind.label, end_loop_label)
        self._loop_label_stack.pop()

    def compile_while_stmt(self, stmt: WhileStmt):
        start_while_label = self.gen_label("start_while")
        end_while_label = self.gen_label("end_while")
        self._loop_label_stack.append(end_while_label)
        self.prep_expression(stmt.expr)
        self.emit(InstructionKind.jump_ifn, [stmt.expr, end_while_label])
        self.emit(InstructionKind.label, start_while_label)
        self.enter_branch()
        self._compile(stmt.body)
        self.exit_branch()
        self.emit(InstructionKind.jump_if, [stmt.expr, start_while_label])
        self.emit(InstructionKind.label, end_while_label)
        self._loop_label_stack.pop()

    def compile_until_region(self, stmt: UntilRegion):
        id = self.analyzer.gen_sym_id()
        exit_until_label = self.gen_label("exit_until")
        self._loop_label_stack.append(exit_until_label)
        self.emit(InstructionKind.enter_until, [stmt.expr, id, exit_until_label])
        is_outermost = self._outermost_until is None
        if is_outermost:
            self._outermost_until = id
        self.enter_branch()
        self._compile(stmt.body)
        self.exit_branch()
        if is_outermost:
            self._outermost_until = None
        self.emit(InstructionKind.label, exit_until_label)
        self.emit(InstructionKind.exit_until, id)
        self._loop_label_stack.pop()

    def compile_return_stmt(self):
        if self._outermost_until is not None:
            self.emit(InstructionKind.exit_until, self._outermost_until)
        self.emit(InstructionKind.ret)

    def _compile(self, stmt: Stmt):
        match stmt:
            case ConstantDeclStmt():
                self.prep_expression(stmt.value)
                self.emit(InstructionKind.declare_constant, [stmt.name, stmt.value])
            case ParallelCommandStmt():
                command_entries = []
                for command in stmt.commands:
                    command_entries.append([command.player_selector, command.kind.name, command.data])
                self.emit(InstructionKind.compound_deimos_call, command_entries)
            case TimerStmt():
                if stmt.action == TimerAction.start:
                    self.emit(InstructionKind.set_timer, stmt.timer_name)
                else:  # TimerAction.end
                    self.emit(InstructionKind.end_timer, stmt.timer_name)
            case StmtList():
                for inner in stmt.stmts:
                    self._compile(inner)
            case CommandStmt():
                self.compile_command(stmt.command)
            case CallStmt():
                self.compile_call(stmt)
            case BlockDefStmt():
                self.compile_block_def(stmt)
            case IfStmt():
                self.compile_if_stmt(stmt)
            case LoopStmt():
                self.compile_loop_stmt(stmt)
            case WhileStmt():
                self.compile_while_stmt(stmt)
            case DefVarStmt():
                self._stacks[-1].push(stmt.sym)
                self.emit(InstructionKind.push_stack)
            case KillVarStmt():
                self.emit(InstructionKind.pop_stack)
                self._stacks[-1].pop(stmt.sym)
            case WriteVarStmt():
                self.prep_expression(stmt.expr)
                self.emit(InstructionKind.write_stack, [self.stack_loc(stmt.sym), stmt.expr])
            case BreakStmt():
                label = self._loop_label_stack[-1]
                self.emit(InstructionKind.jump, label)
            case ReturnStmt():
                self.compile_return_stmt()
            case UntilRegion():
                self.compile_until_region(stmt)
            case _:
                raise CompilerError(f"Unknown statement: {stmt}\n{type(stmt)}")

    def compile(self):
        toplevel_start_label = self.gen_label("program_start")
        self.emit(InstructionKind.jump, toplevel_start_label)
        for stmt in self.analyzer._block_defs:
            self._compile(stmt)
        self.emit(InstructionKind.label, toplevel_start_label)

        for stmt in self.analyzer._stmts:
            self._compile(stmt)
        return self.process_labels(self._program)


if __name__ == "__main__":
    from pathlib import Path
    compiler = Compiler.from_text(Path("./testbot.txt").read_text())
    prog = compiler.compile()
    for i in prog:
        print(i)
    #print(prog)
