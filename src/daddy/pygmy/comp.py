class Visitor:
    def visit(self, node, **args):
        if isinstance(node, tuple):
            return tuple(self.visit(n, **args) for n in node)
        cls = node.__class__.__name__
        handler = getattr(self, f"visit_{cls}", self.generic_visit)
        return handler(node, **args)

    def generic_visit(self, node, **args):
        fields = {}
        for name, child in node:
            if isinstance(child, tuple):
                fields[name] = tuple(self.visit(c, **args)
                                     if isinstance(c, Code)
                                     else c
                                     for c in child)
            elif isinstance(child, Code):
                fields[name] = self.visit(child, **args)
            else:
                fields[name] = child
        return node(**fields)

    # declarations

    #  def visit_Var(self, node, **args):
    #      pass
    #
    #  def visit_Class(self, node, **args):
    #      pass
    #
    #  def visit_Func(self, node, **args):
    #      pass

    # statements

    #  def visit_Pass(self, node, **args):
    #      pass
    #
    #  def visit_Assign(self, node, **args):
    #      pass
    #
    #  def visit_BareCall(self, node, **args):
    #      pass
    #
    #  def visit_For(self, node, **args):
    #      pass
    #
    #  def visit_If(self, node, **args):
    #      pass
    #
    #  def visit_Return(self, node, **args):
    #      pass

    # expressions

    #  def visit_Const(self, node, **args):
    #      pass
    #
    #  def visit_Name(self, node, **args):
    #      pass
    #
    #  def visit_Attr(self, node, **args):
    #      pass
    #
    #  def visit_Item(self, node, **args):
    #      pass
    #
    #  def visit_Call(self, node, **args):
    #      pass
    #
    #  def visit_Op(self, node, **args):
    #      pass
