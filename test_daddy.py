import doctest
import daddy
import daddy.dddlib

for mod in (daddy, daddy.dddlib):
    print(f"testing '{mod.__name__}'")
    f, c = doctest.testmod(mod)
    print(f"> performed {c} tests, {f} failed")
