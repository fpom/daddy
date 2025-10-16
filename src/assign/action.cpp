#include "action.hh"

std::size_t _vector_int_hash(std::size_t seed, std::vector<int> vec) {
  std::size_t h = seed;
  for (std::size_t i = 0; i < vec.size(); i++) {
    h = h * 31 + vec[i];
  }
  return h;
}

class _ActionHom : public StrongHom {
  action_t act;

public:
  _ActionHom(action_t a) : act(a) {
  }

  GDDD phiOne() const {
    GDDD d = GDDD::one;
    for (int i = (int)act.assign.size() - 1; i >= 0; i--) {
      d = GDDD(i, act.assign[i].value, d);
    }
    return d;
  }

  GHom phi(int vr, int vl) const {
    action_t newact;
    // check every condition wrt current edge
    for (int i = 0; i < (int)act.cond.size(); i++) {
      // partially evaluate condition wrt edge
      condition_t cond = act.cond[i];
      cond.coefs = act.cond[i].coefs; // copy vector
      cond.value += cond.coefs[vr] * vl;
      cond.coefs[vr] = 0;
      // check if it's fully evaluated
      int done = 1;
      for (int j = 0; j < (int)cond.coefs.size(); j++) {
        if (cond.coefs[j] != 0) {
          done = 0;
          break;
        }
      }
      if (done) {
        // if so, perform the test
        int istrue;
        switch (cond.op) {
        case EQ:
          istrue = (0 == cond.value);
          break;
        case NEQ:
          istrue = (0 != cond.value);
          break;
        case LT:
          istrue = (0 < cond.value);
          break;
        case GT:
          istrue = (0 > cond.value);
          break;
        case LEQ:
          istrue = (0 <= cond.value);
          break;
        case GEQ:
          istrue = (0 >= cond.value);
          break;
        default:
          istrue = 0;
          break;
        }
        // false => abort exploring this path
        if (!istrue) {
          return GHom(GDDD::null);
        }
        // true => we'll just forget it
      } else {
        // not fully evaluated => add it to continue the path
        newact.cond.push_back(cond);
      }
    }
    // partially evaluate each sum wrt current edge
    weightedsum_t sum = {};
    for (int i = 0; i < (int)act.assign.size(); i++) {
      weightedsum_t sum = act.assign[i];
      sum.coefs = act.assign[i].coefs; // copy vector
      sum.value += sum.coefs[vr] * vl;
      sum.coefs[vr] = 0;
      newact.assign.push_back(sum);
    }
    return actionHom(newact);
  }

  std::size_t hash() const {
    std::size_t h = 0;
    for (std::size_t i = 0; i < act.cond.size(); i++) {
      h = (_vector_int_hash(h, act.cond[i].coefs) * 31 + act.cond[i].value) *
              31 +
          (std::size_t)act.cond[i].op;
    }
    for (std::size_t i = 0; i < act.assign.size(); i++) {
      h = (_vector_int_hash(h, act.assign[i].coefs) * 31 +
           act.assign[i].value) *
          31;
    }
    return h;
  }

  bool operator==(const StrongHom &s) const {
    _ActionHom *ps = (_ActionHom *)&s;
    if (act.cond.size() != ps->act.cond.size()) {
      return false;
    }
    for (int i = 0; i < (int)act.cond.size(); i++) {
      if ((act.cond[i].op != ps->act.cond[i].op) ||
          (act.cond[i].value != ps->act.cond[i].value) ||
          (act.cond[i].coefs != ps->act.cond[i].coefs)) {
        return false;
      }
    }
    for (int i = 0; i < (int)act.assign.size(); i++) {
      if ((act.assign[i].value != ps->act.assign[i].value) ||
          (act.assign[i].coefs != ps->act.assign[i].coefs)) {
        return false;
      }
    }
    return true;
  }

  _GHom *clone() const {
    return new _ActionHom(*this);
  }
};

GHom actionHom(action_t act) {
  return GHom(_ActionHom(act));
}
