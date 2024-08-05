#include "assign.hh"

// implementations details borrowed from <libDDD>/demo/SetVar.cpp

class _LinearUp:public StrongHom {
  int var, val;
public:
 _LinearUp(int vr, int vl):var(vr),val(vl) {}

  GDDD phiOne() const {
    return GDDD::top;
  }

  GHom phi(int vr, int vl) const {
    return GHom(vr, vl, GHom(var, val)); 
  }

  size_t hash() const {
    return val*31 + var;
  }

  bool operator==(const StrongHom &s) const {
    _LinearUp* ps = (_LinearUp*)&s;
    return var == ps->var && val == ps->val;
  }

  _GHom * clone () const {
    return new _LinearUp(*this);
  }
};

class _LinearDown:public StrongHom {
  int tgt, inc;
  std::vector<int> coef;
public:
  _LinearDown(int t, std::vector<int> c, int i):tgt(t),inc(i),coef(c) {}

  GDDD phiOne() const {
    return GDDD(tgt, inc, GDDD::one);
  }

  GHom phi(int vr, int vl) const {
    int ni = vl*coef[vr] + inc;
    return GHom(_LinearUp(vr, vl)) & GHom(_LinearDown(tgt, coef, ni));
  }

  size_t hash() const {
    int h = 0;
    for (int i=0; i<(int)coef.size(); i++) {
      h = h*31 + i;
    }
    return (h*31 + inc)*31 + tgt;
  }

  bool operator==(const StrongHom &s) const {
    _LinearDown* ps = (_LinearDown*)&s;
    return tgt == ps->tgt && inc == ps->inc && coef == ps->coef;
  }

  _GHom * clone () const {
    return new _LinearDown(*this);
  }
};

class _Linear:public StrongHom {
  int tgt, inc;
  std::vector<int> coef;
public:
  _Linear(int t, std::vector<int> c, int i):tgt(t),inc(i),coef(c) {}

  GDDD phiOne() const {
    return GDDD::one;
  }

  GHom phi(int vr, int vl) const {
    int ni = vl*coef[vr] + inc;
    if (vr == tgt) {
      return GHom(_LinearDown(tgt, coef, ni));
    } else {
      return GHom(vr, vl, GHom(_Linear(tgt, coef, ni)));
    }
  }

  size_t hash() const {
    int h = 0;
    for (int i=0; i<(int)coef.size(); i++) {
      h = h*31 + i;
    }
    return (h*31 + inc)*31 + tgt;
  }

  bool operator==(const StrongHom &s) const {
    _Linear* ps = (_Linear*)&s;
    return tgt == ps->tgt && inc == ps->inc && coef == ps->coef;
  }

  _GHom * clone () const {
    return new _Linear(*this);
  }
};

GHom linearAssignHom(int tgt, std::vector<int> coef, int inc) {
  return GHom(_Linear(tgt, coef, inc));
}
