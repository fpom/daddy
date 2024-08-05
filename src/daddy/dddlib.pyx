import ast
import re
import sympy

from pathlib import Path
from collections import defaultdict
from subprocess import check_call

from libcpp cimport bool
from libcpp.pair cimport pair

cdef extern from "dddwrap.h" namespace "std":
    cdef cppclass ofstream:
        ofstream ()
        ofstream (const string &filename)
        void close ()
        ofstream& write (const char* s, int n)
    cdef cppclass ifstream:
        ifstream ()
        ifstream (const string &filename)
        void close ()
        bool eof ()
    void getline (ifstream& i, string& s)

##
## syntax
##

_hom_expr = re.compile(r"^\s*(\w+)\s*(=|==|!=|<=|>=|<|>|\+=)\s*(\w.*?)\s*$", re.I)

def _parse_mul(expr):
    if len(expr.args) != 2:
        raise ValueError(f"invalid expression '{expr}' (too many factors)")
    one, two = expr.args
    if one.is_Integer and two.is_Symbol:
        return {str(two): int(one)}
    elif one.is_Symbol and two.is_Integer:
        return {str(one): int(two)}
    else:
        raise ValueError(f"invalid expression '{expr}' (wrong factors)")

def _parse_sum(expr):
    pass
    coef = {}
    inc = 0
    for term in expr.args:
        if term.is_Integer:
            inc += int(term)
        elif term.is_Symbol:
            coef[str(term)] = 1
        elif term.is_Mul:
            coef.update(_parse_mul(term))
        else:
            raise ValueError(f"invalid expression '{term}' (wrong term)")
    return coef, inc

def _parse_expr(src):
    try:
        expr = sympy.parse_expr(src)
    except Exception as err:
        raise ValueError(f"invalid expression {src} ({err})")
    if expr.is_Integer:
        return {}, int(expr)
    elif expr.is_Symbol:
        return {str(expr): 1}, 0
    elif expr.func.is_Mul:
        return _parse_mul(expr), 0
    elif expr.func.is_Add:
        return _parse_sum(expr)
    else:
        raise ValueError(f"invalid expression {expr}")
        

##
## domain (aka, factory)
##

cdef extern from "dddwrap.h":
    cdef DDD ddd_new_ONE()
    cdef DDD ddd_new_EMPTY()
    cdef DDD ddd_new_range(int var, val_t val1, val_t val2, const DDD&d)
    cdef void saveDDD (ofstream &s, vector[DDD] l)
    cdef void loadDDD (ifstream &s, vector[DDD] &l)
    cdef DDD ddd_concat (DDD &a, DDD &b)
    cdef DDD ddd_union (DDD &a, DDD &b)
    cdef DDD ddd_intersect (DDD &a, DDD &b)
    cdef DDD ddd_minus (DDD &a, DDD &b)
    ctypedef pair[val_t,DDD] *ddd_iterator
    cdef ddd_iterator ddd_iterator_begin (DDD d)
    cdef void ddd_iterator_next (ddd_iterator i)
    cdef bint ddd_iterator_end (ddd_iterator i, DDD d)
    cdef DDD ddd_iterator_ddd (ddd_iterator i)
    cdef val_t ddd_iterator_value (ddd_iterator i)
    cdef bint ddd_is_STOP(DDD &d)

cdef extern from "ddd/Hom_Basic.hh":
    cdef Hom setVarConst(int var, int val)
    cdef Hom varEqState(int var, int val)
    cdef Hom varNeqState(int var, int val)
    cdef Hom varGtState(int var, int val)
    cdef Hom varLtState(int var, int val)
    cdef Hom varLeqState(int var, int val)
    cdef Hom varGeqState(int var, int val)
    cdef Hom incVar(int var, int val)
    cdef Hom varEqVar(int var, int var2)
    cdef Hom varNeqVar(int var, int var2)
    cdef Hom varGtVar(int var, int var2)
    cdef Hom varLtVar(int var, int var2)
    cdef Hom varLeqVar(int var, int var2)
    cdef Hom varGeqVar(int var, int var2)

cdef extern from "assign/assign.hh":
    Hom linearAssignHom(int, vector[int], int)

