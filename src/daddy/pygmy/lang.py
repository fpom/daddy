import ast
import io

from dataclasses import dataclass, fields
from abc import ABC
from typing import Self, Optional

from . import LangError

#
# base class
#


@dataclass(frozen=True)
class Code(ABC):
    def py(self):
        raise NotImplementedError

    @classmethod
    def make(cls, *srcref, **fields) -> Self:
        obj = cls(**fields)
        if len(srcref) == 1 and isinstance((parent := srcref[0]), Code):
            obj.__dict__["__ast__"] = parent.__ast__    # pyright: ignore
            obj.__dict__["__src__"] = parent.__src__    # pyright: ignore
            obj.__dict__["__file__"] = parent.__file__  # pyright: ignore
        elif (len(srcref) == 3
              and isinstance((_ast := srcref[0]), ast.AST)
              and isinstance((_src := srcref[1]), tuple)
              and isinstance((_file := srcref[2]), str)):
            obj.__dict__["__ast__"] = _ast
            obj.__dict__["__src__"] = _src
            obj.__dict__["__file__"] = _file
        elif len(srcref) == 1:
            raise TypeError(f"unexpected argument: {srcref[0]=}")
        else:
            raise TypeError(f"unexpected arguments: {srcref=}")
        return obj

    def fields(self):
        for f in fields(self):
            yield f.name, getattr(self, f.name)

    def __call__(self, **fields) -> Self:
        f = {n: v for n, v in self.fields()} | fields
        return self.make(self, **f)

    def subst(self, nmap):
        init = {}
        for pair in self.fields():
            name, value = pair
            if value is None:
                init[name] = None
            elif isinstance(value, Code):
                init[name] = value.subst(nmap)
            elif isinstance(value, tuple) and \
                    value and isinstance(value[0], Code):
                init[name] = tuple(v.subst(nmap) for v in value)
            else:
                init[name] = value
        return self.make(self, **init)

    def bind(self, nmap):
        return self.subst(nmap)


@dataclass(frozen=True)
class Compound(Code, ABC):
    def py(self, prefix=""):
        out = io.StringIO()
        for indent, *line in self._py():
            out.write(prefix)
            out.write("    " * indent)
            out.write(" ".join(line))
            out.write("\n")
        return out.getvalue()

    def _py(self):
        raise NotImplementedError


#
# expressions
#


@dataclass(frozen=True)
class Expr(Code, ABC):
    pass


@dataclass(frozen=True)
class Const(Expr):
    val: int

    def py(self):
        return repr(self.val)


@dataclass(frozen=True)
class Op(Expr):
    op: str
    children: tuple[Expr, ...]

    def py(self):
        if len(self.children) == 1:
            child = self.children[0].py()
            if isinstance(self.children[0], Op):
                child = f"({child})"
            return f"{self.op} {child}"
        else:
            return f" {self.op} ".join(f"({c.py()})" if isinstance(c, Op)
                                       else f"{c.py()}" for c in self.children)


@dataclass(frozen=True)
class Lookup(Expr, ABC):
    def bind(self, nmap, lvalue=False):
        raise NotImplementedError("abstract method")


@dataclass(frozen=True)
class Name(Lookup):
    id: str

    def py(self):
        return self.id

    def subst(self, nmap):
        if (val := nmap.get(self.id, None)) is not None:
            if isinstance(val, int):
                return Const.make(self, val=val)
            elif isinstance(val, Code):
                return val
            else:
                raise TypeError(f"cannot substitute with {val}")
        return self

    def bind(self, nmap, lvalue=False):
        if lvalue:
            return self
        else:
            return self.subst(nmap)


@dataclass(frozen=True)
class Attr(Lookup):
    value: Lookup
    attr: str

    def py(self):
        if isinstance(self.value, Op):
            return f"({self.value.py()}).{self.attr}"
        else:
            return f"{self.value.py()}.{self.attr}"

    def bind(self, nmap, lvalue=True):
        return self.make(self,
                         value=self.value.bind(nmap, lvalue),
                         attr=self.attr)


