#include "assign.hh"

// implementations details borrowed from <libDDD>/demo/SetVar.cpp

class _AssignConst:public StrongHom {
  int var, val, aug;
public:
  _AssignConst(int vr, int vl, int ag):var(vr),val(vl),aug(ag) {}

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
    _AssignConst* ps = (_AssignConst*)&s;
    return var == ps->var && val == ps->val && aug == ps->aug;
  }

  _GHom * clone () const {
    return new _AssignConst(*this);
  }
};

class _AssignUp:public StrongHom {
  int var, val;
public:
  _AssignUp(int vr, int vl):var(vr),val(vl) {}

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
    _AssignUp* ps = (_AssignUp*)&s;
    return var == ps->var && val == ps->val;
  }

  _GHom * clone () const {
    return new _AssignUp(*this);
  }
};

class _AssignDown:public StrongHom {
  int tgt, src, inc, mul;
public:
  _AssignDown(int t, int s, int i, int m):tgt(t),src(s),inc(i),mul(m) {}

  GDDD phiOne() const {
    return GDDD::top;
  }

  GHom phi(int vr, int vl) const {
    if (vr == src) {
      return GHom(tgt, mul*vl + inc, GHom(vr, vl));
    } else {
      return GHom(_AssignUp(vr, vl)) & GHom(this);
    }
  }

  size_t hash() const {
    return ((mul*31 + inc)*31 + src)*31 + tgt;
  }

  bool operator==(const StrongHom &s) const {
    _AssignDown* ps = (_AssignDown*)&s;
    return tgt == ps->tgt && src == ps->src && inc == ps->inc && mul == ps->mul;
  }

  _GHom * clone () const {
    return new _AssignDown(*this);
  }
};

class _Assign:public StrongHom {
  int tgt, src, aug, inc, mul;
public:
  _Assign(int t, int s, int a, int i, int m):tgt(t),src(s),aug(a),inc(i),mul(m) {}

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
      return GHom(vr, vl, GHom(_AssignConst(tgt, mul*vl + inc, aug)));
    } else if (vr != tgt) {
      return GHom(vr, vl, GHom(this));
    } else if (aug) {
      return GHom(_AssignDown(tgt, src, vl+inc, mul));
    } else {
      return GHom(_AssignDown(tgt, src, inc, mul));
    }
  }

  size_t hash() const {
    return (((mul*31 + inc)*31 + aug)*31 + src)* 31 + tgt;
  }

  bool operator==(const StrongHom &s) const {
    _Assign* ps = (_Assign*)&s;
    return tgt == ps->tgt && src == ps->src && aug == ps->aug && inc == ps->inc && mul == ps->mul;
  }

  _GHom * clone () const {
    return new _Assign(*this);
  }
};

GHom assignHom(int tgt, int src, int aug, int inc, int mul) {
  if (mul == 0 && inc == 0 && aug) {
    return GHom();
  } else if (mul == 0) {
    return GHom(_AssignConst(tgt, inc, aug));
  } else {
    return GHom(_Assign(tgt, src, aug, inc, mul));
  }
}
