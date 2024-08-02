import ast

from typing import NoReturn
from itertools import chain

from . import LangError
from .lang import Const, Name, Op, Lookup, Call, BareCall, Attr, Item, Loop, \
    Comprehension, Assign, If, For, Func, Return, Var, Struct, Param


class NodeTransformer(ast.NodeTransformer):
    def __init__(self, fname, src):
        self.fname = fname
        self.src = src

    def error(self, msg, node) -> NoReturn:
        raise LangError(msg,
                        self.fname,
                        node.lineno,
                        node.col_offset,
                        self.src[node.lineno - 1])

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
        if not isinstance(func, Lookup):
            self.error("unsupported function", node.func)
        return Call(func, tuple(self.visit(a) for a in node.args))

    def visit_Expr(self, node):
        if not isinstance(node.value, ast.Call):
            self.error("bare expressions not supported", node)
        elif node.value.keywords:
            self.error("unsupported argument", node.value.keywords)
        func = self.visit(node.value.func)
        if not isinstance(func, Lookup):
            self.error("unsupported function", node.value.func)
        return BareCall(Call.make(node,
                                  func,
                                  tuple(self.visit(a)
                                        for a in node.value.args)))

    def visit_Attribute(self, node):
        return Attr(self.visit(node.value), node.attr)

    def visit_Subscript(self, node):
        return Item(self.visit(node.value), self.visit(node.slice))

    def visit_GeneratorExp(self, node):
        if len(node.generators) != 1:
            self.error("unsupported multiple generators", node.generators[1])
        gen = node.generators[0]
        if not isinstance(gen.target, ast.Name):
            self.error("unsupported iterator", gen.target)
        loop = Loop.make(node, self.src, self.fname,
                         name=self.visit(gen.target),
                         iter=self.visit(gen.iter))
        match len(gen.ifs):
            case 0:
                cond = Const.make(node, self.src, self.fname, val=True)
            case 1:
                cond = self.visit(gen.ifs[0])
            case _:
                cond = Op("and", tuple(self.visit(i) for i in gen.ifs))
        return Comprehension(self.visit(node.elt), loop, cond)

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
        return For(Loop.make(node, self.src, self.fname,
                             name=self.visit(node.target),
                             iter=self.visit(node.iter)),
                   tuple(self.visit(s) for s in node.body))

    def visit_Return(self, node):
        if node.value is None:
            return Return()
        else:
            return Return(self.visit(node.value))


class TopParser(NodeTransformer):
    def __init__(self, fname, src):
        super().__init__(fname, src)
        self.parser = CodeParser(fname, src)

    def visit_AnnAssign(self, node):
        if not isinstance(node.target, ast.Name):
            self.error("unsupported variable declaration", node.target)
        if isinstance(node.annotation, ast.Subscript):
            if not isinstance(node.annotation.value, ast.Name):
                self.error("unsupported type", node.annotation.value)
            typ_ = node.annotation.value.id
            if not isinstance(node.annotation.slice, (ast.Name, ast.Constant)):
                self.error("unsupported size", node.annotation.slice)
            size = self.visit(node.annotation.slice)
            if isinstance(size, Name):
                size = size.id
        elif isinstance(node.annotation, ast.Name):
            typ_ = node.annotation.id
            size = None
        else:
            self.error("unsupported type", node.annotation)
        # TODO: allow init with static comprehension
        return Var(node.target.id,
                   typ_,
                   size,
                   None if node.value is None else self.visit(node.value))

    def visit_Assign(self, node):
        if not len(node.targets) == 1:
            self.error("unsupporter multiple assignments", node)
        if not isinstance(node.targets[0], ast.Name):
            self.error("unsupported variable declaration", node.targets[0])
        if isinstance(node.value, ast.Constant):
            if not isinstance(node.value.value, int):
                self.error("unsupported type for parameter", node.value)
            return Param(node.targets[0].id, node.value.value)
        elif isinstance(node.value, ast.Name):
            return Param(node.targets[0].id, node.value.id)
        else:
            self.error("unsupported parameter initialisation", node.value)

    def visit_List(self, node):
        ret = []
        for elt in node.elts:
            v = self.visit(elt)
            ret.append(v.val if isinstance(v, Const) else v)
        return ret

    def visit_Dict(self, node):
        ret = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Name):
                k = k.id
            elif isinstance(k, ast.Constant) and isinstance(k.value, str):
                k = k.value
            else:
                self.error("unsupported key", k)
            v = self.visit(v)
            ret[k] = v.val if isinstance(v, Const) else v
        return ret

    def visit_Constant(self, node):
        if not isinstance(node.value, (int, bool)):
            self.error("unsupported value", node)
        return node.value

    def visit_FunctionDef(self, node):
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
        return Func(node.name,
                    args,
                    tuple(self.parser.visit(child) for child in node.body))

    def visit_ClassDef(self, node):
        if node.keywords:
            self.error("unsupported syntax", node.keywords[0])
        parents = []
        for b in node.bases:
            if not isinstance(b, ast.Name):
                self.error("expected name", b)
            parents.append(b.id)
        fields = []
        for s in node.body:
            v = self.visit(s)
            if not isinstance(v, Var):
                self.error("unexpected field", s)
            fields.append(v)
        return Struct(node.name, tuple(fields), tuple(parents))


def parse(src):
    tree = ast.parse(src)
    ast.fix_missing_locations(tree)
    tp = TopParser("<string>", tuple(src.splitlines()))
    return [tp.visit(c) for c in tree.body]
