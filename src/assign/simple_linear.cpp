#include "lineone.hh"

// implementations details borrowed from <libDDD>/demo/SetVar.cpp

class _LineOneConst:public StrongHom {
  int var, val, aug;
public:
  _LineOneConst(int vr, int vl, int ag):var(vr),val(vl),aug(ag) {}

  GDDD phiOne() const {
    return GDDD::one;
  }

  GHom phi(int vr, int vl) const {
    if (vr != var) {
      return GHom(vr, vl, GHom(this)); 
    } else if (aug) {
      return GHom(vr, vl + val);
    } else {
      return GHom(vr, val);
    }
  }

  size_t hash() const {
    return (aug*31 + val)*31 + var;
  }

  bool operator==(const StrongHom &s) const {
    _LineOneConst* ps = (_LineOneConst*)&s;
    return var == ps->var && val == ps->val && aug == ps->aug;
  }

  _GHom * clone () const {
    return new _LineOneConst(*this);
  }
};

class _LineOneUp:public StrongHom {
  int var, val;
public:
  _LineOneUp(int vr, int vl):var(vr),val(vl) {}

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
    _LineOneUp* ps = (_LineOneUp*)&s;
    return var == ps->var && val == ps->val;
  }

  _GHom * clone () const {
    return new _LineOneUp(*this);
  }
};

class _LineOneDown:public StrongHom {
  int tgt, src, inc, mul;
public:
  _LineOneDown(int t, int s, int i, int m):tgt(t),src(s),inc(i),mul(m) {}

  GDDD phiOne() const {
    return GDDD::top;
  }

  GHom phi(int vr, int vl) const {
    if (vr == src) {
      return GHom(tgt, mul*vl + inc, GHom(vr, vl));
    } else {
      return GHom(_LineOneUp(vr, vl)) & GHom(this);
    }
  }

  size_t hash() const {
    return ((mul*31 + inc)*31 + src)*31 + tgt;
  }

  bool operator==(const StrongHom &s) const {
    _LineOneDown* ps = (_LineOneDown*)&s;
    return tgt == ps->tgt && src == ps->src && inc == ps->inc && mul == ps->mul;
  }

  _GHom * clone () const {
    return new _LineOneDown(*this);
  }
};

class _LineOne:public StrongHom {
  int tgt, src, aug, inc, mul;
public:
  _LineOne(int t, int s, int a, int i, int m):tgt(t),src(s),aug(a),inc(i),mul(m) {}

  GDDD phiOne() const {
    return GDDD::one;
  }                   

  GHom phi(int vr, int vl) const {
    if (vr == tgt && vr == src) {
      if (aug) {
        return GHom(vr, vl + mul*vl + inc);
      } else {
        return GHom(vr, mul*vl + inc);
      }
    } else if (vr == src) {
      return GHom(vr, vl, GHom(_LineOneConst(tgt, mul*vl + inc, aug)));
    } else if (vr != tgt) {
      return GHom(vr, vl, GHom(this));
    } else if (aug) {
      return GHom(_LineOneDown(tgt, src, vl+inc, mul));
    } else {
      return GHom(_LineOneDown(tgt, src, inc, mul));
    }
  }

  size_t hash() const {
    return (((mul*31 + inc)*31 + aug)*31 + src)* 31 + tgt;
  }

  bool operator==(const StrongHom &s) const {
    _LineOne* ps = (_LineOne*)&s;
    return tgt == ps->tgt && src == ps->src && aug == ps->aug && inc == ps->inc && mul == ps->mul;
  }

  _GHom * clone () const {
    return new _LineOne(*this);
  }
};

GHom lineOneHom(int tgt, int src, int aug, int inc, int mul) {
  if (mul == 0 && inc == 0 && aug) {
    return GHom();
  } else if (mul == 0) {
    return GHom(_LineOneConst(tgt, inc, aug));
  } else {
    return GHom(_LineOne(tgt, src, aug, inc, mul));
  }
}
