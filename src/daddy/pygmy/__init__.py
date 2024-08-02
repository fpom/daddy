class LangError(Exception):
    def __init__(self, msg, fname, lineno, column, sourceline):
        self.file = fname
        self.lineno = lineno
        self.column = column
        self.sourceline = sourceline
        super().__init__(f"In '{fname}' line {lineno}\n"
                         f"-> {sourceline}\n"
                         f"   {' ' * column}^ {msg}")