@dataclass(frozen=True)
class Item(Lookup):
    value: Lookup
    item: Expr

    def py(self):
        if isinstance(self.value, Op):
            return f"({self.value.py()})[{self.item.py()}]"
        else:
            return f"{self.value.py()}[{self.item.py()}]"

    def bind(self, env, lvalue=False):
        return self.make(self,
                         value=self.value.bind(env, lvalue),
                         item=self.item.bind(env))


@dataclass(frozen=True)
class Call(Expr):
    func: str
    args: tuple[Expr, ...]

    def py(self):
        return f"{self.func}({', '.join(a.py() for a in self.args)})"

    def call(self, ret, op, defs, stack):
        func = defs[self.func]
        yield from func.call(self.args, ret, op, defs, stack)


#
# statements
#


@dataclass(frozen=True)
class Stmt(Compound, ABC):
    def inline(self, ret, op, defs, stack):
        raise NotImplementedError("abstract method")


@dataclass(frozen=True)
class Block(Stmt):
    body: tuple[Stmt, ...]

    def __post_init__(self):
        self.__dict__["body"] = tuple(self._flatten(tuple(self.body)))

    def _flatten(self, obj):
        if isinstance(obj, (Block, tuple, list)):
            for item in obj:
                yield from self._flatten(item)
        else:
            yield obj

    def __iter__(self):
        yield from self.body

    def __add__(self, other):
        return Block.make(self, body=(self.body + tuple(other)))

    def __bool__(self):
        return bool(self.body)

    def __getitem__(self, index):
        return self.body[index]


@dataclass(frozen=True)
class Pass(Stmt):
    def _py(self):
        yield 0, "pass"

    def inline(self, ret, op, defs, stack):
        yield self


@dataclass(frozen=True)
class Assign(Stmt):
    target: Lookup
    value: Expr
    op: Optional[str] = None

    def _py(self):
        yield 0, f"{self.target.py()} {self.op or ''}= {self.value.py()}"

    def bind(self, nmap):
        return self.make(self,
                         target=self.target.bind(nmap, True),
                         value=self.value.bind(nmap),
                         op=self.op)

    def inline(self, ret, op, defs, stack):
        if isinstance(self.value, Call):
            yield from self.value.call(self.target, self.op, defs, stack)
        else:
            yield self


@dataclass(frozen=True)
class If(Stmt):
    cond: Expr
    then: Block
    orelse: Block

    def _py(self):
        if not (self.then or self.orelse):
            return
        if self.then:
            yield 0, f"if {self.cond.py()}:"
            yield from ((i+1, *r) for s in self.then for i, *r in s._py())
            if self.orelse:
                yield 0, "else:"
                yield from ((i+1, *r) for s in self.orelse for i, *r in s._py())
        elif self.orelse:
            if isinstance(self.cond, Op):
                yield 0, f"if not ({self.cond.py()}):"
            else:
                yield 0, f"if not {self.cond.py()}:"
            yield from ((i+1, *r) for s in self.orelse for i, *r in s._py())

    def inline(self, ret, op, defs, stack):
        t = Block.make(self.then,
                       body=(s for stmt in self.then
                             for s in stmt.inline(ret, op, defs, stack)))
        e = Block.make(self.orelse,
                       body=(s for stmt in self.orelse
                             for s in stmt.inline(ret, op, defs, stack)))
        yield self(then=t, orelse=e)


@dataclass(frozen=True)
class Return(Stmt):
    value: Optional[Expr] = None

    def _py(self):
        if self.value is None:
            yield 0, "return"
        else:
            yield 0, f"return {self.value.py()}"

    def inline(self, ret, op, defs, stack):
        if ret is None and self.value is None:
            pass
        elif ret is not None and self.value is None:
            LangError.from_code(self, f"cannot assign bare return")
        elif ret is None and self.value is not None:
            LangError.from_code(self, f"cannot discard return value")
        else:
            yield Assign.make(self, target=ret, value=self.value, op=op)


@dataclass(frozen=True)
class BareCall(Stmt):
    call: Call

    def _py(self):
        yield 0, self.call.py()

    def inline(self, ret, op, defs, stack):
        yield from self.call.call(None, None, defs, stack)


