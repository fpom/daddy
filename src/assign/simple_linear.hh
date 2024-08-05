#ifndef __LINEONE_HH
#define __LINEONE_HH

#include "ddd/Hom.h"

// `lineOne_hom(tgt, src, aug, inc, mul)` implements either:
//  - `tgt = mul*src + inc` if `aug` is false
//  - `tgt += mul*src + inc` if `aug` is true
// where `tgt` and `src` are two DDD variables, and `inc` and `mul` are ints
GHom lineOneHom(int tgt, int src, int aug, int inc, int mul);

#endif
