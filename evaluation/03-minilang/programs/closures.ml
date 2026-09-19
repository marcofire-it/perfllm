fn make_counter() {
  let n = 0;
  return fn () { n = n + 1; return n; };
}
let c1 = make_counter();
let c2 = make_counter();
c1(); c1();
print(c1(), c2());
let fs = [];
let i = 0;
while (i < 3) {
  let k = i;
  push(fs, fn () { return k; });
  i = i + 1;
}
print(fs[0](), fs[1](), fs[2]());
let gs = [];
let j = 0;
while (j < 3) {
  push(gs, fn () { return j; });
  j = j + 1;
}
print(gs[0](), gs[1](), gs[2]());
let shared = 0;
fn inc() { shared = shared + 1; }
fn get() { return shared; }
inc(); inc();
print(get(), shared);
fn adder(a) { return fn (b) { return a + b; }; }
let add5 = adder(5);
print(add5(3), adder(1)(2));