cdef class domain:
    """`ddd` and `hom` factory

    Only the `ddd` and `hom` instances from the same `domain` are compatible
    with each other. This allows to create them for distinct models without
    interference between their variables names and domains.

    Attributes:
     - `tuple vars`: the variables names for this factory, in the
       order they are arranged in the `ddd`s
     - `int depth`: the number of variables, that is the depth of the `ddd`s
     - `dict doms`: map variables names and numbers to sets of values allow
       for the variable
     - `ddd full`: the set of all possible valuations wrt the variables domain
     - `ddd empty`: the empty set of valuations
     - `ddd one`: the accepting all node
     - `hom id`: the identity homomorphism
    """
    def __cinit__(self, **doms):
        self.vmap = {}
        self.vars = tuple(doms)
        self.depth = len(self.vars)
        self.sdoms = {}
        self.ddoms = {}
        self.full = ddd.__new__(ddd)
        self.one = ddd.__new__(ddd)
        self.empty = ddd.__new__(ddd)
        self.id = hom.__new__(hom)
        self.full.f = self.one.f = self.empty.f = self.id.f = self
        self.id.h = Hom()

    def __init__(self, **doms):
        """initialise a `domain` by defining the variables and their domains

        >>> dom = domain(x=(0, 1), y=2, z=(0, 1, 2))
        >>> dom.vars
        ('x', 'y', 'z')
        >>> dom.depth
        3
        >>> dom.doms
        {'x': {0, 1}, 'y': {0, 1}, 'z': {0, 1, 2}}
        >>> len(dom.full)
        12

        Arguments:
         - `name=values, ...`: for each `str name` defines the values this
           variable is allowed to hold as a collection, the order these names are
           given is the order of the variables in the `ddd`s from to to bottom.
           If `values` is an `int`, it is replaced by `range(values)`
        """
        cdef str name
        cdef int rank
        cdef ddd tmp = ddd.__new__(ddd)
        cdef object dom
        cdef set sdom
        for rank, (name, dom) in enumerate(doms.items()):
            self.vmap[rank] = name
            self.vmap[name] = rank
            if isinstance(dom, int):
                dom = range(dom)
            sdom = self.sdoms[name] = self.sdoms[rank] = set(dom)
            tmp.d = self._from_set(rank, sdom, ddd_new_ONE())
            self.ddoms[name] = self.ddoms[rank] = self.makeddd(tmp.d)
        tmp = self()
        self.full.d = tmp.d
        self.one.d = ddd_new_ONE()
        self.empty.d = ddd_new_EMPTY()

    def __len__(self):
        """number of variables in the domain

        >>> len(domain(x=3, y=4))
        2
        """
        return len(self.vars)

    def __eq__(self, domain other):
        """domains equality

        Two domains are equal if they have the same variables, in the same
        order, and with the same domains.

        >>> domain(x=2, y=2) == domain(x=(0, 1), y=(0, 1))
        True
        >>> domain(x=2, y=2) == domain(y=2, x=2)
        False
        """
        # don't call ddd.__eq__ as it calls domain.checkd that calls domain.__eq__
        return self.full.d.set_equal(other.full.d) and self.vars == other.vars

    def __ne__(self, domain other):
        "domain inequality"
        return not self.__eq__(other)

    @property
    def doms(self):
        """variable domains
        
        >>> domain(x=2, y=2).doms
        {'x': {0, 1}, 'y': {0, 1}}
        """
        return {v: self.sdoms[v] for v in self.vars}

    cdef DDD _from_set(self, int var, set dom, DDD tail):
        """build a `DDD` from a set

        The `DDD` valuates `var` in set `dom` and is followed by `tail`.
        For instance, `_from_set(2, {1, 4}, d)` is `2 ---1|4--> d`
        """
        cdef DDD d
        cdef val_t m, M, v
        cdef int i
        m, M = min(dom), max(dom)
        if M - m + 1 == len(dom):
            return DDD(var, m, M, tail)
        else:
            for i, v in enumerate(dom):
                if i == 0:
                    d = DDD(var, v, tail)
                else:
                    d = ddd_union(d, DDD(var, v, tail))
            return d

    cdef inline void checkd(self, ddd d):
        "helper method to check that a `ddd` is from this domain"
        if d.f != self:
            raise ValueError("not same domains")

    cdef inline void checkh(self, hom h):
        "helper method to check that a `hom` is from this domain"
        if h.f != self:
            raise ValueError("not same domains")

    cdef inline ddd makeddd(self, DDD d):
        "auxiliary method to make a `ddd` from a `DDD`"
        cdef ddd obj = ddd.__new__(ddd)
        obj.f = self
        obj.d = d
        return obj

    cdef inline hom makehom(self, Hom h):
        "auxiliary method to make a `hom` from a `Hom`"
        cdef hom obj = hom.__new__(hom)
        obj.f = self
        obj.h = h
        return obj

    def __call__(self, *largs, **values):
        """create a `ddd` or a `hom` instance

        If called with a positional argument, it builds a `hom`, otherwise
        it expects a valuation given as the keywords arguments to build a `ddd`.

        Possible calls are:

         1. No arguments: return a `ddd` with all possible valuations
         2. `"id"`: return the identity `hom`
         3. `var=values, ...`: return a `ddd` with the variables ranging over the
            provided values (iterables)
         4. `":=", var=values, ...`: return a constant `hom` that always returns
            the `ddd` specified as previously
         5. `"x OP y"`: return a `hom` that computes the given operation, where
            `x` is a variable and `y` is a variable or a value and `OP` is the
            operation to implement:
           a. If `OP` is one of `==`, `!=`, `<=`, `>=`, `<`, `>`, the resulting
              `hom` selects the subset of valuations where `x OP y`. The returned
              `hom` is a selector.
           b. If `OP` is `=`, the resulting `hom` assigns `y` to `x`
           c. If `OP` is `+=`, the resulting `hom` increments `x` by `y`

        In cases 5.b and 5.c, `y` may also be an expression equivalent of `m*z+i`
        where, `z` is a variable and `m`, `i` are constants. The exact syntax is
        very general as the expression is parsed and simplified by `sympy`.

        As noted above, only the identity `hom` and those constructed with
        comparison operators (case 5.a) are selectors and are suitable to
        serve as conditions.

        >>> dom = domain(x=2, y=2)
        >>> dom("id").is_selector()
        True
        >>> dom(":=", x=0, y=0).is_selector()
        False
        >>> dom("x < y").is_selector()
        True
        >>> dom("x += 1").is_selector()
        False

        Note also that in cases 5.b and 5.c, when `y` is a variable, we use an 
        inefficient construct that may even fail if the domain of `y` is large.

        When creating `ddd`, the variables that are not valuated are considered
        to range over all their full domains. The returned `ddd` is the
        Cartesian product of all the variables valuations. For instance:

        >>> dom = domain(x=(0, 1), y=range(5), z=(0, 1))
        >>> d = dom(x=0, y=(1,2))
        >>> d == dom(x=0, y=1, z={0, 1}) | dom(x=0, y=2, z={0, 1})
        True
        >>> h = dom("x += 1")
        >>> h(d) == dom(x=1, y=1, z={0, 1}) | dom(x=1, y=2, z={0, 1})
        True

        Selector homomorphisms always return a subset of their arguments as
        they only filter the paths in it.

        >>> dom = domain(x=2, y=2)
        >>> h = dom("x == 0")
        >>> h(dom.full) == dom(x=0, y={0, 1}) 
        True
        >>> h = dom("x != 1")
        >>> h(dom.full) == dom(x=0, y={0, 1})
        True
        >>> h = dom("x < 1")
        >>> h(dom.full) == dom(x=0, y={0, 1})  #3
        True
        >>> h = dom("x <= 0")
        >>> h(dom.full) == dom(x=0, y={0, 1})
        True
        >>> h = dom("x > 0")
        >>> h(dom.full) == dom(x=1, y={0, 1})
        True
        >>> h = dom("x >= 1")
        >>> h(dom.full) == dom(x=1, y={0, 1})
        True
        >>> h = dom("x == y")
        >>> h(dom.full) == dom(x=0, y=0) | dom(x=1, y=1)
        True
        >>> h = dom("x != y")
        >>> h(dom.full) == dom(x=0, y=1) | dom(x=1, y=0)
        True
        >>> h = dom("x < y")
        >>> h(dom.full) == dom(x=0, y=1)
        True
        >>> h = dom("x <= y")
        >>> h(dom.full) == dom(x=0, y={0, 1}) | dom(x=1, y=1)
        True
        >>> h = dom("x > y")
        >>> h(dom.full) == dom(x=1, y=0)
        True
        >>> h = dom("x >= y")
        >>> h(dom.full) == dom(x=1, y={0, 1}) | dom(x=0, y=0)
        True

        Other homomorphisms assign variables and thus may return valuations
        that do not exist in their argument. They may even return valuations
        that are not in the domain (see `hom.clip()` to solve this).

        >>> dom = domain(x=2, y=2)
        >>> h = dom("x = 1")
        >>> h(dom(x=0, y={0, 1})) == dom(x=1, y={0, 1})
        True
        >>> h = dom("x += 1")
        >>> d = h(dom.full)
        >>> values = list(d.values())
        >>> len(values)
        4
        >>> for i in [1, 2]:
        ...     for j in [0, 1]:
        ...         assert dict(x=i, y=j) in values
        >>> h = dom("x = y")
        >>> h(dom.full) == dom(x=0, y=0) | dom(x=1, y=1)
        True
        >>> h = dom("y = x")
        >>> h(dom.full) == dom(x=0, y=0) | dom(x=1, y=1)
        True
        >>> h = dom("x += y")
        >>> d = h(dom.full)
        >>> values = list(d.values())
        >>> len(values)
        4
        >>> assert {'x': 0, 'y': 0} in values
        >>> assert {'x': 1, 'y': 0} in values
        >>> assert {'x': 1, 'y': 1} in values
        >>> assert {'x': 2, 'y': 1} in values
        >>> h = dom(":=", x=0, y=0)
        >>> h(dom.full) == dom(x=0, y=0)
        True

        More complex assignments are possible but involve parsing on the
        right-hand side of the assignment that must be an integer linear
        combination of variables.

        >>> dom = domain(x=10, y=10, z=10)
        >>> d = dom(x=1, y=1, z=1)
        >>> h = dom("x = y + 2*z + 3")
        >>> h(d) == dom(x=6, y=1, z=1)
        True
        >>> h = dom("y += x + 2*z + 3")
        >>> h(d) == dom(x=1, y=7, z=1)
        True
        """
        if (a := len(largs)) == 0:
            expr = None
        elif a == 1:
            expr = largs[0]
        else:
            raise TypeError("expected at most one positional argument")
        if expr is None:
            return self._call_ddd(values)
        elif expr == ":=":
            return self.const(self._call_ddd(values))
        elif expr == "id" and not values:
            return self.id
        elif expr and not values:
            return self._call_hom(expr)
        else:
            raise TypeError("invalid arguments")

    cdef ddd _call_ddd(self, dict values):
        "auxiliary method for `__call__`"
        cdef str n
        cdef int r, i
        cdef val_t v
        cdef set  vals, dom
        cdef DDD d = ddd_new_ONE()
        cdef ddd t
        for r in reversed(range(self.depth)):
            n = self.vmap[r]
            dom = self.sdoms[n]
            if n in values:
                if isinstance(values[n], int):
                    vals = {values[n]}
                else:
                    vals = set(values[n])
                vals.intersection_update(dom)
                if not vals:
                    raise ValueError(f"no values within domain for '{n}'")
                elif vals == dom:
                    t = self.ddoms[r]
                    d = ddd_concat(t.d, d)
                else:
                    d = self._from_set(r, vals, d)
            else:
                t = self.ddoms[n]
                d = ddd_concat(t.d, d)
        return self.makeddd(d)

    cdef hom _call_hom(self, str expr):
        "auxiliary method for `__call__`"
        cdef str left, op, right, var
        cdef int inc
        cdef dict coef
        cdef object match = _hom_expr.match(expr)
        if match is None:
            raise ValueError(f"invalid 'hom' expression '{expr}'")
        left, op, right = match.groups()
        if right.isnumeric():
            return self.op(left, op, int(right))
        elif right in self.vmap:
            return self.op(left, op, right)
        elif op == "=" or op == "+=":
            coef, inc = _parse_expr(right)
            if op == "+=":
                coef[left] = 1 + coef.get(left, 0)
            return self.assign(left, inc, **coef)
        else:
            raise ValueError(f"unsupported 'hom' expression '{expr}'")

    cpdef hom const(self, ddd d):
        """return a contant `hom` that returns `d`

        Same as `domain.__call__(":=", ...)` but more general as `d` can be
        a `ddd` that could not be specified as `...`
        """
        return self.makehom(Hom(d.d))

    cpdef hom op(self, str left, str op, object right):
        """return a `hom` that implements an operation

        Same as `domain.__call__("left op right")` but does not need parsing
        """
        cdef int val, lft, rgt, i
        cdef list coef
        cdef Hom r
        try:
            lft = self.vmap[left]
        except KeyError:
            raise ValueError(f"unknown variable {left}")
        if isinstance(right, int):
            val = right
            if op == "==":
                r = varEqState(lft, val)
            elif op == "!=":
                r = varNeqState(lft, val)
            elif op == ">":
                r = varGtState(lft, val)
            elif op == "<":
                r = varLtState(lft, val)
            elif op == "<=":
                r = varLeqState(lft, val)
            elif op == ">=":
                r = varGeqState(lft, val)
            elif op == "=":
                r = setVarConst(lft, val)
            elif op == "+=":
                r = incVar(lft, val)
            else:
                raise ValueError(f"unsupported operator '{op}'")
        elif isinstance(right, str):
            try:
                rgt = self.vmap[right]
            except KeyError:
                raise ValueError(f"unknown variable {left}")
            if op == "==":
                r = varEqVar(lft, rgt)
            elif op == "!=":
                r = varNeqVar(lft, rgt)
            elif op == ">":
                r = varGtVar(lft, rgt)
            elif op == "<":
                r = varLtVar(lft, rgt)
            elif op == "<=":
                r = varLeqVar(lft, rgt)
            elif op == ">=":
                r = varGeqVar(lft, rgt)
            elif op == "=":
                coef = [1 if i == rgt else 0
                        for i in range(len(self.vars))]
                r = linearAssignHom(lft, coef, 0)
            elif op == "+=":
                coef = [1 if i == rgt or i == lft
                        else 0 for i in range(len(self.vars))]
                r = linearAssignHom(lft, coef, 0)
            else:
                raise ValueError(f"unsupported operator '{op}'")
        else:
            raise TypeError(f"expected 'str' or 'int' but got"
                            f" {right.__class__.__name__}")
        return self.makehom(r)

    def assign(self, str tgt, int inc, **coef):
        cdef str v
        cdef int t
        cdef list c = [coef.get(v, 0) for v in self.vars]
        try:
            t = self.vmap[tgt]
        except KeyError:
            raise ValueError(f"unknown variable {tgt}")
        return self.makehom(linearAssignHom(t, c, inc))

    def save(self, str path, *ddds, **headers):
        """save a series of `ddd`s to a file

        Additional headers can be saved, given as `**headers`. Every header
        is serialized to text using `repr` and will be read back using
        `ast.literal_eval`. Headers `Count` and `Domains` are reserved.

        Arguments:
         - `str path`: where to save to
         - `ddd, ...`: a series of `ddd`s to be saved, at least one is expected
         - `key=value, ...`: an optional series of headers to save together
           with the `ddd`s
        """
        cdef ofstream f = ofstream(path.encode())
        cdef vector[DDD] vec
        cdef ddd d
        cdef int i
        cdef bytes line
        cdef str v, key
        cdef object val
        if not ddds:
            raise ValueError("no ddds provided")
        # save headers
        if "Count" in headers:
            raise ValueError("reserved header 'Count'")
        elif "Domains" in headers:
            raise ValueError("reserved header 'Domains'")
        headers["Count"] = len(ddds)
        headers["Domains"] = {v: self.sdoms[v] for v in self.vars}
        for key, val in sorted(headers.items()):
            line = (f"{key}: {val!r}\n").encode()
            f.write(line, len(line))
        f.write(b"\n", 1)
        # save DDDs
        vec.resize(len(ddds))
        for i, d in enumerate(ddds):
            if not d.f is self:
                raise ValueError("cannot save ddds from another domain")
            vec[i] = d.d
        saveDDD(f, vec)
        f.close()

    def load(self, str path):
        """load a previously saved series of `ddd`s

        Arguments:
         - `str path`: where to load the `ddd`s from

        Return: a pair `headers, [ddd, ...]` with the loaded headers and `ddd`s
        """
        cdef ifstream f = ifstream(path.encode())
        cdef dict headers = {}
        cdef vector[DDD] vec
        cdef int r
        cdef int count = -1
        cdef dict varmap
        cdef str v
        cdef bytes line, h, s
        cdef string rawline
        cdef object obj
        cdef DDD d
        cdef dict doms = {}
        # read headers
        while True:
            getline(f, rawline)
            line = rawline.strip()
            if not line:
                break
            try:
                h, line = (s.strip() for s in line.split(b":", 1))
                obj = ast.literal_eval(line.strip().decode())
            except:
                raise ValueError("invalid header line: %r" % line.decode())
            if h == b"Count":
                count = obj
            elif h == b"Domains":
                doms = obj
            else:
                headers[h.decode()] = obj
        if count < 0:
            raise ValueError("missing header 'Count'")
        elif count == 0:
            raise ValueError("no ddds saved")
        elif not doms:
            raise ValueError("missing header 'Domains'")
        elif doms != {v: self.sdoms[v] for v in self.vars}:
            raise ValueError("incompatible domains")
        elif tuple(doms) != self.vars:
            raise ValueError("incompatible variables ordering")
        # read DDDs
        vec.resize(count)
        loadDDD(f, vec)
        f.close()
        return headers, [self.makeddd(d) for d in vec]


