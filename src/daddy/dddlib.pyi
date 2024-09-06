from typing import Iterator

class domain:
    vmap: dict
    ddoms: dict
    sdoms: dict
    vars: dict
    depth: int
    full: ddd
    one: ddd
    empty: ddd
    id: hom
    parse: object
    def __init__(self, **doms): ...
    def __len__(self) -> int: ...
    def __eq__(self, other) -> bool: ...
    def __ne__(self, other) -> bool: ...
    @property
    def doms(self) -> dict[str, set[int]]: ...
    def __call__(self, *largs, **values) -> hom | ddd: ...
    def const(self, d: ddd) -> hom: ...
    def op(self, left: str, op: str, right: int | str) -> hom: ...
    def assign(self, _tgt: str, _inc: str, **coef: int) -> None: ...
    def save(self, path: str, *ddds: ddd, **headers: object) -> None: ...
    def load(self, path: str) -> domain: ...

class ddd:
    @property
    def domain(self) -> domain: ...
    @property
    def vars(self) -> tuple[str, ...]: ...
    @property
    def head(self) -> str: ...
    @property
    def stop(self) -> bool: ...
    def __or__(self, other: ddd) -> ddd: ...
    def __xor__(self, other: ddd) -> ddd: ...
    def __and__(self, other: ddd | hom) -> ddd | hom: ...
    def __invert__(self) -> ddd: ...
    def __sub__(self, other: ddd) -> ddd: ...
    def __eq__(self, other) -> bool: ...
    def __ne__(self, other) -> bool: ...
    def __le__(self, other: ddd) -> bool: ...
    def __lt__(self, other: ddd) -> bool: ...
    def __ge__(self, other: ddd) -> bool: ...
    def __gt__(self, other: ddd) -> bool: ...
    def __len__(self) -> int: ...
    def __bool__(self) -> bool: ...
    def __hash__(self) -> int: ...
    def pick(self, as_dict: bool = False) -> ddd | dict[str, int]: ...
    def __iter__(self) -> Iterator[edge]: ...
    def values(self) -> Iterator[dict[str, int]]: ...
    def domains(
        self, doms: dict[str, set[int]] | None = None
    ) -> Iterator[dict[str, set[int]]]: ...
    def dot(self, path: str) -> None: ...
    def clip(self) -> ddd: ...

class edge:
    var: str
    val: int
    succ: ddd
    @property
    def domain(self) -> domain: ...
    def __eq__(self, other) -> bool: ...
    def __ne__(self, other) -> bool: ...
    def __lt__(self, other) -> bool: ...
    def __le__(self, other) -> bool: ...
    def __gt__(self, other) -> bool: ...
    def __ge__(self, other) -> bool: ...

class hom:
    @property
    def domain(self) -> domain: ...
    def __hash__(self) -> int: ...
    def __eq__(self, other) -> bool: ...
    def __ne__(self, other) -> bool: ...
    def invert(self, potential: ddd | None = None) -> hom: ...
    def __call__(self, d: ddd) -> ddd: ...
    def __or__(self, other: hom) -> hom: ...
    def __mul__(self, other: hom) -> hom: ...
    def __and__(self, other: ddd | hom) -> ddd | hom: ...
    def __sub__(self, other: ddd) -> hom: ...
    def ite(self, then: hom, orelse: hom | None = None) -> hom: ...
    def fixpoint(self) -> hom: ...
    def lfp(self) -> hom: ...
    def gfp(self) -> hom: ...
    def is_selector(self) -> bool: ...
    def clip(self) -> hom: ...
