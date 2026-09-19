fn grade(x) {
  if (x >= 90) { return "A"; }
  else if (x >= 80) { return "B"; }
  else if (x >= 70) { return "C"; }
  else { return "F"; }
}
print(grade(95), grade(85), grade(75), grade(10));
if (1 > 2) { print("no"); }
if (1 < 2) { print("yes"); }
if (false) { print("a"); } else { print("b"); }
let x = 5;
if (x == 5) { if (x > 3) { print("nested"); } else { print("wrong"); } }