##
## ddd
##


cdef class edge:
    """the edge of a `ddd`

    Attributes:
     - `str var`: variable name corresponding to the edge source node
     - `int val`: value on the edge
     - `ddd succ`: target node of the edge

    The source node is not given because it is always the `ddd` from which the
    edges are extracted.
    """
    def __cinit__(self, str var, val_t val, ddd succ):
        self.var = var
        self.val = val
        self.succ = succ

    cdef inline tuple tuple(self):
        "return a pair with var number, and val"
        return (self.succ.f.vmap[self.var], self.val)

    cdef inline void check(self, edge other):
        "check if same domain"
        if self.succ.f != other.succ.f:
            raise ValueError("not same domains")

    @property
    def domain(self):
        return self.succ.f

    def __eq__(self, edge other):
        """equality

        Two edges are equal if they have the same domain and fields

        """
        return (self.succ.f == other.succ.f
                and self.var == other.var
                and self.val == other.val
                and self.succ == other.succ)

    def __ne__(self, edge other):
        "inequality"
        return not self.__eq__(other)

    def __lt__(self, edge other):
        """strictly lower than

        Comparison is based on the order of variables in the domain,
        and then the values.
        """
        self.check(other)
        return self.tuple < other.tuple

    def __le__(self, edge other):
        """lower than or equal

        Comparison is based on the order of variables in the domain,
        and then the values.
        """
        self.check(other)
        return self.tuple <= other.tuple

    def __gt__(self, edge other):
        """strictly greater than

        Comparison is based on the order of variables in the domain,
        and then the values.
        """
        self.check(other)
        return self.tuple > other.tuple

    def __ge__(self, edge other):
        """greater than or equal

        Comparison is based on the order of variables in the domain,
        and then the values.
        """
        self.check(other)
        return self.tuple >= other.tuple


