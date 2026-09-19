let i = 0;
while (i < 10) {
  i = i + 1;
  if (i % 2 == 0) { continue; }
  if (i > 7) { break; }
  print(i);
}
print("i =", i);
let a = 0;
let out = [];
while (a < 3) {
  let b = 0;
  while (true) {
    if (b == a) { break; }
    push(out, a * 10 + b);
    b = b + 1;
  }
  a = a + 1;
}
print(out);
let k = 0;
while (k < 100) { k = k + 1; if (k == 3) { break; } }
print(k);
