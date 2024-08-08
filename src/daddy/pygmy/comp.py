from contextlib import contextmanager

from . import LangError
from .lang import Code


class Visitor:
    def visit(self, node):
        if isinstance(node, tuple):
            return tuple(self.visit(n) for n in node)
        cls = node.__class__.__name__
        handler = getattr(self, f"visit_{cls}", self.generic_visit)
        return handler(node)

    def generic_visit(self, node):
        for _, child in node:
            if isinstance(child, tuple):
                for c in child:
                    if isinstance(c, Code):
                        self.visit(c)
            elif isinstance(child, Code):
                self.visit(child)


class CheckNames(Visitor):
    def __init__(self, mod):
        self.var = mod.var
        self.cls = mod.cls
        self.fun = mod.fun
        self.assign = False
        self.decl = self.var | self.cls | self.fun

    @contextmanager
    def __call__(self, **args):
        old = {}
        for k, v in args.items():
            old[k] = getattr(self, k)
            setattr(self, k, v)
        yield
        for k, v in old.items():
            setattr(self, k, v)

    # declarations

    #  def visit_Var(self, node):
    #      pass
    #
    #  def visit_Class(self, node):
    #      pass
    #
    #  def visit_Func(self, node):
    #      pass

    # statements

    #  def visit_Pass(self, node):
    #      pass

    def visit_Assign(self, node):
        with self(assign=True):
            self.visit(node.target)
        self.visit(node.value)

    #  def visit_BareCall(self, node):
    #      pass

    #  def visit_For(self, node):
    #      pass
    #
    #  def visit_If(self, node):
    #      pass
    #
    #  def visit_Return(self, node):
    #      pass

    # expressions

    #  def visit_Const(self, node):
    #      pass

    def visit_Name(self, node):
        if self.assign and node.id not in self.var:
            LangError.from_code(node, "no such variable")
        elif node.id not in self.decl:
            LangError.from_code(node, "not declared")
        return self.var[node.id]

    def visit_Attr(self, node):
        with self(assign=False):
            value = self.visit(node.value)
            # TODO: check that value has attribute .attr

    def visit_Item(self, node):
        with self(assign=False):
            value = self.visit(node.value)
            # TODO: check that value is list

    def visit_Call(self, node):
        if node.func not in self.fun:
            LangError.from_code(node, "no such function")
        self.generic_visit(node)

    #  def visit_Op(self, node):
    #      # TODO: check nesting of operations => int-linear expression
    #      pass
