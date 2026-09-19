fn fib(n) { if (n < 2) { return n; } return fib(n - 1) + fib(n - 2); }
print(fib(20));
fn count(n) { if (n == 0) { return 0; } return 1 + count(n - 1); }
print(count(200));
fn even(n) { if (n == 0) { return true; } return odd(n - 1); }
fn odd(n) { if (n == 0) { return false; } return even(n - 1); }
print(even(10), odd(7), even(7));
fn sum_list(xs, i) { if (i == len(xs)) { return 0; } return xs[i] + sum_list(xs, i + 1); }
print(sum_list([1, 2, 3, 4], 0));
