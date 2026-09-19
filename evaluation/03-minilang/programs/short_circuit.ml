print(false and (1 / 0 == 0));
print(true or (1 / 0 == 0));
print(true and false, false or true, false or false, true and true);
let n = 0;
fn side() { n = n + 1; return true; }
let r = false and side();
r = true or side();
print(n);
r = true and side();
r = false or side();
print(n, r);
print(false and false or true);
print(true or false and false);