cdef class ddd:
    """data-decision-diagram

    This class exposes a high-level representation of class `DDD` from
    `libDDD`. In particular, variable numbers are never exposed, only variable
    names are. Moreover, `ddd` instances are associated with domains
    and only the `ddd`s from the same domain are compatible with each other.
    """
    def __init__(self):
        """class `ddd` should never be instanciated directly

        To construct a `ddd` instance, use either:
         - `domain.__call__()` that is the usual method
         - `domain.one` or `domain.empty` that are less likely
            to be useful
        """
        raise TypeError("class 'ddd' should not be instantiated directly")

    @property
    def domain(self):
        """domain from which the `hom` is

        >>> dom = domain(x=2, y=2)
        >>> d = dom(x=0, y=1)
        >>> d.domain is dom
        True
        """
        return self.f

    @property
    def vars(self):
        """the variables in this `ddd`

        Usually these are the variables of its domain, by if the `ddd` is the
        internal node of a larger `ddd`, only the trailing part will be
        returned

        >>> dom = domain(x=2, y=2)
        >>> d = dom(x=0, y=1)  # d is  (x)---0-->(y)---1-->[ONE]
        >>> d.vars
        ('x', 'y')
        >>> e = next(iter(d))  # e is  (x)---0-->(y) 
        >>> e.succ.vars        # e.succ is  (y)---1---> [ONE]
        ('y',)

        Return: `tuple`
        """
        return self.f.vars[self.d.variable():]

    @property
    def head(self):
        """the variable name on the top-node of the `ddd`

        >>> dom = domain(x=2, y=2)
        >>> d = dom(x=0, y=1)  # d is  (x)---0-->(y)---1-->[ONE]
        >>> d.head
        'x'
        >>> e = next(iter(d))  # e is  (x)---0-->(y) 
        >>> e.succ.head        # e.succ is  (y)---1--->[ONE]
        'y'

        Return: `str`
        """
        return self.f.vmap[self.d.variable()]

    @property
    def stop(self):
        """whether this `ddd` is NULL of ONE

        This allows to test that a traversal of a `ddd` has reached a stop,
        that is either the `ddd` is empty, or it is an accepting leaf at the
        bottom of a larger `ddd`

        >>> dom = domain(x=2, y=2)
        >>> dom.one.stop
        True
        >>> dom.empty.stop
        True
        >>> d = dom(x=0, y=1)  # d is  (x)---0-->(y)---1-->[ONE]
        >>> d.stop
        False
        >>> e = next(iter(d))  # e is  (x)---0-->(y) 
        >>> e.succ.stop        # e.succ is  (y)---1--->[ONE]
        False
        >>> e = next(iter(e.succ))  # e is  (y)---0-->[ONE]
        >>> e.succ.stop             # e.succ is  [ONE]
        True

        Return: `bool`
        """
        return ddd_is_STOP(self.d)

    # FIXME: find a general way to build ddd manually while not breaking domains
    #  def __add__(self, ddd other):
    #      """concatenation
    #
    #      `a + b` replaces "one" terminals of `a` by `b`.
    #      This is used to build a `ddd` by hand, but avoid it unless you known
    #      what you're doing. In particular, this allows to build `ddd`s that are
    #      not valid with respect to the variable ordering or the organisation in
    #      layers of variables.
    #      """
    #      self.f.checkd(other)
    #      return self.f.makeddd(ddd_concat(self.d, other.d))

    def __or__(self, ddd other):
        """union

        `a | b` contains all the valuations contained in `a` or `b`

        >>> dom = domain(x=2, y=2)
        >>> d1 = dom(x=0, y=0) | dom(x=1, y=1)
        >>> d2 = dom(x=1, y=0) | dom(x=0, y=1)
        >>> d1 != d2
        True
        >>> d1 & d2 == dom.empty
        True
        >>> d1 != dom.full != d2
        True
        >>> d1 | d2 == dom.full
        True
        >>> d1 | dom.empty == d1
        True
        """
        self.f.checkd(other)
        return self.f.makeddd(ddd_union(self.d, other.d))

    def __xor__(self, ddd other):
        """disjoint union

        `a ^ b` is `(a | b) - (a & b)`
        """
        return (self | other) - (self & other)

    def __and__(self, object other):
        """intersection

        `a & b` contains all the valuations contained in `a` and `b`

        >>> dom = domain(x=2, y=2)
        >>> d = dom(x=0, y=0) | dom(x=1, y=1)
        >>> d != dom.full
        True
        >>> d & dom.empty == dom.empty
        True
        >>> d & dom.full == d
        True
        """
        cdef ddd d
        cdef hom h
        if isinstance(other, ddd):
            d = <ddd>other
            self.f.checkd(d)
            return self.f.makeddd(ddd_intersect(self.d, d.d))
        elif isinstance(other, hom):
            h = <hom>other
            self.f.checkh(h)
            return self.f.makehom(hom_intersect_Hom_DDD(h.h, self.d))
        else:
            raise TypeError(f"expected 'ddd' or 'hom' object but got"
                            f" '{other.__class__.__name__}'")

    def __invert__(self):
        """complement within the domain

        `~d == d.domain.full - d`

        >>> dom = domain(x=2, y=2)
        >>> d = dom(x=0, y=0)
        >>> ~d == dom.full - d
        True
        >>> ~d == dom(x=0, y=1) | dom(x=1, y=0) | dom(x=1, y=1)
        True
        """
        return self.f.full - self

    def __sub__(self, ddd other):
        """difference

        `a - b` contains all the valuations that are in `a` but not in `b`

        >>> dom = domain(x=2, y=2)
        >>> d = dom(x=0, y=0)
        >>> dom.full - d == dom(x=0, y=1) | dom(x=1, y=0) | dom(x=1, y=1)
        True
        """
        self.f.checkd(other)
        return self.f.makeddd(ddd_minus(self.d, other.d))

    def __eq__(self, ddd other):
        """equality
        
        `a == b` iff `a` contains exactly the same valuations as `b` and both
        are from the same domain

        >>> dom1 = domain(x=2, y=2)
        >>> dom2 = domain(x=2, y=2)
        >>> dom3 = domain(y=2, x=2)
        >>> dom1(x=0, y=0) == dom2(x=0, y=0)
        True
        >>> dom1(x=0, y=0) == dom3(x=0, y=0)
        False
        >>> dom1(x=0, y=0) == dom1(x=1, y=0)
        False
        """
        return self.f == other.f and self.d.set_equal(other.d)

    def __ne__(self, ddd other):
        """inequality

        `a != b` iff not `a == b`
        """
        return not self.__eq__(other)

    def __le__(self, ddd other):
        """inclusion

        `a <= b` iff all the valuations in `a` are also in `b` and both are
        from the same domain

        >>> dom = domain(x=2, y=2)
        >>> dom(x=0, y=0) <= dom.full
        True
        >>> dom(x={0, 1}, y={0, 1}) <= dom.full
        True
        """
        return (self | other) == other

    def __lt__ (self, ddd other):
        """strict inclusion

        `a < b` iff `a <= b` and `a != b`

        >>> dom = domain(x=2, y=2)
        >>> dom(x=0, y=0) < dom.full
        True
        >>> dom(x={0, 1}, y={0, 1}) < dom.full
        False
        """
        return self != other and self <= other

    def __ge__ (self, ddd other):
        """reversed inclusion

        `a >= b` iff `b <= a`

        >>> dom = domain(x=2, y=2)
        >>> dom.full >= dom(x=0, y=0)
        True
        >>> dom(x={0, 1}, y={0, 1}) >= dom.full
        True
        """
        return (self | other) == self

    def __gt__ (self, ddd other):
        """reversed strict inclusion

        `a > b` iff `b < a`

        >>> dom = domain(x=2, y=2)
        >>> dom.full > dom(x=0, y=0)
        True
        >>> dom(x={0, 1}, y={0, 1}) > dom.full
        False
        """
        return self != other and self >= other

    def __len__(self):
        """number of valuations

        The length of a `ddd` is the number of valuations it contains.
        Note that the length of ONE is `1` by convention.

        >>> dom = domain(x=2, y=2, z=3)
        >>> len(dom.full)  # 2*2*3
        12
        >>> len(dom.empty)
        0
        >>> len(dom.one)
        1
        >>> len(dom(x=0, y=0, z=0) | dom(x=1, y=1, z=1) | dom(x=1, y=1, z=1))
        2
        """
        return int(self.d.set_size())

    def __bool__(self):
        """a `ddd` is `True` iff it is ONE or contains at least one valuation

        >>> dom = domain(x=2, y=2)
        >>> bool(dom.full)
        True
        >>> bool(dom.empty)
        False
        >>> bool(dom.one)
        True
        >>> bool(dom(x=0, y=0, z=0))
        True
        """
        return self.d.set_size() > 0

    def __hash__(self):
        """hash of a `ddd`

        The hash of a `ddd` is unique wrt its set of valuations. So, two `ddd`s
        `a` and `b` such that `a == b` also have the same hash.
        """
        return int(self.d.hash())

    cdef DDD _pick(self, DDD d):
        "auxiliary method to compute `ddd.pick()`"
        cdef ddd_iterator it
        if ddd_is_STOP(d):
            return d
        it = ddd_iterator_begin(d)
        if ddd_iterator_end(it, d):
            return ddd_new_EMPTY()
        return DDD(d.variable(),
                   ddd_iterator_value(it),
                   self._pick(ddd_iterator_ddd(it)))

    def pick(self, as_dict=False):
        """pick an arbitrary valuation from a `ddd`

        The returned valuation is arbitrary in the sense that we cannot expect
        it to have specific properties, but it is not randomly chosen

        >>> dom = domain(x=2, y=2)
        >>> p = dom.full.pick()
        >>> p <= dom.full
        True
        >>> len(p)
        1

        Arguments:
         - `bool as_dict`: if `True`, the picked valuation is returned as a
           `dict`, otherwise its is returned as a `ddd` (default)

        Return: `ddd` or `dict`
        """
        cdef ddd p = self.f.makeddd(self._pick(self.d))
        cdef dict d
        if as_dict:
            for d in p.values():
                return d
        else:
            return p

    def __iter__(self):
        """yield the edges starting from the top-node of a `ddd`

        Each edge is an instance of class `edge`, this allows to traverse a
        `ddd` considered as a graph.

        >>> dom = domain(x=2, y=2)  # (x)---0|1-->(y)---0|1-->[ONE]
        >>> for x, e in enumerate(sorted(dom.full)):
        ...     assert e.var == "x"
        ...     assert e.val == x
        ...     for y, f in enumerate(sorted(e.succ)):
        ...         assert f.var == "y"
        ...         assert f.val == y
        ...         assert f.succ == dom.one

        Note that sorting the edges as above is generally not a good idea as
        it leads to explicitly enumerate all of them at each level. This was
        only made to exhibit the structure of the (very small) `ddd`.

        Yield: `edge` instances
        """
        cdef ddd_iterator it
        if not self.stop:
            it = ddd_iterator_begin(self.d)
            while not ddd_iterator_end(it, self.d):
                yield edge(self.head,
                           ddd_iterator_value(it),
                           self.f.makeddd(ddd_iterator_ddd(it)))
                ddd_iterator_next(it)

    def values(self):
        """yield all the valuations as `dict`s

        This method explicitly enumerates the `ddd` and is inefficient
        on large `ddd`s.

        >>> dom = domain(x=2, y=2)
        >>> values = list(dom.full.values())
        >>> len(values)
        4
        >>> for i in [0, 1]:
        ...     for j in [0, 1]:
        ...         assert dict(x=i, y=j) in values

        Yield: `dict`
        """
        cdef edge e
        cdef dict s
        if self.stop:
            yield {}
        else:
            for e in self:
                for s in e.succ.values():
                    yield {e.var: e.val} | s

    def domains(self, dict doms=None):
        """compute the actual domains of variables

        For each variable `v`, this is the set values that `v` can have among
        all the valuations stored in the `ddd`.

        >>> dom = domain(x=2, y=2)
        >>> d = dom(x=0, y=1)
        >>> d.domains() == {'x': {0}, 'y': {1}}
        True

        Arguments:
         - `dict doms`: if not `None`, this `dict` is updated otherwise, a fresh
           `dict` is used

        Return: a `dict` mapping variable names to `set`s
        """
        cdef edge e
        if doms is None:
            doms = {}
        doms.setdefault(self.head, set())
        for e in self:
            doms[e.var].add(e.val)
            e.succ.domains(doms)
        return doms

    def _dot(self, out, nid, node):
        nid[node] = len(nid)
        if node.stop:
            out.write(f'    "n{nid[node]}" [shape=square, label="1"];\n')
        else:
            out.write(f'    "n{nid[node]}" [label="{node.head}"];\n')
        edges = defaultdict(set)
        for e in node:
            if e.succ not in nid:
                self._dot(out, nid, e.succ)
            edges[e.succ].add(e.val)
        for succ, values in edges.items():
            m, M = min(values), max(values)
            if m == M:
                lbl = f"{m}"
            if (count := len(values)) == M - m + 1 and count > 2:
                lbl = f"{m}..{M}"
            else:
                lbl = "|".join(str(v) for v in sorted(values))
            out.write(f'    n{nid[node]} -> n{nid[succ]} [label="{lbl}"];\n')

    def dot(self, path):
        """dump `ddd` to GraphViz `dot` format

        If `path` as suffix `.dot`, a `dot` file is just saved, otherwise, it is
        converted to the corresponding format (eg, `pdf`, `png`, `svg`, or any
        format supported by the local GraphViz installation)

        Arguments:
         - `str|pathlib.Path path`: target file
        """
        path = Path(path)
        path_dot = path.with_suffix(".dot")
        with path_dot.open("w") as out:
            out.write("digraph ddd {\n")
            self._dot(out, defaultdict(), self)
            out.write("}\n")
        if (fmt := path.suffix.lower().lstrip(".")) != "dot":
            check_call(["dot", f"-T{fmt}", "-o", path, path_dot])

