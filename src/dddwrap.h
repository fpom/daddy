#include <fstream>
#include <sstream>
#include "ddd/DDD.h"

#define val_t GDDD::val_t

#define ddd_new_ONE() DDD(DDD::one)
#define ddd_new_EMPTY() DDD(DDD::null)
#define ddd_is_STOP(d) (d == DDD::one) || (d == DDD::null)

#define ddd_concat(a,b) DDD(a ^ b)
#define ddd_union(a,b) DDD(a + b)
#define ddd_intersect(a,b) DDD(a * b)
#define ddd_minus(a,b) DDD(a - b)

#define ddd_iterator GDDD::const_iterator
#define ddd_iterator_begin(d) d.begin()
#define ddd_iterator_next(i) i++
#define ddd_iterator_end(i,d) (i == d.end())
#define ddd_iterator_value(i) i->first
#define ddd_iterator_ddd(i) DDD(i->second)

#define hom_eq(a,b) (a == b)
#define hom_ne(a,b) (a != b)
#define hom_call(h,d) DDD(h(d))
#define hom_union(a,b) (a + b)
#define hom_circ(a,b) (a & b)
#define hom_intersect_DDD_Hom(a,b) (a * b)
#define hom_intersect_Hom_DDD(a,b) (a * b)
#define hom_intersect_Hom_Hom(a,b) (a * b)
#define hom_minus_Hom_DDD(a,b) (a - b)
#define hom_ITE(a,b,c) ITE(a, b, c)
#define hom_neg(a) (! a)
