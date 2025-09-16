from ast import literal_eval as num
from pathlib import Path
from pygraphviz import AGraph


def dot2tikz(src: Path, tgt: Path, layout: str = "dot", styles=False, **tikz):
    g = AGraph(src)
    g.layout(prog=layout)
    nodes = {}
    xmax = ymax = xmin = ymin = None
    for n in g.nodes():
        x, y = [num(p) for p in n.attr["pos"].split(",")]
        xmax = x if xmax is None else max(x, xmax)
        xmin = x if xmin is None else min(x, xmin)
        ymax = y if ymax is None else max(y, ymax)
        ymin = y if ymin is None else min(y, ymin)
        nodes[n] = {
            "x": x,
            "y": y,
            "t": n.attr["label"],
            "s": n.attr.get("shape", None) == "square",
        }
    xd = xmax - xmin
    yd = ymax - ymin
    with open(tgt, "w") as out:
        if styles:
            out.write("\\tikzstyle{dddvar}=[draw,circle]\n")
            out.write("\\tikzstyle{dddone}=[draw]\n")
            out.write(
                "\\tikzstyle{dddarc}=[fill=white,opacity=.8,text opacity=1,scale=.6]\n"
            )
        opt = ",".join(f"{k}={v}" for k, v in tikz.items())
        out.write(f"\\begin{{tikzpicture}}[{opt}]\n")
        for n, a in nodes.items():
            x = (a["x"] - xmin) / xd
            y = (a["y"] - ymin) / yd
            s = "dddone" if a["s"] else "dddvar"
            out.write(f"  \\node[{s}] ({n}) at ({x:.3f},{y:.3f}) {{{a['t']}}};\n")
        for e in g.edges():
            t = e.attr["label"].replace("|", ",")
            out.write(f"  \\draw[->] ({e[0]}) -- node[dddarc] {{{t}}} ({e[1]});\n")
        out.write("\\end{tikzpicture}\n")
