"""PoC implementation of a generic libDDD action"""

from dataclasses import dataclass
from typing import Literal


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
        return self.__class__(*(v for p in zip(self.k[1:], self.v[1:]) for v in p))

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
            if h is None:
                return ddd()
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
class WeightedSum:
    vars: tuple[str, ...]
    coefs: tuple[int, ...]
    const: int = 0

    def push(self, var: str, val: int):
        assert self.vars and var == self.vars[0]
        return WeightedSum(
            self.vars[1:], self.coefs[1:], self.const + self.coefs[0] * val
        )

    def done(self):
        return not any(self.coefs)

    def __call__(self):
        assert not self.vars and self.done()
        return self.const


@dataclass
class Condition:
    sum: WeightedSum
    op: Literal["==", "!=", "<", "<=", ">", ">="]

    def push(self, var: str, val: int):
        return Condition(self.sum.push(var, val), self.op)

    def done(self):
        return self.sum.done()

    def __call__(self):
        if self.op == "==":
            return self.sum() == 0
        elif self.op == "!=":
            return self.sum() != 0
        elif self.op == "<":
            return self.sum() < 0
        elif self.op == "<=":
            return self.sum() <= 0
        elif self.op == ">":
            return self.sum() > 0
        elif self.op == ">=":
            return self.sum() >= 0
        else:
            raise ValueError(f"invalid operator {self.op!r}")


@dataclass
class Action(Hom):
    cond: tuple[Condition, ...]
    assign: dict[str, WeightedSum]

    def phi(self, e: str, x: int):
        cond: list[Condition] = []
        for old in self.cond:
            new = old.push(e, x)
            if new.done():
                if not new():
                    return [], None
            else:
                cond.append(new)
        return [], Action(
            tuple(cond),
            {k: v.push(e, x) for k, v in self.assign.items()},
        )

    def one(self):
        d = ddd()
        for v, a in reversed(self.assign.items()):
            d = ddd(v, a()) + d
        return d


if __name__ == "__main__":
    d = ddd(a=1, b=2, c=3)
    act = Action(
        (
            Condition(WeightedSum(d.k, (1, 2, 3), 0), ">"),
            Condition(WeightedSum(d.k, (0, 0, 1), 0), "!="),
        ),
        {
            "a": WeightedSum(d.k, (1, 0, 0), 0),
            "b": WeightedSum(d.k, (0, 1, 1), 1),
            "c": WeightedSum(d.k, (0, 0, 0), 0),
        },
    )
