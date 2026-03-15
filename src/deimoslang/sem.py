from typing import Optional
from enum import Enum, auto
from copy import deepcopy

from .tokenizer import Tokenizer, Token
from .parser import *
from .types import *


class SemError(Exception):
    pass


class Scope:
    def __init__(self, parent: Optional["Scope"], is_block: bool):
        self.parent = parent
        self._syms: list[Symbol] = []
        self._mixins: set[str] = set()
        self._unique_player_selectors: set[PlayerSelector] = set()
        self._active_vars: list[Symbol] = []
        self._cleaned_vars: set[Symbol] = set() # if all branching scopes agree on cleanup, do not clean up the same variables again
        self.is_block = is_block # cleanup must not cross a block boundary as we do not have the notion of a moved variable

    def new_block(self) -> "Scope":
        return Scope(parent=self, is_block=True)

    def new_branch(self) -> "Scope":
        res = Scope(parent=self, is_block=False)

        # when a branch cleans up, the variables may still be active in the parent or other branches
        res._active_vars = self._active_vars[:]

        return res

    # Only blocks require lookup for now. Variables are only used internally and the sym is always locally known
    def lookup_block_by_name(self, literal: str) -> Symbol | None:
        for sym in reversed(self._syms):
            if sym.kind != SymbolKind.block:
                continue
            if sym.literal == literal:
                return sym
        if self.parent is not None:
            return self.parent.lookup_block_by_name(literal)
        return None

    def is_mixin(self, literal: str) -> bool:
        if literal in self._mixins:
            return True
        if self.parent is not None:
            return self.parent.is_mixin(literal)
        return False

    def is_block_local_var(self, sym: Symbol) -> bool:
        cur = self
        while sym is not None:
            if sym in cur._syms:
                return True
            elif cur.is_block:
                # must be checked after cur._syms
                break
            cur = cur.parent
        return False

    def put_sym(self, sym: Symbol) -> Symbol:
        self._syms.append(sym)
        return sym

    def activate_var(self, sym: Symbol):
        if sym in self._active_vars:
            raise SemError(f"Attempted to activate an already active variable: {sym}")
        self._active_vars.append(sym)

    def kill_var(self, sym: Symbol):
        if not self.is_block_local_var(sym):
            raise SemError(f"Attempted to kill a variable that isn't local to the current block")
        if sym not in self._active_vars:
            raise SemError(f"Attempted to kill an inactive variable: {sym}")
        self._cleaned_vars.add(sym)
        self._active_vars.remove(sym)


