let x = 1;
{
  x = 2;
  let y = 10;
  print(x, y);
}
print(x);
let z = "outer";
{
  let z = "inner";
  print(z);
  {
    let z = "innermost";
    print(z);
  }
  print(z);
}
print(z);
let i = 0;
while (i < 2) { let tmp = i * 2; i = i + 1; }
print(i);
fn f() { let x = 100; return x; }
print(f(), x);
