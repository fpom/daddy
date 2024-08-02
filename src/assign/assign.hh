#ifndef __ASSIGN_HH
#define __ASSIGN_HH

#include "ddd/Hom.h"

// `assign_hom(tgt, src, aug, inc, mul)` implements either:
//  - `tgt = mul*src + inc` if `aug` is false
//  - `tgt += mul*src + inc` if `aug` is true
// where `tgt` and `src` are two DDD variables, and `inc` and `mul` are ints
GHom assignHom(int tgt, int src, int aug, int inc, int mul);

#endif
