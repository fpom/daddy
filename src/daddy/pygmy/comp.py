from typing import Iterable
from itertools import chain

from .lang import Module, Code, Name
from . import LangError
# from ..dddlib import domain


class Visitor:
    def visit(self, node, **args):
        cls = node.__class__.__name__
        visit = getattr(self, f"visit_{cls}", self.generic_visit)
        visit(node, **args)

    def visit_tuple(self, node, **args):
        for child in node:
            self.visit(child, **args)

    def generic_visit(self, node, **args):
        if isinstance(node, Code):
            for _, child in node.iterfields():
                self.visit(child, **args)

    # def visit_Module(self, node, **args):
    #     pass
    #
    # def visit_Var(self, node, **args):
    #     pass
    #
    # def visit_Class(self, node, **args):
    #     pass
    #
    # def visit_Func(self, node, **args):
    #     pass
    #
    # def visit_Pass(self, node, **args):
    #     pass
    #
    # def visit_Assign(self, node, **args):
    #     pass
    #
    # def visit_BareCall(self, node, **args):
    #     pass
    #
    # def visit_If(self, node, **args):
    #     pass
    #
    # def visit_Return(self, node, **args):
    #     pass
    #
    # def visit_Const(self, node, **args):
    #     pass
    #
    # def visit_Name(self, node, **args):
    #     pass
    #
    # def visit_Attr(self, node, **args):
    #     pass
    #
    #  def visit_Item(self, node, **args):
    #      pass
    #
    #  def visit_Call(self, node, **args):
    #      pass
    #
    #  def visit_Op(self, node, **args):
    #      pass


class NameCheck(Visitor):
    "check that names are correctly loaded/assigned"

    def __call__(self, mod):
        for fun in mod.fun.values():
            self.visit(fun)

    def visit_Func(self, node):
        # parser ensures that globals are declared
        arg = set(node.args)
        var = set(v.name for v in chain(node.globals, node.locals))
        for stmt in node.body:
            self.visit(stmt, arg=arg, var=var)

    def visit_Assign(self, node, arg, var):
        if isinstance(node.target, Name) and node.target.id in arg:
            LangError.from_code(node, "cannot assign parameter")
        self.generic_visit(node, arg=arg, var=var)

    def visit_Name(self, node, arg, var):
        if node.id not in arg | var:
            LangError.from_code(node, "not a (visible) name")


class GetFunctions(Visitor):
    def __call__(self, fun, mod):
        calls = set()
        self.visit_Func(fun, mod, calls, [])
        return calls

    def visit_Func(self, node, mod, calls, stack):
        calls.add(node.name)
        for stmt in node.body:
            self.visit(stmt, mod=mod, calls=calls, stack=stack + [node.name])

    def visit_Call(self, node, mod, calls, stack):
        if None in stack:
            LangError.from_code(node, "forbidden call in expression")
        if node.func in stack:
            s = "->".join(stack) + f"=>{node.func}"
            LangError.from_code(node, f"forbidden recursive call: {s}")
        if node.func not in mod.fun:
            LangError.from_code(node, "function not defined")
        calls.add(node.func)
        self.generic_visit(
            mod.fun[node.func], mod=mod, calls=calls, stack=stack + [node.func]
        )

    def visit_Op(self, node, mod, calls, stack):
        self.generic_visit(node, mod=mod, calls=calls, stack=stack + [None])


def scope(mod: Module, functions: Iterable[str] = []) -> Module:
    functions = set(functions or (n for n, f in mod.fun.items() if not f.args))
    getfun = GetFunctions()
    for fname in list(functions):
        functions.update(getfun(mod.fun[fname], mod))
    var, cls, fun = {}, {}, {}
    for fname in functions:
        f = mod.fun[fname]
        g = list(f.globals)
        s = {}
        for v in f.globals:
            var[v.name] = v
            if v.type in mod.cls:
                cls[v.type] = mod.cls[v.type]
        for v in f.locals:
            n = s[v.name] = f"{f.name}_{v.name}"
            v = var[n] = v(name=n)
            g.append(v)
            if v.type in mod.cls:
                cls[v.type] = mod.cls[v.type]
        fun[fname] = f(
            locals=(), globals=tuple(g), body=tuple(b.subst(s) for b in f.body)
        )
    return Module(var=var, cls=cls, fun=fun)
