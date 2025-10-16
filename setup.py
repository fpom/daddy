import os
import sys
import requests
import tarfile

from pathlib import Path
from setuptools import setup, Extension

from Cython.Build import cythonize
from Cython.Compiler import Options

##
##
##

DDD = Path("usr/local")
URL = {
    "linux": "https://lip6.github.io/libDDD/linux.tgz",
    "darwin": "https://github.com/lip6/libDDD/raw/osx/osx.tgz",
    "win32": "https://github.com/lip6/libDDD/raw/Windows/windows.zip",
}
SYS = sys.platform
DDDURL = URL[SYS]
DDDLIB = DDD / "lib" / "libDDD.a"
DDDINC = DDD / "include"
DDDTAR = Path(DDDURL.rsplit("/", 1)[-1])

##
##
##

os.chdir("src")

if not DDDTAR.exists():
    print("Downloading", DDDTAR)
    with requests.get(DDDURL, stream=True) as r:
        with DDDTAR.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

if not DDD.exists():
    print("Unpacking", DDDTAR)
    with tarfile.open(DDDTAR) as arch:
        # windows.zip is actually a tar file
        arch.extractall()

if not DDDLIB.exists():
    print(DDDLIB, "not found")
    sys.exit(1)
if not DDDINC.exists():
    print(DDDINC, "not found")
    sys.exit(1)

##
##
##

Options.docstrings = True
Options.annotate = False

extensions = [
    Extension(
        "daddy.dddlib",
        ["daddy/dddlib.pyx", "assign/assign.cpp", "assign/action.cpp"],
        language="c++",
        include_dirs=[str(DDDINC), "."],
        extra_objects=[str(DDDLIB)],
        extra_compile_args=["-std=c++11"],
    ),
]

setup(
    name="daddy",
    packages=["daddy", "daddy.pygmy"],
    ext_modules=cythonize(extensions, language_level=3),
)