##
## Hom
##

cdef extern from "dddwrap.h":
    cdef bint hom_eq(Hom a, Hom b)
    cdef bint hom_ne(Hom a, Hom b)
    cdef Hom hom_neg(Hom a)
    cdef DDD hom_call(Hom h, DDD d)
    cdef Hom hom_union(Hom a, Hom b)
    cdef Hom hom_circ(Hom a, Hom b)
    cdef Hom hom_intersect_DDD_Hom(DDD a,Hom b)
    cdef Hom hom_intersect_Hom_DDD(Hom a, DDD b)
    cdef Hom hom_intersect_Hom_Hom(Hom a, Hom b)
    cdef Hom hom_minus_Hom_DDD(Hom a, DDD b)
    cdef Hom hom_ITE(Hom a, Hom b, Hom c)
    cdef Hom fixpoint(const Hom &h)


cdef class hom:
    """homomorphisms on a `ddd`

    This class exposes a high-level representation of class `Hom` from `libDDD`.
    As for class `ddd`, instances are associated with domains and only the
    `ddd`s and `hom`s from the same domain are compatible with each other.
    """
    def __init__(self):
        """class `hom` should never be instanciated directly

        To construct a `hom` instance, use either:
         - `domain.__call__()` that is the usual method
         - `domain.id`, `domain.const()`, or `domain.op()`
        """
        raise TypeError("class 'hom' should not be instantiated directly")

    @property
    def domain(self):
        "domain from which the `hom` is"
        return self.f

    def __hash__(self):
        "hash of a `hom`"
        return int(self.h.hash())

    def __eq__(self, hom other):
        """equality of two `hom`

        Two `hom` instances are equal if they are the same operation and are
        both from the same domain.
        """
        return self.f == other.f and hom_eq(self.h, other.h)

    def __ne__(self, hom other):
        """inequality

        `a != b` iff not `a == b`
        """
        return self.f == other.f and hom_ne(self.h, other.h)

    def __invert__(self):
        """negation of a selector `hom`

        `(~h)(d) == d - h(d)`

        >>> dom = domain(x=2, y=2)
        >>> h = dom("x == 0")
        >>> (~h)(dom.full) == dom(x=1, y={0, 1})
        True
        """
        if not self.is_selector():
            raise ValueError("not a selector")
        return self.f.makehom(hom_neg(self.h))

    def __call__(self, ddd d):
        """application onto a `ddd`

        >>> dom = domain(x=2, y=2)
        >>> h = dom("x == 0")
        >>> h(dom.full) == dom(x=0, y={0, 1})
        True

        Return: the resulting `ddd`
        """
        self.f.checkd(d)
        return self.f.makeddd(hom_call(self.h, d.d))

    def __or__(self, hom other):
        """union of two `hom`

        `(h1 | h2)(d) == h1(d) | h2(d)`

        >>> dom = domain(x=2, y=2)
        >>> h = dom("x == 0") | dom("y == 0")
        >>> h(dom.full) == dom.full - dom(x=1, y=1)
        True
        """
        self.f.checkh(other)
        return self.f.makehom(hom_union(self.h, other.h))

    def __mul__(self, hom other):
        """composition of two `hom`
        
        `(h1 * h2)(d) == h1(h2(d))`

        >>> dom = domain(x=2, y=2)
        >>> h = dom("x += 1") * dom("x == 0")  # select x==0, then do x += 1
        >>> h(dom.full) == dom(x=1, y={0, 1})
        True
        """
        self.f.checkh(other)
        return self.f.makehom(hom_circ(self.h, other.h))

    def __and__(self, object other):
        """intersection with a `ddd` or another `hom`

        `(h & d1)(d2) == h(d1) & d2`
        `(h1 & h2)(d) == h1(d) & h2(d)`

        >>> dom = domain(x=2, y=2)
        >>> h = dom("x += 1")
        >>> d = h(dom.full)
        >>> values = list(d.values())
        >>> assert len(values) == 4
        >>> assert {"x": 1, "y": 0} in values
        >>> assert {"x": 1, "y": 1} in values
        >>> assert {"x": 2, "y": 0} in values
        >>> assert {"x": 2, "y": 1} in values
        >>> (h & dom.full)(dom.full) == dom(x=1, y={0, 1})
        True
        >>> (h & dom("x <= 1"))(dom.full) == dom(x=1, y={0, 1})
        True
        """
        cdef ddd d
        cdef hom h
        if isinstance(other, ddd):
            d = <ddd>other
            self.f.checkd(d)
            return self.f.makehom(hom_intersect_Hom_DDD(self.h, d.d))
        elif isinstance(other, hom):
            h = <hom>other
            self.f.checkh(h)
            if not other.is_selector():
                raise ValueError("not a selector")
            return self.f.makehom(hom_intersect_Hom_Hom(self.h, h.h))
        else:
            raise TypeError(f"expected 'hom' or 'ddd' object but got"
                            f" '{other.__class__.__name__}'")

    def __sub__(self, ddd other):
        """difference with a `ddd`

        `(h - d1)(d2) == h(d1) - d2`

        >>> dom = domain(x=2, y=2)
        >>> d = dom(x=1, y=1)
        >>> h = dom("x += 1") * dom("x == 0")
        >>> (h - d)(dom.full) == dom(x=1, y=0)
        True
        """
        self.f.checkd(other)
        return self.f.makehom(hom_minus_Hom_DDD(self.h, other.d))

    cpdef hom ite(self, hom then, hom orelse=None):
        """if-then-else composition

        `h.ite(h1, h2)(d)` is `h1(d)` if `h(d)` is not empty, otherwise it is
        `h2(d)`. If `h2` is omitted, it is replaced with the identity `hom`
        
        >>> dom = domain(x=2, y=2)
        >>> cond = dom("x == 0")
        >>> then = dom("x += 1")
        >>> h = cond.ite(then)
        >>> h(dom.full) == dom(x=1, y={0, 1})
        True
        >>> h = cond.ite(then, dom(":=", x=0, y=0))
        >>> h(dom.full) == dom(x=1, y={0, 1}) | dom(x=0, y=0)
        True
        """
        if not self.is_selector():
            raise ValueError("not a selector")
        self.f.checkh(then)
        if orelse is None:
            return self.f.makehom(hom_ITE(self.h, then.h, self.f.id.h))
        else:
            self.f.checkh(orelse)
            return self.f.makehom(hom_ITE(self.h, then.h, orelse.h))

    cpdef hom fixpoint (self):
        """fixpoint homomorphism

        `h.fixpoint(d)` is equivalent to compute `d = h(d)` until a fixpoint is
        reached.

        Note: this operation is not guaranteed to converge, use `lfp` and `gfp`
        instead to have such a guarantee.
        """
        return self.f.makehom(fixpoint(self.h))

    cpdef hom lfp (self):
        """least fixpoint homomorphism

        This is `(h | id).fixpoint()`, where `id` is the identity homomorphism,
        that is guaranteed to converge. This results in an homomorphism that
        tends to grow its argument.

        >>> dom = domain(x=10)
        >>> h = dom("x < 9").ite(dom("x += 1"))
        >>> (h.lfp())(dom(x=0)) == dom.full
        True
        """
        return (self | self.f.id).fixpoint()

    cpdef hom gfp (self):
        """greatest fixpoint homomorphism

        This is `(h & id).fixpoint()`, where `id` is the identity homomorphism,
        that is guaranteed to converge. This results in an homomorphism that
        tends to shrink its arguments.

        >>> dom = domain(x=10)
        >>> h = dom("x < 9").ite(dom("x += 1"))
        >>> (h.gfp())(dom.full) == dom(x=9)
        True
        """
        return (self & self.f.id).fixpoint()

    cpdef hom invert (self, ddd potential=None):
        """predecessor homomorphism

        If `h(d1)` == d2` then `h.invert()(d2) == d1`, where `d1` is included
        into the domain from which `h` is. If the domain needs to be further
        restricted to a subdomain `p` (for instance a set of reachable states),
        use `h.invert(p)`.

        >>> dom = domain(x=2, y=2)
        >>> h = dom("x += 1") * dom("x == 0")  # selects x==0, then x+=1
        >>> f = h.invert()
        >>> f(dom(x=1, y=1)) == dom(x=0, y=1)
        True
        """
        cdef DDD p
        if potential is not None:
            self.f.checkd(potential)
            p = potential.d
        else:
            p = self.f.full.d
        return self.f.makehom(self.h.invert(p))

    cpdef bint is_selector(self):
        """chech whether teh homomorphism is a selector

        A selector is a homomorphism that only selects paths of a `ddd` but
        does not change the valuations and does not add paths.
        """
        return self.h.is_selector()

    cpdef hom clip(self):
        """restriction tho the domain

        `h(d)` is not guaranteed to be included in the domain of `h`,
        but `h.clip()(d)` is as it is `h & h.domain.full`

        >>> dom = domain(x=(0, 1))
        >>> d = dom(x=0)
        >>> h = dom("x += 5")
        >>> h(d) <= dom.full
        False
        >>> for v in h(d).values():
        ...     print(v)
        {'x': 5}
        >>> h.clip()(d) <= dom.full
        True
        >>> len(h.clip()(d))
        0
        """
        return self & self.f.full
