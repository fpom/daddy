import ast

from typing import NoReturn
from itertools import chain
from dataclasses import dataclass
from collections import namedtuple
from contextlib import contextmanager

from . import LangError
from .lang import Const, Name, Op, Lookup, Call, BareCall, Attr, Item, \
    Assign, If, Func, Return, Var, Class, Pass, Block


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

    def _attr(self, code, node):
        if code is not None:
            # keep track of original source code
            code.__dict__["__ast__"] = node
            code.__dict__["__src__"] = self.src
            code.__dict__["__file__"] = self.fname
        return code

    def visit(self, node):
        return self._attr(super().visit(node), node)

    def generic_visit(self, node):
        self.error("unsupported syntax", node)

    def visit_Name(self, node):
        if isinstance((val := self.env.get(node.id, None)), int):
            return Const(val)
        else:
            return Name(node.id)


class CodeParser(NodeTransformer):
    def visit_Constant(self, node):
        if not isinstance(node.value, (int, bool)):
            self.error("unsupported value", node)
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
        if node.keywords:
            self.error("unsupported argument", node.keywords)
        func = self.visit(node.func)
        if not isinstance(func, Name):
            self.error("unsupported function", node.func)
        return Call(func.id, tuple(self.visit(a) for a in node.args))

    def visit_Expr(self, node):
        if not isinstance(node.value, ast.Call):
            self.error("bare expressions not supported", node)
        elif node.value.keywords:
            self.error("unsupported argument", node.value.keywords)
        func = self.visit(node.value.func)
        if not isinstance(func, Name):
            self.error("unsupported function", node.value.func)
        return BareCall(Call.make(node,
                                  func.id,
                                  tuple(self.visit(a)
                                        for a in node.value.args)))

    def visit_Attribute(self, node):
        return Attr(self.visit(node.value), node.attr)

    def visit_Subscript(self, node):
        return Item(self.visit(node.value), self.visit(node.slice))

    def visit_Assign(self, node):
        if len(node.targets) != 1:
            self.error("unsupported multiple assignments", node)
        target = self.visit(node.targets[0])
        if not isinstance(target, Lookup):
            self.error("unsupported assignment target", target)
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
        if not isinstance(target, Lookup):
            self.error("unsupported assignment target", node.target)
        return Assign(target, self.visit(node.value), op)

    def visit_If(self, node):
        try:
            cond = self.static(node.test)
        except Exception:
            cond = self
        if cond is self:
            return If(self.visit(node.test),
                      self._attr(Block(self.visit(s) for s in node.body),
                                 node),
                      self._attr(Block(self.visit(s) for s in node.orelse),
                                 node))
        elif cond:
            return Block(self.visit(s) for s in node.body)
        else:
            return Block(self.visit(s) for s in node.orelse)

    def visit_For(self, node):
        if not isinstance(node.target, ast.Name):
            self.error("unsupported iterator", node.target)
        if node.orelse:
            self.error("unsupported 'else' in for loop", node)
        body = []
        for val in self.static(node.iter):
            bind = ForBinder(node.target.id, val, self.fname, self.src)
            for child in node.body:
                bound = bind.visit(child)
                assert bound is not child
                body.append(self.visit(bound))
        return Block(body)

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
        if not isinstance(node.target, ast.Name):
            self.error("unsupported variable declaration", node.target)
        if (lno := self.decl.get(node.target.id, None)) is not None:
            self.error(f"already declared line {lno}", node)
        self.decl[node.target.id] = node.lineno
        if node.value is None:
            init = None
        else:
            init = self.static(node.value)
        if isinstance(node.annotation, ast.Subscript):
            if not isinstance(node.annotation.value, ast.Name):
                self.error("unsupported type", node.annotation.value)
            if not isinstance(node.annotation.slice, ast.Name):
                self.error("unsupported items type", node.annotation.slice)
            if init is None:
                self.error("missing initial value", node)
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
        if not len(node.targets) == 1:
            self.error("unsupporter multiple assignments", node)
        if not isinstance(node.targets[0], ast.Name):
            self.error("unsupported variable declaration", node.targets[0])
        if (lno := self.decl.get(node.targets[0].id, None)) is not None:
            self.error(f"already declared line {lno}", node)
        self.decl[node.targets[0].id] = node.lineno
        self.env[node.targets[0].id] = self.static(node.value)

    def visit_FunctionDef(self, node):
        if (lno := self.decl.get(node.name, None)) is not None:
            self.error(f"already declared line {lno}", node)
        self.decl[node.name] = node.lineno
        if node.returns:
            self.error("unsupported function annotation", node.returns)
        if node.decorator_list:
            self.error("unsupported function decorators",
                       node.decorator_list[0])
        if node.args.vararg:
            self.error("unsupported function arguments", node.args.vararg)
        if node.args.kwarg:
            self.error("unsupported function arguments", node.args.kwarg)
        if node.args.kwonlyargs:
            self.error("unsupported function arguments",
                       node.args.kwonlyargs[0])
        if node.args.kw_defaults or node.args.defaults:
            self.error("unsupported function arguments",
                       (node.args.kw_defaults or node.args.defaults)[0])
        args = tuple(a.arg for a in chain(node.args.posonlyargs,
                                          node.args.args))
        body, glob, loca = [], [], []
        for child in node.body:
            if isinstance(child, ast.Global):
                if body:
                    self.error("must come before statements", child)
                elif loca:
                    self.error("must come before local declarations", child)
                for n in child.names:
                    if n in args:
                        self.error(f"'{n}' declared as argument", child)
                    if (d := self.var.get(n, None)) is None:
                        self.error(f"undeclared variable {n}", child)
                    else:
                        glob.append(d)
            elif isinstance(child, ast.AnnAssign):
                if body:
                    self.error("must come before statements", child)
                with self.newscope():
                    var = self.visit(child)
                if var.name in args:
                    self.error(f"'{var.name}' is an argument", child)
                if any(var.name == g.name for g in glob):
                    self.error(f"'{var.name}' is declared global", child)
                if var.init is None:
                    self.error("missing initial value", child)
                loca.append(var)
            else:
                body.append(self.parser.visit(child))
        self.env[node.name] = self.static(node, node.name)
        self.fun[node.name] = self._attr(Func(node.name,
                                              args,
                                              self._attr(Block(body), node),
                                              tuple(glob),
                                              tuple(loca)),
                                         node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name == "*":
                self.error("unsupported '*'-import", alias)
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
        if (lno := self.decl.get(node.name, None)) is not None:
            self.error(f"already declared line {lno}", node)
        self.decl[node.name] = node.lineno
        if node.keywords:
            self.error("unsupported syntax", node.keywords[0])
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Name) or deco.id != "dataclass":
                self.error("unsupported decorator", deco)
        parents = []
        for b in node.bases:
            if not isinstance(b, ast.Name):
                self.error("expected name", b)
            parents.append(b.id)
        with self.newscope():
            fields = []
            for s in node.body:
                v = self.visit(s)
                if not isinstance(v, Var):
                    self.error("expected field", s)
                fields.append(v)
        cls = self._attr(Class(node.name,
                         dataclass(self.static(node, node.name)),
                         tuple(fields),
                         tuple(parents)),
                         node)
        self.env[node.name] = cls.cls
        self.cls[cls.name] = cls


module = namedtuple("module", ["var", "cls", "fun"])


def parse(src):
    tree = ast.parse(src)
    ast.fix_missing_locations(tree)
    tp = TopParser("<string>", tuple(src.splitlines()))
    for c in tree.body:
        if (var := tp.visit(c)) is not None:
            if var.init is None:
                LangError.from_code(var, "missing initial value")
    return module(tp.var, tp.cls, tp.fun)
