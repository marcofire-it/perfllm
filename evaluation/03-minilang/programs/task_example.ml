// closure e liste
fn make_counter() {
  let n = 0;
  fn inc() { n = n + 1; return n; }
  return inc;
}
let c = make_counter();
c(); c();
print("count:", c());                 // count: 3

let xs = [3, 1, 2];
fn sort(v) {                          // bubble sort in place
  let i = 0;
  while (i < len(v)) {
    let j = 0;
    while (j < len(v) - 1 - i) {
      if (v[j] > v[j + 1]) { let t = v[j]; v[j] = v[j + 1]; v[j + 1] = t; }
      j = j + 1;
    }
    i = i + 1;
  }
}
sort(xs);
print(xs, len(xs), xs[-1]);           // [1, 2, 3] 3 3
print(-7 / 2, -7 % 2, 7 / -2);        // -3 -1 -3
print(str(12) + "!", type(nil));      // 12! nil
