fn nothing() { }
fn bare() { return; }
fn early(n) {
  let i = 0;
  while (true) {
    if (i == n) { return i * 10; }
    i = i + 1;
  }
  return -1;
}
fn after() { return 1; print("unreachable"); }
fn nested_block(x) { if (x) { { return "inner"; } } return "outer"; }
print(nothing(), bare(), type(nothing()));
print(early(3), after());
print(nested_block(true), nested_block(false));
fn loop_ret() { let i = 0; while (i < 5) { let j = 0; while (j < 5) { if (i * j == 6) { return [i, j]; } j = j + 1; } i = i + 1; } return nil; }
print(loop_ret());
