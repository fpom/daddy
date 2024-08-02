Data Decision Diagrams with a pythonic interface
================================================

This library provides a Python binding for the Data Decision Diagrams
library [libDDD](https://github.com/lip6/libDDD). Compared to
[pyddd](https://github.com/fpom/pyddd), `daddy` provides a much higher-level
interface with an easy Pythonic API.

## Requirements

 - Python 3
 - sympy
 - Cython (for installation)
 - requests (for installation)

libDDD itself is downloaded and statically linked into the main module during
the installation. (Static linking simplifies things a lot as libDDD is compiled
with tricky flags.)

## Installation

Run `pip install daddy` as usual. It may take some time as libDDD is downloaded
and upacked if not found in `src` subdirectory. Then, compilation itself takes
quite some time.

## Usage

`daddy` module exposes the content of its sub-module `daddy.dddlib` that exports
three classes:

 - `domain` is the starting point, allowing to define a set of variables over
   given domains, from a `domain` instance, one can derive the other objects
 - `ddd` is a non-mutable  set of valuations for the variables of a domain
 - `hom` is an operation on a `ddd` that returns another `ddd` and is used
   as a function

Additionally, `daddy.dddlib` defined class `edge` that is used to iterate over the
structure of a `ddd`. Documentation is currently within the docstrings, to start
with, look at `domain.__init__` and `domain.__call__`.

## Licence (MIT)

(C) 2024 Franck Pommereau <franck.pommereau@univ-evry.fr>

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the “Software”), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
