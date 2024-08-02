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
    log = False

    def phi(self, e, x):
        """method to be implemented, as in libDDD

        should return a list of [var, val, ...] and an homomorphism
        this defaut method implements the identity

        >>> d = ddd(a=1, b=2, c=3, d=4)
        >>> Hom()(d) == d
        True
        """
        return [e, x], self

    def __repr__(self):
        return "</>"

    def __call__(self, d, ctx="{}"):
        "implementation of applying an homomorphism onto a ddd"
        if not d:
            return ddd()
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
class Const(Hom):
    """homomorphism to implement `var = val` or `var += val`

     - `var` is the DDD variable to be assigned
     - `val` is the value to assign to the variable
     - `aug` is to choose between `=` and `+=`
    """
    var: str
    val: int
    aug: bool = False

    def __repr__(self):
        a = "+" if self.aug else ""
        return f"<{self.var}{a}={self.val}>"

    def phi(self, e, x):
        """
        >>> d = ddd(a=1, b=2, c=3, d=4)
        >>> Const("b", 0)(d)  # b = 0
        [a=1, b=0, c=3, d=4]
        >>> Const("b", 10, True)(d)  # b += 10
        [a=1, b=12, c=3, d=4]
        """
        if e != self.var:
            # copy edge and recurse to `var`
            return [e, x], self
        elif self.aug:
            # perform augmented assignment of `var`
            return [e, x+self.val], Hom()
        else:
            # perform simple assignment of `var`
            return [e, self.val], Hom()


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
    src: str
    inc: int = 0
    mul: int = 1

    def __repr__(self):
        return f"<{self.tgt}={self.mul}*{self.src}+{self.inc}|>"

    def phi(self, e, x):
        """
        >>> d = ddd(b=2, c=3, d=4)  # a has been removed
        >>> Down("a", "d")(d)       # and it is assigned back
        [a=4, b=2, c=3, d=4]
        """
        if e == self.src:
            # perform assignment
            return [self.tgt, self.mul*x + self.inc, e, x], Hom()
        else:
            # recurse in tail, then put head back using Up
            return [], Up(e, x) * self


@dataclass
class Assign(Hom):
    "main assignment class"
    tgt: str
    src: str
    aug: bool = False
    inc: int = 0
    mul: int = 1

    def __repr__(self):
        a = "+" if self.aug else ""
        return f"<{self.tgt}{a}={self.mul}*{self.src}+{self.inc}>"

    def phi(self, e, x):
        """
        >>> d = ddd(a=1, b=2, c=3, d=4)
        >>> Assign("a", "d")(d)
        [a=4, b=2, c=3, d=4]
        >>> Assign("d", "a")(d)
        [a=1, b=2, c=3, d=1]
        """
        if e == self.src == self.tgt:
            # assigning variable to itself must be done in-place
            if self.aug:
                return [e, x + self.mul*x + self.inc], Hom()
            else:
                return [e, self.mul*x + self.inc], Hom()
        elif e == self.src:
            # src is before tgt => assign a const
            return [e, x], Const(self.tgt, self.mul*x + self.inc, self.aug)
        elif e != self.tgt:
            # tgt nor src reached => recurse in tail
            return [e, x], self
        elif self.aug:  # and e == self.tgt
            # tgt reached (before src) => use down
            # since aug is true, add the current value of edge to inc
            return [], Down(self.tgt, self.src, x + self.inc, self.mul)
        else:  # not self.aug and e == self.tgt
            # tgt reached (before src) => use down
            # since aug is false, the current value of edge is discarded
            return [], Down(self.tgt, self.src, self.inc, self.mul)

    def apply(self, d):
        "simulate the expected result by direct change in the faked ddd class"
        if self.aug:
            return d(**{self.tgt:
                        d[self.tgt] + self.mul*d[self.src] + self.inc})
        else:
            return d(**{self.tgt:
                        self.mul*d[self.src] + self.inc})


def ass(tgt, src, aug, inc, mul):
    "chose appropriate homomorphism to optimize calls wrt on mul and inc"
    if inc == 0 and mul == 0 and aug:
        # tgt += 0  => identity
        return Hom()
    elif mul == 0:
        # tgt (+)= inc  => constant assignment
        return Const(tgt, inc, aug)
    else:
        # general case
        return Assign(tgt, src, aug, inc, mul)


if __name__ == "__main__":
    # doctests
    import doctest
    doctest.testmod()
    # systematic test of many cases
    d = ddd(a=1, b=2, c=3, d=4)
    for mul in [1, 0, 3]:
        for aug in [False, True]:
            for inc in [0, 10]:
                for x, y in ["da", "ad", "bb"]:
                    a = Assign(x, y, aug, inc, mul)
                    e = ass(a.tgt, a.src, a.aug, a.inc, a.mul)
                    if Hom.log:
                        print(f"{a}({d})")
                    r = a(d)
                    if Hom.log:
                        print("=>", r)
                        if a != e:
                            print(f"~ {e}")
                        print()
                    x = a.apply(d)
                    assert r == x, f"{r} != {x}"
