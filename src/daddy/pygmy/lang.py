import ast
import io

from dataclasses import dataclass
from abc import ABC
from collections.abc import Iterator
from typing import Self, Iterable, Optional, Union, NoReturn, \
    get_args, get_origin
from inspect import isclass

from . import LangError


#
# base class
#


@dataclass(frozen=True)
class Code(ABC):
    def error(self, msg) -> NoReturn:
        f, a, s = self.__file__, self.__ast__, self.__src__  # pyright: ignore
        raise LangError(msg, f, a.lineno, a.col_offset, s[a.lineno - 1])

    def py(self):
        raise NotImplementedError

    @classmethod
    def make(cls, *srcref, **fields) -> Self:
        for name, base in cls.cls_fields():
            if (val := fields.get(name, None)) is not None:
                if isinstance(val, Code):
                    assert isinstance(val, base)
                elif isinstance(val, Iterable):
                    assert all(isinstance(v, base) for v in val)
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
        else:
            raise TypeError(f"unexpected argument: {srcref=}")
        return obj

    @classmethod
    def cls_fields(cls, only=None, ignore=()) -> Iterator[tuple[str, type]]:
        if only is None:
            only = object
        if not isinstance(only, (tuple, list, set)):
            only = (only,)
        if not isinstance(ignore, (tuple, list, set)):
            ignore = (ignore,)
        for name, field in cls.__dataclass_fields__.items():
            ftype = field.type
            if isclass(ftype):
                base = ftype
            elif get_origin(ftype) is tuple:
                base = get_args(ftype)[0]
            elif get_origin(ftype) is Union:
                base = get_args(ftype)[0]
            else:
                raise ValueError(f"unknown field type '{cls.__name__}.{name}:"
                                 f" {ftype}'")
            if (issubclass(base, ignore)             # pyright: ignore
                    or not issubclass(base, only)):  # pyright: ignore
                continue
            yield name, base


#
# expressions
#


@dataclass(frozen=True)
class Expr(Code, ABC):
    pass


@dataclass(frozen=True)
class Const(Expr):
    val: object

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
    pass


@dataclass(frozen=True)
class Name(Lookup):
    id: str

    def py(self):
        return self.id


@dataclass(frozen=True)
class Attr(Lookup):
    value: Lookup
    attr: str

    def py(self):
        if isinstance(self.value, Op):
            return f"({self.value.py()}).{self.attr}"
        else:
            return f"{self.value.py()}.{self.attr}"


@dataclass(frozen=True)
class Item(Lookup):
    value: Lookup
    item: Expr

    def py(self):
        if isinstance(self.value, Op):
            return f"({self.value.py()})[{self.item.py()}]"
        else:
            return f"{self.value.py()}[{self.item.py()}]"


@dataclass(frozen=True)
class Loop(Expr):
    name: Name
    iter: Expr

    def py(self):
        return f"for {self.name.id} in {self.iter.py()}"


@dataclass(frozen=True)
class Comprehension(Expr):
    expr: Expr
    loop: Loop
    cond: Expr

    def py(self):
        return f"({self.expr.py()} {self.loop.py()} if {self.cond.py()})"


@dataclass(frozen=True)
class Call(Expr):
    func: Lookup
    args: tuple[Expr, ...]

    def py(self):
        return f"{self.func.py()}({', '.join(a.py() for a in self.args)})"


#
# statements
#


@dataclass(frozen=True)
class Stmt(Code, ABC):
    def py(self, prefix=""):
        out = io.StringIO()
        for indent, line in self._py():
            out.write(prefix)
            out.write("    " * indent)
            out.write(line)
            out.write("\n")
        return out.getvalue()

    def _py(self):
        raise NotImplementedError


@dataclass(frozen=True)
class Pass(Stmt):
    def bind(self, env) -> Iterator[Stmt]:
        yield self

    def _py(self):
        yield 0, "pass"


@dataclass(frozen=True)
class Assign(Stmt):
    target: Lookup
    value: Expr
    op: Optional[str] = None

    def _py(self):
        yield 0, f"{self.target.py()} {self.op or ''}= {self.value.py()}"


@dataclass(frozen=True)
class If(Stmt):
    cond: Expr
    then: tuple[Stmt, ...]
    orelse: tuple[Stmt, ...]

    def _py(self):
        if not (self.then or self.orelse):
            return
        if self.then:
            yield 0, f"if {self.cond.py()}:"
            yield from ((i+1, r) for s in self.then for i, r in s._py())
            if self.orelse:
                yield 0, "else:"
                yield from ((i+1, r) for s in self.orelse for i, r in s._py())
        elif self.orelse:
            if isinstance(self.cond, Op):
                yield 0, f"if not ({self.cond.py()}):"
            else:
                yield 0, f"if not {self.cond.py()}:"
            yield from ((i+1, r) for s in self.orelse for i, r in s._py())


@dataclass(frozen=True)
class For(Stmt):
    loop: Loop
    body: tuple[Stmt, ...]

    def _py(self):
        yield 0, f"{self.loop.py()}:"
        yield from ((i+1, r) for s in self.body for i, r in s._py())


@dataclass(frozen=True)
class Return(Stmt):
    value: Optional[Expr] = None

    def _py(self):
        if self.value is None:
            yield 0, "return"
        else:
            yield 0, f"return {self.value.py()}"


@dataclass(frozen=True)
class BareCall(Stmt):
    call: Call

    def _py(self):
        yield 0, self.call.py()


#
# declarations
#


@dataclass(frozen=True)
class Decl(Code, ABC):
    pass


@dataclass(frozen=True)
class Func(Decl):
    name: str
    args: tuple[str, ...]
    body: tuple[Stmt, ...]

    def _py(self):
        args = ", ".join(self.args)
        yield 0, f"def {self.name}({args}):"
        yield from ((i+1, r) for s in self.body for i, r in s._py())


@dataclass(frozen=True)
class Var(Decl):
    name: str
    type: str
    size: Optional[int | str]
    init: Optional[object]

    def _py(self):
        yield 0, f"{self.name}: {self.type} = {self.init}"


@dataclass(frozen=True)
class Param(Decl):
    name: str
    value: int | str

    def _py(self):
        yield 0, f"{self.name} = {self.value}"


@dataclass(frozen=True)
class Struct(Decl):
    name: str
    fields: tuple[Var, ...]
    parents: tuple[str, ...]

    def _py(self):
        yield 0, f"class {self.name}:"
        yield from ((i+1, r) for f in self.fields for i, r in f._py())