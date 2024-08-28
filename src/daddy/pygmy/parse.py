import ast

from typing import NoReturn
from itertools import chain
from dataclasses import dataclass
from contextlib import contextmanager

from . import LangError
from .lang import Const, Name, Op, Lookup, Call, BareCall, Attr, Item, \
    Assign, If, Func, Return, Var, Class, Pass, Block, Module, Code


class ForBinder(ast.NodeTransformer):
    def __init__(self, name, value, fname, src):
        self.name = name
        self.value = ast.Constant(value)
        self.fname = fname
        self.src = src

    def generic_visit(self, node):
        init = {}
        # adapted from ast.NodeTransformer.generic_visit
        for field, old_value in ast.iter_fields(node):
            if isinstance(old_value, list):
                new_values = []
                for value in old_value:
                    if isinstance(value, ast.AST):
                        value = self.visit(value)
                        if value is None:
                            continue
                        elif not isinstance(value, ast.AST):
                            new_values.extend(value)
                            continue
                    new_values.append(value)
                init[field] = new_values
            elif isinstance(old_value, ast.AST):
                new_node = self.visit(old_value)
                if new_node is not None:
                    init[field] = new_node
            else:
                init[field] = old_value
        new = node.__class__(**init)
        ast.copy_location(node, new)
        return new

    def visit_Name(self, node):
        if node.id == self.name:
            if isinstance(node.ctx, ast.Store):
                raise LangError("cannot assign for-loop index",
                                self.fname,
                                node.lineno,
                                node.col_offset,
                                self.src[node.lineno - 1])
            return self.generic_visit(self.value)
        return self.generic_visit(node)


class NodeTransformer(ast.NodeTransformer):
    def __init__(self, fname, src):
        self.fname = fname
        self.src = src
        self.env = {}

    def error(self, msg, node) -> NoReturn:
        raise LangError(msg,
                        self.fname,
                        node.lineno,
                        node.col_offset,
                        self.src[node.lineno - 1])

    def static(self, node, name=None):
        if name:
            n = ast.Module(body=[node])
            ast.fix_missing_locations(n)
            code = compile(n, self.fname, "exec")
        else:
            n = ast.Expression(body=node)
            ast.fix_missing_locations(n)
            code = compile(n, self.fname, "eval")
        try:
            if name is None:
                ret = eval(code, dict(self.env))
            else:
                loc = {}
                exec(code, dict(self.env), loc)
                ret = loc[name]
        except Exception as err:
            self.error(f"not static expression ({err})", node)
        return ret

    def _attr[T: Code](self, code: T, node) -> T:
        if isinstance(code, Code):
            # keep track of original source code
            code.__dict__["__ast__"] = node
            code.__dict__["__src__"] = self.src
            code.__dict__["__file__"] = self.fname
        return code

    def visit(self, node):
        try:
            return self._attr(super().visit(node), node)
        except AssertionError as err:
            a = err.args[0]
            if isinstance(a, str):
                self.error(a, node)
            else:
                self.error(*a)

    def generic_visit(self, node):
        self.error("unsupported syntax", node)

    def visit_Name(self, node):
        if isinstance((val := self.env.get(node.id, None)), int):
            return Const(val)
        else:
            return Name(node.id)


