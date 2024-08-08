from typing import NoReturn


class LangError(Exception):
    def __init__(self, msg, fname, lineno, column, sourceline):
        self.file = fname
        self.lineno = lineno
        self.column = column
        self.sourceline = sourceline
        super().__init__(f"In '{fname}' line {lineno}\n"
                         f"-> {sourceline}\n"
                         f"   {' ' * column}^ {msg}")

    @classmethod
    def from_code(cls, code, msg) -> NoReturn:
        f, a, s = code.__file__, code.__ast__, code.__src__
        raise cls(msg, f, a.lineno, a.col_offset, s[a.lineno - 1])
