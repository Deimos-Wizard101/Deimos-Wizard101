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

    log_literal = auto()
    log_window = auto()
    log_bagcount = auto()
    log_mana = auto()
    log_health = auto()
    log_gold = auto()

    jump = auto()
    jump_if = auto()
    jump_ifn = auto()

    enter_until = auto()

    label = auto()
    ret = auto()
    call = auto()
    deimos_call = auto()

    load_playstyle = auto()

    push_stack = auto()
    pop_stack = auto()
    write_stack = auto()

    nop = auto()

class Instruction:
    def __init__(self, kind: InstructionKind, data: Any | None = None) -> None:
        self.kind = kind
        self.data = data

    def __repr__(self) -> str:
        if self.data:
            return f"{self.kind.name} {self.data}"
        return f"{self.kind.name}"


class Compiler:
    def __init__(self, analyzer: Analyzer):
        self.analyzer = analyzer
        self._program: list[Instruction] = []
        self._stack_offset = 0
        self._stack_slots: dict[Symbol, int] = {}
        self._loop_label_stack = []

    @staticmethod
    def from_text(code: str) -> "Compiler":
        tokenizer = Tokenizer()
        parser = Parser(tokenizer.tokenize(code))
        analyzer = Analyzer(parser.parse())
        analyzer.analyze_program()
        return Compiler(analyzer=analyzer)

    def push_stack(self, sym: Symbol) -> int:
        self.emit(InstructionKind.push_stack)
        res = self._stack_offset
        self._stack_offset += 1
        self._stack_slots[sym] = res
        return res

    def pop_stack(self, sym: Symbol):
        del self._stack_slots[sym]
        self._stack_offset -= 1
        self.emit(InstructionKind.pop_stack)

    def stack_loc(self, sym: Symbol):
        return self._stack_slots[sym] - self._stack_offset

    def emit(self, kind: InstructionKind, data: Any | None = None):
        self._program.append(Instruction(kind, data))

    def gen_label(self, name="anonymous") -> Symbol:
        return Symbol(f":{name}:", self.analyzer.gen_sym_id(), SymbolKind.label)

    def emit_deimos_call(self, com: Command):
        self.emit(InstructionKind.deimos_call, [com.player_selector, com.kind.name, com.data])

    def compile_command(self, com: Command):
        match com.kind:
            case CommandKind.kill:
                self.emit(InstructionKind.kill)
            case CommandKind.sleep:
                self.emit(InstructionKind.sleep, com.data[0])
            case CommandKind.log:
                kind = com.data[0]
                match kind:
                    case LogKind.window:
                        self.emit(InstructionKind.log_window, [com.player_selector, com.data[1]])
                    case LogKind.bagcount:
                        self.emit(InstructionKind.log_bagcount, [com.player_selector])
                    case LogKind.health:
                        self.emit(InstructionKind.log_health, [com.player_selector])
                    case LogKind.mana:
                        self.emit(InstructionKind.log_mana, [com.player_selector])
                    case LogKind.gold:
                        self.emit(InstructionKind.log_gold, [com.player_selector])
                    case LogKind.literal:
                        self.emit(InstructionKind.log_literal, com.data[1:len(com.data)])
                    case _:
                        raise CompilerError(f"Unimplemented log kind: {com}")

            case CommandKind.sendkey | CommandKind.click | CommandKind.teleport \
                | CommandKind.goto | CommandKind.usepotion | CommandKind.buypotions \
                | CommandKind.relog | CommandKind.tozone:
                self.emit_deimos_call(com)

            case CommandKind.waitfor:
                # copy the original data to split inverted waitfor in two
                non_inverted_com = copy.copy(com)
                data1 = com.data[:]
                data1[1] = False
                non_inverted_com.data = data1
                self.emit_deimos_call(non_inverted_com)
                if com.data[1] == True:
                    self.emit_deimos_call(com)

            case CommandKind.load_playstyle:
                self.emit(InstructionKind.load_playstyle, com.data[0])
            case _:
                raise CompilerError(f"Unimplemented command: {com}")

    def process_labels(self, program: list[Instruction]):
        offsets = {}

        # discover labels
        for idx, instr in enumerate(program):
            match instr.kind:
                case InstructionKind.label:
                    sym = instr.data
                    offsets[sym] = idx
                case _:
                    pass

        # resolve labels
        for idx, instr in enumerate(program):
            match instr.kind:
                case InstructionKind.label:
                    program[idx] = Instruction(InstructionKind.nop)
                case InstructionKind.call | InstructionKind.jump:
                    sym = instr.data
                    offset = offsets[sym]
                    program[idx] = Instruction(instr.kind, offset-idx)
                case InstructionKind.jump_if | InstructionKind.jump_ifn | InstructionKind.enter_until:
                    assert(type(instr.data) == list)
                    sym = instr.data[1]
                    offset = offsets[sym]
                    program[idx] = Instruction(instr.kind, [instr.data[0], offset-idx])
                case _:
                    pass

        return program

    def compile_block_def(self, block_def: BlockDefStmt):
        if isinstance(block_def.name, SymExpression):
            # This is only safe because the sem stage ensures there's no nested blocks
            enter_block_label = block_def.name.sym
            self.emit(InstructionKind.label, enter_block_label)
            self._compile(block_def.body)
            self.emit(InstructionKind.ret)
        elif isinstance(block_def.name, IdentExpression):
            raise CompilerError(f"Encountered an unresolved block sym during compilation: {block_def}")
        else:
            raise CompilerError(f"Encountered a malformed block sym during compilation: {block_def}")

    def compile_call(self, call: CallStmt):
        if isinstance(call.name, SymExpression):
            self.emit(InstructionKind.call, call.name.sym)
            self.emit(InstructionKind.nop)
        elif isinstance(call.name, IdentExpression):
            raise CompilerError(f"Encountered an unresolved call during compilation: {call}")
        else:
            raise CompilerError(f"Encountered a malformed call during compilation: {call}")

    def prep_expression(self, expr: Expression):
        match expr:
            case BinaryExpression():
                self.prep_expression(expr.lhs)
                self.prep_expression(expr.rhs)
            case ReadVarExpr():
                if isinstance(expr.loc, SymExpression):
                    expr.loc = StackLocExpression(self.stack_loc(expr.loc.sym))
                else:
                    raise CompilerError(f"Malformed ReadVarExpr: {expr}")
            case SelectorGroup():
                self.prep_expression(expr.expr)
            case UnaryExpression():
                self.prep_expression(expr.expr)
            case NumberExpression() | StringExpression() | KeyExpression() | CommandExpression() | XYZExpression() | IdentExpression() | StackLocExpression() | Eval():
                pass
            case _:
                raise CompilerError(f"Unhandled expression type: {expr}")

    def compile_if_stmt(self, stmt: IfStmt):
        after_if_label = self.gen_label("after_if")
        branch_true_label = self.gen_label("branch_true")
        self.prep_expression(stmt.expr)
        self.emit(InstructionKind.jump_if, [stmt.expr, branch_true_label])
        self._compile(stmt.branch_false)
        self.emit(InstructionKind.jump, after_if_label)
        self.emit(InstructionKind.label, branch_true_label)
        self._compile(stmt.branch_true)
        self.emit(InstructionKind.label, after_if_label)

    def compile_loop_stmt(self, stmt: LoopStmt):
        start_loop_label = self.gen_label("start_loop")
        end_loop_label = self.gen_label("end_loop")
        self._loop_label_stack.append(end_loop_label)
        self.emit(InstructionKind.label, start_loop_label)
        self._compile(stmt.body)
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
        self._compile(stmt.body)
        self.emit(InstructionKind.jump_if, [stmt.expr, start_while_label])
        self.emit(InstructionKind.label, end_while_label)
        self._loop_label_stack.pop()

    def compile_until_stmt(self, stmt: UntilStmt):
        start_until_label = self.gen_label("start_until")
        end_until_label = self.gen_label("end_until")
        self._loop_label_stack.append(end_until_label)
        self.prep_expression(stmt.expr)
        self.emit(InstructionKind.jump_if, [stmt.expr, end_until_label])
        self.emit(InstructionKind.enter_until, [stmt.expr, end_until_label]) # Order is important here. If this is after the label we blow the stack
        self.emit(InstructionKind.label, start_until_label)
        self._compile(stmt.body)
        self.emit(InstructionKind.jump_ifn, [stmt.expr, start_until_label])
        self.emit(InstructionKind.label, end_until_label)
        self._loop_label_stack.pop()

    def _compile(self, stmt: Stmt):
        match stmt:
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
            case UntilStmt():
                self.compile_until_stmt(stmt)
            case DefVarStmt():
                self.push_stack(stmt.sym)
            case KillVarStmt():
                self.pop_stack(stmt.sym)
            case WriteVarStmt():
                self.prep_expression(stmt.expr)
                self.emit(InstructionKind.write_stack, [self.stack_loc(stmt.sym), stmt.expr])
            case BreakStmt():
                label = self._loop_label_stack[-1]
                self.emit(InstructionKind.jump, label)
            case ReturnStmt():
                self.emit(InstructionKind.ret)
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