#
# declarations
#


@dataclass(frozen=True)
class Decl(Compound, ABC):
    pass


@dataclass(frozen=True)
class Var(Decl):
    name: str
    type: type
    size: Optional[int | str]
    init: Optional[object]

    def _py(self):
        yield 0, f"{self.name}: {self.type.__name__} = {self.init}"


@dataclass(frozen=True)
class Class(Decl):
    name: str
    cls: object
    fields: tuple[Var, ...] = ()
    parents: tuple[str, ...] = ()

    def _py(self):
        yield 0, "@dataclass"
        if self.parents:
            yield 0, f"class {self.name}({', '.join(self.parents)}):"
        else:
            yield 0, f"class {self.name}:"
        yield from ((i+1, *r) for f in self.fields for i, *r in f._py())


@dataclass(frozen=True)
class Func(Decl):
    name: str
    args: tuple[str, ...]
    body: Block
    globals: tuple[Var, ...]
    locals: tuple[Var, ...]

    def _py(self):
        args = ", ".join(self.args)
        yield 0, f"def {self.name}({args}):"
        if self.globals:
            yield 1, "global", ", ".join(v.name for v in self.globals)
        yield from ((i+1, *r) for v in self.locals for i, *r in v._py())
        yield from ((i+1, *r) for s in self.body for i, *r in s._py())

    def _isret(self, block):
        if block:
            if isinstance(block[-1], Return):
                return True
            elif isinstance(block[-1], If):
                return self._isret(block[-1].then) \
                    and self._isret(block[-1].orelse)
        return False

    def _makeret(self, block):
        body = []
        for pos, stmt in enumerate(block):
            if isinstance(stmt, Return):
                body.append(stmt)
                break
            elif isinstance(stmt, If):
                stmt = stmt(then=self._makeret(stmt.then),
                            orelse=self._makeret(stmt.orelse))
                if stmt.then and isinstance(stmt.then[-1], Return):
                    if stmt.orelse and isinstance(stmt.orelse[-1], Return):
                        # if / ... return / else ... return
                        body.append(stmt)
                        break
                    else:
                        # if / ... return / else ...
                        stmt = stmt(orelse=stmt.orelse
                                    + self._makeret(block[pos+1:]))
                        if not self._isret(stmt.orelse):
                            LangError.from_code(stmt, "missing return in else")
                        body.append(stmt)
                        break
                else:
                    if stmt.orelse and isinstance(stmt.orelse[-1], Return):
                        # if / ... / else ... return
                        stmt = stmt(then=stmt.then
                                    + self._makeret(block[pos+1:]))
                        if not self._isret(stmt.then):
                            LangError.from_code(stmt, "missing return in then")
                        body.append(stmt)
                        break
                    else:
                        # if / ... / else ...
                        body.append(stmt)
            else:
                body.append(stmt)
        return Block.make(block, body=body)

    def call(self, args, ret, op, defs, stack=[]):
        if len(args) != len(self.args):
            LangError.from_code(self, (f"expected {len(self.args)} arguments,"
                                       f" got {len(args)}"))
        if self.name in stack:
            LangError.from_code(self, "unsupported recursive function")
        nmap = {p: a for p, a in zip(self.args, args)}
        scope = {n.name: Name.make(n, id=f"{self.name}_{n.name}")
                 for n in self.locals}
        for stmt in self._makeret(self.body):
            bound = stmt.subst(scope).bind(nmap)
            yield from bound.inline(ret, op, defs, stack + [self.name])


#
# module
#

@dataclass(frozen=True)
class Module(Compound):
    var: dict[str, Var]
    cls: dict[str, Class]
    fun: dict[str, Func]

    def __post_init__(self):
        d = self.__dict__["all"] = {}
        for _, decl in self.fields():
            d.update(decl)

    def _py(self):
        yield 0, "from dataclasses import dataclass"
        for decl, sep in [(self.cls, True),
                          (self.var, False),
                          (self.fun, True)]:
            yield 0, ""
            for n, d in enumerate(decl.values()):
                if n and sep:
                    yield 0, ""
                yield from d._py()
