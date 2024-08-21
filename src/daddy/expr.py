import re

from secrets import token_hex
from sympy import parse_expr, Symbol


class Parser:
    """a simple parser for assignments

    It parses expression as `x = 2` or `x += y`, with:
     - a variable at the left-hand side
     - a linear combination of variables on the right-hand side
    """
    ops = ("=", "==", "!=", "<=", ">=", "<", ">", "+=")

    def __init__(self, *names):
        """create a parser for a fixed set of names

        Names are arbitrary strings considered as atoms, eg:
         - regular variable names as `x`, `my_var`, etc.
         - more complex strings as `x.attr[3]`
         - or even arbitrary strings as `it's raining`
        """
        self.n2t = {}
        self.t2n = {}
        self.loc = {}
        for n in names:
            s = 2
            while True:
                h = token_hex(s)
                t = f"_{h}"
                if t not in self.t2n:
                    break
                s += 1
            self.loc[t] = Symbol(n)
            self.n2t[n] = t
            self.t2n[t] = n
        ne = "|".join(re.escape(n) for n in names)
        self.n = re.compile(ne)
        te = "|".join(re.escape(t) for t in self.t2n)
        op = "|".join(re.escape(x) for x in self.ops)
        self.a = re.compile(fr"^\s*({te})\s*({op})\s*(\w.*)$")

    def _get(self, m):
        s = m.group(0)
        return self.n2t.get(s, s)

    def __call__(self, src: str) -> tuple[str, str, int | str | tuple[int, dict[str, int]]]:
        """parse `str` as an assignment

        Takes a string as input and returns either:
         - `str, str, int` for assignments as `x = 3` in which case it returns
           `'x', '=', 3`
         - `str, str, str` for assignments as `x += y` in which case it returns
           `'x', '+=', 'y'`
         - `str, str, (int, dict)` for assignments as `x += y + 2*z` in which
           case it returns `'x', '=', (12, {'x': 1, 'y': 1, 'z': 2})`, where the
           `int` is the constant added and the `dict` has the coefficients for
           the linear combination of variables. Note that in this case, the
           second returned string is always `'='` as `+=` is interpreted by
           adding `1` to the coefficient of `x` in the returned `dict`.
        """
        s = self.n.sub(self._get, src)
        m = self.a.match(s)
        if m is None:
            raise ValueError(f"invalid expression '{src}' (wrong structure)")
        left, op, right = m.groups()
        left = self.t2n[left]
        if right.isnumeric():
            return left, op, int(right)
        elif right in self.t2n:
            return left, op, self.t2n[right]
        elif op == "=" or op == "+=":
            coef, inc = self._parse_expr(right)
            if op == "+=":
                coef[left] = 1 + coef.get(left, 0)
            return left, "=", (inc, coef)
        else:
            raise ValueError(f"invalid expression '{src}' (wrong assignment)")

    def _parse_expr(self, src):
        try:
            expr = parse_expr(src, self.loc, ())
        except Exception as err:
            raise ValueError(f"invalid expression {src} ({err})")
        if expr.is_Integer:
            return {}, int(expr)
        elif expr.is_Symbol:
            return {str(expr): 1}, 0
        elif expr.func.is_Mul:
            return self._parse_mul(expr), 0
        elif expr.func.is_Add:
            return self._parse_sum(expr)
        else:
            raise ValueError(f"invalid expression {expr} (wrong op)")

    def _parse_mul(self, expr):
        if len(expr.args) != 2:
            raise ValueError(f"invalid expression '{expr}' (too many factors)")
        one, two = expr.args
        if one.is_Integer and two.is_Symbol:
            return {str(two): int(one)}
        elif one.is_Symbol and two.is_Integer:
            return {str(one): int(two)}
        else:
            raise ValueError(f"invalid expression '{expr}' (wrong factors)")

    def _parse_sum(self, expr):
        pass
        coef = {}
        inc = 0
        for term in expr.args:
            if term.is_Integer:
                inc += int(term)
            elif term.is_Symbol:
                coef[str(term)] = 1
            elif term.is_Mul:
                coef.update(self._parse_mul(term))
            else:
                raise ValueError(f"invalid expression '{term}' (wrong term)")
        return coef, inc
