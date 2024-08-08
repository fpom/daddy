import ast

from typing import NoReturn
from itertools import chain
from dataclasses import dataclass
from collections import namedtuple
from contextlib import contextmanager
from inspect import isclass

from . import LangError
from .lang import Const, Name, Op, Lookup, Call, BareCall, Attr, Item, \
    Assign, If, For, Func, Return, Var, Class, Pass


class ACDC:
    _known = {}
    _decl = Class("_ACDC_")

    @classmethod
    def make(cls, value):
        if isinstance(value, cls):
            return cls
        value = dict(value)
        fields = {}
        for f in cls._decl.fields:
            val = value[f.name]
            if f.size is not None and f.size != len(val):
                raise ValueError("wrong length")
            if issubclass(f.type, ACDC):
                if f.size is None:
                    fields[f.name] = f.type.make(val)
                else:
                    fields[f.name] = [f.type.make(v) for v in val]
            else:
                if f.size is None:
                    fields[f.name] = f.type(val)
                else:
                    fields[f.name] = [f.type(v) for v in val]
        return cls(**fields)


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
        return self._dc2d(ret)

    def _dc2d(self, obj):
        if hasattr(obj, "__dataclass_fields__") and \
                (cname := obj.__class__.__name__) in self.env and \
                isinstance(obj, self.env[cname]):
            return {k: self._dc2d(getattr(obj, k))
                    for k in obj.__dataclass_fields__}
        else:
            return obj

    def visit(self, node):
        code = super().visit(node)
        # insert __ast__ into object to keep track of original source code
        try:
            # may fail in TopParser for variables initialisations
            code.__dict__["__ast__"] = node
            code.__dict__["__src__"] = self.src
            code.__dict__["__file__"] = self.fname
        except Exception:
            pass
        return code

    def generic_visit(self, node):
        self.error("unsupported syntax", node)

    def visit_Name(self, node):
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
        return If(self.visit(node.test),
                  tuple(self.visit(s) for s in node.body),
                  tuple(self.visit(s) for s in node.orelse))

    def visit_For(self, node):
        if not isinstance(node.target, ast.Name):
            self.error("unsupported iterator", node.target)
        if node.orelse:
            self.error("unsupported 'else' in for loop", node)
        items = self.static(ast.Call(func=ast.Name(id="list",
                                                   ctx=ast.Load()),
                                     args=[node.iter]))
        return For(name=self.visit(node.target),
                   items=tuple(items),
                   body=tuple(self.visit(s) for s in node.body))

    def visit_Return(self, node):
        if node.value is None:
            return Return()
        else:
            return Return(self.visit(node.value))

    def visit_Pass(self, node):
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
    def newdecl(self):
        decl, self.decl = self.decl, {}
        yield
        self.decl = decl

    def visit_AnnAssign(self, node):
        if not isinstance(node.target, ast.Name):
            self.error("unsupported variable declaration", node.target)
        if (lno := self.decl.get(node.target.id, None)) is not None:
            self.error(f"already declared line {lno}", node)
        self.decl[node.target.id] = node.lineno
        if isinstance(node.annotation, ast.Subscript):
            if not isinstance(node.annotation.value, ast.Name):
                self.error("unsupported type", node.annotation.value)
            typ_ = node.annotation.value.id
            if not isinstance(node.annotation.slice, (ast.Name, ast.Constant)):
                self.error("unsupported size", node.annotation.slice)
            size = self.static(node.annotation.slice)
            if not isinstance(size, int):
                self.error("invalid size", node.annotation.slice)
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
        if node.value is None:
            init = None
        else:
            # TODO: check type here instead of in static
            init = self.static(node.value)
        var = Var(node.target.id, typ_, size, init)
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
        self.env[node.name] = self.static(node, node.name)
        self.fun[node.name] = Func(node.name,
                                   args,
                                   tuple(self.parser.visit(child)
                                         for child in node.body))

    def visit_ClassDef(self, node):
        if (lno := self.decl.get(node.name, None)) is not None:
            self.error(f"already declared line {lno}", node)
        self.decl[node.name] = node.lineno
        if node.keywords:
            self.error("unsupported syntax", node.keywords[0])
        parents = []
        for b in node.bases:
            if not isinstance(b, ast.Name):
                self.error("expected name", b)
            parents.append(b.id)
        with self.newdecl():
            fields = []
            for s in node.body:
                v = self.visit(s)
                if not isinstance(v, Var):
                    self.error("expected field", s)
                fields.append(v)
        c = Class(node.name, tuple(fields), tuple(parents))
        self.env[node.name] = self._dataclass(self.static(node, node.name), c)
        self.cls[c.name] = c

    def _dataclass(self, cls, decl):
        class _ACDC_(dataclass(cls), ACDC):
            _known = {n: self.env[n] for n in self.cls}
            _decl = decl
        return _ACDC_


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
