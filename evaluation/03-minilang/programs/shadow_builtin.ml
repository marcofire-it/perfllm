fn use_len() { return len("abc"); }
{
  let len = fn (x) { return "shadowed"; };
  print(len("abc"));
}
print(len("abc"), use_len());
{
  let str = fn (v) { return "custom"; };
  print(str(1));
}
print(str(1));
{
  let range = 7;
  print(range);
}