class CodeParser(NodeTransformer):
    def visit_Constant(self, node):
        assert isinstance(node.value, (int, bool)), "unsupported value"
        return Const(node.value)

    def visit_UnaryOp(self, node):
        match type(node.op):
            case ast.UAdd:
                return self.visit(node.operand)
            case ast.USub:
                return Op("-", (self.visit(node.operand),))
            case ast.Not:
                return Op("not", (self.visit(node.operand),))
            case _:
                self.error("unsupported operator", node.op)

    def visit_BinOp(self, node):
        match type(node.op):
            case ast.Add:
                return Op("+", (self.visit(node.left), self.visit(node.right)))
            case ast.Sub:
                return Op("-", (self.visit(node.left), self.visit(node.right)))
            case ast.Mult:
                return Op("*", (self.visit(node.left), self.visit(node.right)))
            case _:
                self.error("unsupported operator", node.op)

    def visit_BoolOp(self, node):
        match type(node.op):
            case ast.Or:
                return Op("or", tuple(self.visit(child)
                                      for child in node.values))
            case ast.And:
                return Op("and", tuple(self.visit(child)
                                       for child in node.values))
            case _:
                self.error("unsupported operator", node.op)

    def visit_Compare(self, node):
        args = [self.visit(a) for a in [node.left] + node.comparators]
        pairs = []
        for left, op, right in zip(args, node.ops, args[1:]):
            match type(op):
                case ast.Eq:
                    pairs.append(Op.make(node, self.src, self.fname,
                                         op="==",
                                         children=(left, right)))
                case ast.NotEq:
                    pairs.append(Op.make(node, self.src, self.fname,
                                         op="!=",
                                         children=(left, right)))
                case ast.Lt:
                    pairs.append(Op.make(node, self.src, self.fname,
                                         op="<",
                                         children=(left, right)))
                case ast.LtE:
                    pairs.append(Op.make(node, self.src, self.fname,
                                         op="<=",
                                         children=(left, right)))
                case ast.Gt:
                    pairs.append(Op.make(node, self.src, self.fname,
                                         op=">",
                                         children=(left, right)))
                case ast.GtE:
                    pairs.append(Op.make(node, self.src, self.fname,
                                         op=">=",
                                         children=(left, right)))
                case _:
                    self.error("unsupported operator", op)
        if len(pairs) == 1:
            return pairs[0]
        else:
            return Op("and", tuple(pairs))

    def visit_Call(self, node):
        assert not node.keywords, ("unsupported argument", node.keywords)
        assert isinstance(node.func, ast.Name), \
            ("unsupported function", node.func)
        return Call(node.func.id, tuple(self.visit(a) for a in node.args))

    def visit_Expr(self, node):
        assert isinstance(node.value, ast.Call), "unsupported bare expressions"
        return BareCall(self.visit(node.value))

    def visit_Attribute(self, node):
        return Attr(self.visit(node.value), node.attr)

    def visit_Subscript(self, node):
        return Item(self.visit(node.value), self.visit(node.slice))

    def visit_Assign(self, node):
        assert len(node.targets) == 1, "unsupported multiple assignments"
        target = self.visit(node.targets[0])
        assert isinstance(target, Lookup), \
            ("unsupported assignment target", node.targets[0])
        return Assign(target, self.visit(node.value), None)

    def visit_AugAssign(self, node):
        match type(node.op):
            case ast.Add:
                op = "+"
            case ast.Sub:
                op = "-"
            case _:
                self.error("unsupported operator", node.op)
        target = self.visit(node.target)
        assert isinstance(target, Lookup), \
            ("unsupported assignment target", node.target)
        return Assign(target, self.visit(node.value), op)

    def visit_If(self, node):
        try:
            cond = self.static(node.test)
        except Exception:
            cond = self
        if cond is self:
            t = Block(self.visit(s) for s in node.body)       # pyright: ignore
            e = Block(self.visit(s) for s in node.orelse)     # pyright: ignore
            return If(self.visit(node.test),
                      self._attr(t, node),
                      self._attr(e, node))                    # pyright: ignore
        elif cond:
            return Block(self.visit(s) for s in node.body)    # pyright: ignore
        else:
            return Block(self.visit(s) for s in node.orelse)  # pyright: ignore

    def visit_For(self, node):
        assert isinstance(node.target, ast.Name), \
            ("unsupported iterator", node.target)
        assert not node.orelse, "unsupported 'else' in for loop"
        body = []
        for val in self.static(node.iter):
            bind = ForBinder(node.target.id, val, self.fname, self.src)
            for child in node.body:
                bound = bind.visit(child)
                assert bound is not child
                body.append(self.visit(bound))
        return Block(body)                                    # pyright: ignore

    def visit_Return(self, node):
        if node.value is None:
            return Return()
        else:
            return Return(self.visit(node.value))

    def visit_Pass(self, _):
        return Pass()

    def visit_AnnAssign(self, node):
        self.error("forbidden nested declaration", node)

    def visit_FunctionDef(self, node):
        self.error("forbidden nested declaration", node)

    def visit_ClassDef(self, node):
        self.error("forbidden nested declaration", node)


