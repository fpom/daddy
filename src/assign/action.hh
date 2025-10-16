#ifndef __ACTION_HH
#define __ACTION_HH

#include "ddd/Hom.h"
#include "ddd/Hom_Basic.hh"
#include <vector>

typedef enum comparator { EQ, NEQ, LT, GT, LEQ, GEQ } comparator;

typedef struct weightedsum_t {
  int value;
  std::vector<int> coefs;
} weightedsum_t;

typedef struct condition_t {
  comparator op;
  int value;
  std::vector<int> coefs;
} condition_t;

typedef struct action_t {
  std::vector<condition_t> cond;
  std::vector<weightedsum_t> assign;
} action_t;

GHom actionHom(action_t a);

#endif
