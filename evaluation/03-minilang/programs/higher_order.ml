fn map(xs, f) {
  let out = [];
  let i = 0;
  while (i < len(xs)) { push(out, f(xs[i])); i = i + 1; }
  return out;
}
fn filter(xs, pred) {
  let out = [];
  let i = 0;
  while (i < len(xs)) { if (pred(xs[i])) { push(out, xs[i]); } i = i + 1; }
  return out;
}
fn compose(f, g) { return fn (x) { return f(g(x)); }; }
print(map([1, 2, 3], fn (x) { return x * x; }));
print(filter(range(10), fn (x) { return x % 3 == 0; }));
let inc = fn (x) { return x + 1; };
let dbl = fn (x) { return x * 2; };
print(compose(inc, dbl)(5), compose(dbl, inc)(5));
fn curry(a) { return fn (b) { return fn (c) { return a + b + c; }; }; }
print(curry(1)(2)(3));
print(type(inc), inc);
let apply = fn (f, v) { return f(v); };
print(apply(len, "four"), apply(str, 42) + "!");
