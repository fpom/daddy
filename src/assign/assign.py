"""PoC implementation of a generic libDDD assignment

`ass(tgt, src, aug, inc, mul)` implements either:
 - `tgt = mul*src + inc` if `aug` is false
 - `tgt += mul*src + inc` if `aug` is true

Where `tgt` and `src` are two DDD variables, and `inc` and `mul` are
two constants. This module is a proof of concept implementation that is
intended to be more readable and debuggable than the final C++ implementation.
"""
from dataclasses import dataclass


class ddd:
    "simple implementation of a linear DDD"
    def __init__(self, *raw, **content):
        if raw:
            assert not content
            self.k = tuple(raw[0::2])
            self.v = tuple(raw[1::2])
        else:
            self.k = tuple(content.keys())
            self.v = tuple(content.values())

    def __call__(self, **assign):
        return self.__class__(**{k: assign.get(k, v) for k, v in self})

    def __getitem__(self, key):
        for k, v in self:
            if k == key:
                return v

    def __eq__(self, other):
        return self.k == other.k and self.v == other.v

    def __iter__(self):
        yield from zip(self.k, self.v)

    def __repr__(self):
        items = [f"{k}={v}" for k, v in self]
        return f"[{', '.join(items)}]"

    def __bool__(self):
        return bool(self.k)

    def head(self):
        return self.k[0], self.v[0]

    def tail(self):
        return self.__class__(*(v for p in zip(self.k[1:], self.v[1:])
                                for v in p))

    def __add__(self, other):
        r = self.__class__()
        r.k = self.k + other.k
        r.v = self.v + other.v
        return r


class Hom:
    """simple implementation of a homomorphism base class and identity

    set `Hom.log = True` to trace every call and computation steps
    (doing this will make doctests fail because of extra output)
    """
    log = True

    def phi(self, e, x):
        """method to be implemented, as in libDDD

        should return a list of [var, val, ...] and an homomorphism
        this defaut method implements the identity

        >>> d = ddd(a=1, b=2, c=3, d=4)
        >>> Hom()(d) == d
        True
        """
        return [e, x], self

    def one(self):
        return ddd()

    def __repr__(self):
        return "</>"

    def __call__(self, d, ctx="{}"):
        "implementation of applying an homomorphism onto a ddd"
        if not d:
            return self.one()
        elif self.__class__ is Hom:
            # shortcut to simply traces when `Hom.log == True`
            return d
        else:
            e, x = d.head()
            s, h = self.phi(e, x)
            n, t = ddd(*s), d.tail()
            if n:
                ctx = ctx.format(f"{n} + {{}}").replace("] + [", ", ")
            if self.log:
                print(ctx.format(f"{h}({t})"))
            return n + h(t, ctx=ctx)

    def __mul__(self, other):
        "composition of two homomorphisms"
        one, two = self, other

        class MH(Hom):
            def __repr__(self):
                return f"({one!r} * {two!r})"

            def __call__(self, d, ctx="{}"):
                n = two(d, ctx.format(f"{one}({{}})"))
                return one(n, ctx)

        return MH()


@dataclass
class Up(Hom):
    "insert an edge `var=val` after the top-most edge"
    var: str
    val: int

    def __repr__(self):
        return f"<|{self.var}={self.val}>"

    def phi(self, e, x):
        """
        >>> d = ddd(a=1, b=2, c=3, d=4)
        >>> Up("x", 0)(d)
        [a=1, x=0, b=2, c=3, d=4]
        """
        return [e, x, self.var, self.val], Hom()


@dataclass
class Down(Hom):
    """perform assignment when src is after tgt

    assume tgt was the head of the DDD and has been removed already
    """
    tgt: str
    coef: dict[str, int]
    inc: int = 0

    def __repr__(self):
        return f"<{self.tgt}={self.coef}+{self.inc}|>"

    def phi(self, e, x):
        # new const to add = old + this var multiplied
        ni = x*self.coef[e] + self.inc
        # recurse in tail with new coefs, then put head back
        return [], Up(e, x) * Down(self.tgt, self.coef, ni)

    def one(self):
        # when reaching end, put result for target, it will be put back
        # at its position using all the Up's
        return ddd(self.tgt, self.inc)


@dataclass
class Assign(Hom):
    "main assignment class"
    tgt: str
    coef: dict[str, int]
    inc: int = 0

    def __repr__(self):
        return f"<{self.tgt}={self.coef}+{self.inc}>"

    def phi(self, e, x):
        # new const to add = old + this var multiplied
        ni = x*self.coef[e] + self.inc
        if e == self.tgt:
            # need Down to perform assignment after computation
            return [], Down(self.tgt, self.coef, ni)
        else:
            # just recurse in tail
            return [e, x], Assign(self.tgt, self.coef, ni)