class Analyzer:
    def __init__(self, stmts: list[Stmt]):
        self.scope = Scope(parent=None, is_block=False)
        self._next_sym_id = 0
        self._block_defs: list[BlockDefStmt] = []
        self._stmts = stmts
        self._mixin_cache: dict[int, Symbol] = {} # {(block_sym, [mixed_syms]): mixed_block}

        self._block_nesting_level = 0
        self._loop_nesting_level = 0
        self._loop_nesting_stack = []

    def open_block(self):
        self.scope = self.scope.new_block()

        self._loop_nesting_stack.append(self._loop_nesting_level)
        self._loop_nesting_level = 0
        self._block_nesting_level += 1

    def close_block(self):
        self.scope = self.scope.parent
        self._loop_nesting_level = self._loop_nesting_stack.pop()
        self._block_nesting_level -= 1

    def open_loop(self):
        self.scope = self.scope.new_branch()
        self._loop_nesting_level += 1

    def close_loop(self):
        if len(self.scope._mixins) > 0:
            raise SemError("Mixins are only allowed at the top level of a block")
        self.scope = self.scope.parent
        self._loop_nesting_level-=1

    def gen_sym_id(self) -> int:
        result = self._next_sym_id
        self._next_sym_id += 1
        return result

    def gen_block_sym(self, name: str) -> Symbol:
        return self.scope.put_sym(Symbol(name, self.gen_sym_id(), SymbolKind.block))

    def gen_var_sym(self, name="anonymous") -> Symbol:
        return self.scope.put_sym(Symbol(f":{name}:", self.gen_sym_id(), SymbolKind.variable))

    def gen_label_sym(self, name="anonymous") -> Symbol:
        return self.scope.put_sym(Symbol(f":{name}", self.gen_sym_id(), SymbolKind.label))

    def def_var(self) -> Symbol:
        var_sym = self.gen_var_sym()
        self.scope.activate_var(var_sym)
        return var_sym

    def mark_var_dead(self, sym: Symbol):
        self.scope.kill_var(sym)

    def gen_cleanup_all_vars(self) -> StmtList:
        res = []
        for var in reversed(self.scope._active_vars):
            self.mark_var_dead(var)
            res.append(KillVarStmt(var))
        return StmtList(res)

    def sem_expr(self, expr: Expression) -> Expression:
        return expr # TODO

    def mix_block(self, stmt: BlockDefStmt, source_sym: Symbol) -> BlockDefStmt:
        def _mix_stmt(stmt: Stmt, mixins: set[str]):
            match stmt:
                case StmtList():
                    for inner in stmt.stmts:
                        _mix_stmt(inner, mixins)
                case CallStmt():
                    if isinstance(stmt.name, IdentExpression):
                        if stmt.name.ident in mixins:
                            sym = self.scope.lookup_block_by_name(stmt.name.ident)
                            if sym.defnode is None:
                                # The target is unfinished. Trust that it will be valid in the future
                                stmt.name = SymExpression(sym)
                            else:
                                assert isinstance(sym.defnode, BlockDefStmt)
                                if len(sym.defnode.mixins) > 0:
                                    raise SemError(f"Recursive mixins aren't allowed")
                                if sym is None:
                                    raise SemError(f"Unable to find symbol in scope: {stmt.name.ident}")
                                stmt.name = SymExpression(sym)
                        else:
                            raise SemError(f"Undeclared identifer during mixin stage: {stmt.name.ident}")
                    elif isinstance(stmt.name, SymExpression):
                        assert isinstance(stmt.name.sym.defnode, BlockDefStmt)
                        if len(stmt.name.sym.defnode.mixins) > 0:
                            raise SemError(f"Recursive mixins aren't allowed")
                    else:
                        raise SemError(f"Invalid call target: {stmt.name}")
                case WhileStmt():
                    _mix_stmt(stmt.body, mixins)
                case IfStmt():
                    _mix_stmt(stmt.branch_true, mixins)
                    _mix_stmt(stmt.branch_false, mixins)
                case LoopStmt():
                    _mix_stmt(stmt.body, mixins)
                case UntilRegion():
                    _mix_stmt(stmt.body, mixins)

        mixed_syms: dict[str, Symbol] = {}
        for m in stmt.mixins:
            ms = self.scope.lookup_block_by_name(m)
            if ms is None:
                raise SemError(f"Unable to resolve mixin: {m}")
            mixed_syms[m] = ms

        assert isinstance(stmt.name, SymExpression)
        key = hash((source_sym, frozenset(mixed_syms.values())))
        self._mixin_cache[key] = stmt.name.sym

        _mix_stmt(stmt.body, stmt.mixins)
        stmt.mixins = set()
        return stmt
    
    def lookup_constant(self, name: str) -> Expression | None:
        for stmt in self._stmts:
            if isinstance(stmt, ConstantDeclStmt) and stmt.name == name:
                return stmt.value
                
        # Not found
        return None

    def sem_stmt(self, stmt: Stmt) -> Stmt:
        match stmt:
            case TimerStmt():
                return stmt
            case ConstantDeclStmt():
                stmt.value = self.sem_expr(stmt.value)
                return stmt
            case BlockDefStmt():
                if not isinstance(stmt.name, IdentExpression):
                    raise SemError(f"Only IdentExpression is allowed during block declaration")
                sym = self.gen_block_sym(stmt.name.ident)
                stmt.body.stmts.append(ReturnStmt())
                self.open_block()
                stmt.body = self.sem_stmt(stmt.body)
                stmt.mixins = self.scope._mixins
                self.close_block()
                stmt.name = SymExpression(sym)
                sym.defnode = stmt
                if len(stmt.mixins) == 0:
                    self._block_defs.append(stmt)
                return None
            case StmtList():
                res = []
                for inner in stmt.stmts:
                    if semmed := self.sem_stmt(inner):
                        res.append(semmed)
                return StmtList(res)
            case CallStmt():
                if isinstance(stmt.name, IdentExpression):
                    sym = self.scope.lookup_block_by_name(stmt.name.ident)
                elif isinstance(stmt.name, SymExpression):
                    sym = stmt.name.sym
                else:
                    raise SemError(f"Malformed call: {stmt}")
                if self.scope.is_mixin(stmt.name.ident):
                    return stmt # defer mixins until the last possible moment
                else:
                    if sym is None:
                        raise SemError(f"Unable to find symbol in scope: {stmt.name.ident}")
                    if sym.defnode is not None:
                        assert isinstance(sym.defnode, BlockDefStmt)
                        if len(sym.defnode.mixins) > 0:
                            mixed_syms: dict[str, Symbol] = {}
                            for m in sym.defnode.mixins:
                                ms = self.scope.lookup_block_by_name(m)
                                if ms is None:
                                    raise SemError(f"Unable to resolve mixin: {m}")
                                mixed_syms[m] = ms

                            key = hash((sym, frozenset(mixed_syms.values())))
                            if key in self._mixin_cache:
                                sym = self._mixin_cache[key]
                            else:
                                mixed_sym = self.gen_block_sym(f":mixed_{stmt.name.ident}")
                                mixed_sym.defnode = deepcopy(sym.defnode)
                                mixed_sym.defnode.name = SymExpression(mixed_sym)
                                self.mix_block(mixed_sym.defnode, sym)
                                sym = mixed_sym
                                self._block_defs.append(sym.defnode)
                    stmt.name = SymExpression(sym)
                    return stmt
            case CommandStmt():
                if isinstance(stmt.command, ParallelCommandStmt):
                    for cmd in stmt.command.commands:
                        self.scope._unique_player_selectors.add(cmd.player_selector)
                    return stmt
                else:
                    # Original code for single commands
                    self.scope._unique_player_selectors.add(stmt.command.player_selector)
                    return stmt
            case IfStmt():
                stmt.expr = self.sem_expr(stmt.expr)

                self.scope = self.scope.new_branch()
                stmt.branch_true = self.sem_stmt(stmt.branch_true)
                self.scope = self.scope.parent

                self.scope = self.scope.new_branch()
                stmt.branch_false = self.sem_stmt(stmt.branch_false)
                self.scope = self.scope.parent
                return stmt
            case LoopStmt():
                self.open_loop()
                stmt.body = self.sem_stmt(stmt.body)
                self.close_loop()
                return stmt
            case WhileStmt():
                stmt.expr = self.sem_expr(stmt.expr)
                self.open_loop()
                stmt.body = self.sem_stmt(stmt.body)
                self.close_loop()
                return stmt
            case UntilStmt():
                self.open_loop()
                expr = self.sem_expr(stmt.expr) # sem ahead of time because it's used twice
                body = self.sem_stmt(stmt.body)
                self.close_loop()
                return IfStmt(
                    expr,
                    branch_true=StmtList([]),
                    branch_false=StmtList([
                        UntilRegion(
                            expr=expr,
                            body=WhileStmt(
                                UnaryExpression(Token(TokenKind.keyword_not, "not", LineInfo(-1, -1, -1)), expr),
                                body
                            ),
                        ),
                    ])
                )
            case TimesStmt():
                var_sym = self.def_var()
                prologue = [
                    DefVarStmt(var_sym),
                    WriteVarStmt(var_sym, NumberExpression(stmt.num)),
                ]
                epilogue = [
                    KillVarStmt(var_sym),
                ]
                cond = GreaterExpression(ReadVarExpr(SymExpression(var_sym)), NumberExpression(0))
                stmt.body.stmts.append(
                    WriteVarStmt(var_sym, SubExpression(ReadVarExpr(SymExpression(var_sym)), NumberExpression(1)))
                )

                res = StmtList(prologue + [self.sem_stmt(WhileStmt(cond, stmt.body))] + epilogue)
                self.mark_var_dead(var_sym)
                return res
            case ReturnStmt():
                if self._block_nesting_level <= 0:
                    raise SemError(f"Return used outside of block scope")
                return StmtList([
                    self.gen_cleanup_all_vars(),
                    stmt
                ])
            case BreakStmt():
                if self._loop_nesting_level <= 0:
                    raise SemError(f"Break used outside of loop scope")
                return stmt
            case DefVarStmt() | WriteVarStmt() | KillVarStmt():
                return stmt
            case MixinStmt():
                if not self.scope.is_block:
                    raise SemError("Mixin is only allowed inside blocks")
                self.scope._mixins.add(stmt.name)
                return None
            case _:
                raise SemError(f"Unhandled statement type: {stmt}")
        raise SemError(f"Statement fell through: {stmt}")

    def analyze_program(self):
        res = []
        for stmt in self._stmts:
            if semmed := self.sem_stmt(stmt):
                res.append(semmed)
        self._stmts = res


if __name__ == "__main__":
    from pathlib import Path

    toks = Tokenizer().tokenize(Path("./testbot.txt").read_text())
    parser = Parser(toks)
    parsed = (parser.parse())

    analyzer = Analyzer(parsed)
    analyzer.analyze_program()

    for block in analyzer._block_defs:
        print_cmd(str(block))

    for stmt in analyzer._stmts:
        print_cmd(str(stmt))