class TopParser(NodeTransformer):
    def __init__(self, fname, src):
        super().__init__(fname, src)
        self.decl = {}
        self.parser = CodeParser(fname, src)
        self.parser.env = self.env
        self.var = {}
        self.cls = {}
        self.fun = {}

    @contextmanager
    def newscope(self):
        decl, self.decl = self.decl, {}
        var, self.var = self.var, {}
        yield
        self.decl, self.var = decl, var

    def visit_AnnAssign(self, node):
        assert isinstance(node.target, ast.Name), \
            ("not a variable declaration", node.target)
        assert (lno := self.decl.get(node.target.id, None)) is None, \
            f"already declared line {lno}"
        self.decl[node.target.id] = node.lineno
        if node.value is None:
            init = None
        else:
            init = self.static(node.value)
        if isinstance(node.annotation, ast.Subscript):
            assert isinstance(node.annotation.value, ast.Name), \
                ("unsupported type", node.annotation.value)
            assert isinstance(node.annotation.slice, ast.Name), \
                ("unsupported items type", node.annotation.slice)
            assert init is not None, "missing initial value"
            typ_ = node.annotation.slice.id
            try:
                init = tuple(init)
            except Exception:
                self.error("cannot iterate over init value", node.value)
            size = len(init)
        elif isinstance(node.annotation, ast.Name):
            typ_ = node.annotation.id
            size = None
        else:
            self.error("unsupported type", node.annotation)
        if typ_ in ("int", "bool"):
            typ_ = int
        elif typ_ in self.cls:
            typ_ = self.env[typ_]
        else:
            self.error("unsupported type", node.annotation)
        var = self._attr(Var(node.target.id, typ_, size, init), node)
        self.var[var.name] = var
        return var

    def visit_Assign(self, node):
        assert len(node.targets) == 1, "unsupported multiple assignments"
        assert isinstance(node.targets[0], ast.Name), \
            ("unsupported variable declaration", node.targets[0])
        assert (lno := self.decl.get(node.targets[0].id, None)) is None, \
            f"already declared line {lno}"
        self.decl[node.targets[0].id] = node.lineno
        self.env[node.targets[0].id] = self.static(node.value)

    def visit_FunctionDef(self, node):
        assert (lno := self.decl.get(node.name, None)) is None, \
            f"already declared line {lno}"
        self.decl[node.name] = node.lineno
        assert not node.decorator_list, \
            ("unsupported function decorators", node.decorator_list[0])
        assert node.args.vararg is None, \
            ("unsupported function arguments", node.args.vararg)
        assert node.args.kwarg is None, \
            ("unsupported function arguments", node.args.kwarg)
        assert not node.args.kwonlyargs, \
            ("unsupported function arguments", node.args.kwonlyargs[0])
        assert not (node.args.kw_defaults or node.args.defaults), \
            ("unsupported function arguments",
             (node.args.kw_defaults or node.args.defaults)[0])
        args = tuple(a.arg for a in chain(node.args.posonlyargs,
                                          node.args.args))
        body, glob, loca = [], [], []
        for child in node.body:
            if isinstance(child, ast.Global):
                assert not body, ("must come before statements", child)
                assert not loca, ("must come before local declarations", child)
                for n in child.names:
                    assert n not in args, \
                        (f"'{n}' declared as argument", child)
                    assert (d := self.var.get(n, None)) is not None, \
                        (f"undeclared variable {n}", child)
                    glob.append(d)
            elif isinstance(child, ast.AnnAssign):
                assert not body, ("must come before statements", child)
                with self.newscope():
                    var = self.visit(child)
                assert var.name not in args, \
                    (f"'{var.name}' is an argument", child)
                assert all(var.name != g.name for g in glob), \
                    (f"'{var.name}' is declared global", child)
                assert var.init is not None, ("missing initial value", child)
                loca.append(var)
            else:
                body.append(self.parser.visit(child))
        self.env[node.name] = self.static(node, node.name)
        block = self._attr(Block(body), node)                 # pyright: ignore
        self.fun[node.name] = self._attr(Func(node.name,
                                              args,
                                              block,
                                              tuple(glob),
                                              tuple(loca)),
                                         node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            assert alias.name != "*", ("unsupported '*'-import", alias)
            if alias.asname:
                name = alias.asname
            else:
                name = alias.name
            self.env[alias.name] = self.static(node, name)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.asname:
                name = alias.asname
            else:
                name = alias.name
            self.env[alias.name] = self.static(node, name)

    def visit_ClassDef(self, node):
        assert (lno := self.decl.get(node.name, None)) is None, \
            f"already declared line {lno}"
        self.decl[node.name] = node.lineno
        assert not node.keywords, ("unsupported syntax", node.keywords[0])
        for deco in node.decorator_list:
            assert isinstance(deco, ast.Name) and deco.id == "dataclass", \
                ("unsupported decorator", deco)
        parents = []
        for b in node.bases:
            assert isinstance(b, ast.Name), ("expected name", b)
            parents.append(b.id)
        with self.newscope():
            fields = []
            for s in node.body:
                v = self.visit(s)
                assert isinstance(v, Var), ("expected field declaration", s)
                fields.append(v)
        cls = self._attr(Class(node.name,
                         dataclass(self.static(node, node.name)),
                         tuple(fields),
                         tuple(parents)),
                         node)
        self.env[node.name] = cls.cls
        self.cls[cls.name] = cls


def parse(src):
    tree = ast.parse(src)
    ast.fix_missing_locations(tree)
    tp = TopParser("<string>", tuple(src.splitlines()))
    for c in tree.body:
        if (var := tp.visit(c)) is not None:
            if var.init is None:
                LangError.from_code(var, "missing initial value")
    return Module(var=tp.var, cls=tp.cls, fun=tp.fun)
