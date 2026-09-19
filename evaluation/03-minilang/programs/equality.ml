print([1, [2, "a"]] == [1, [2, "a"]], [1, 2] == [1, 2, 3], [] == []);
print(1 == "1", 1 == true, nil == nil, nil == false, "1" == 1, 0 == false);
print([1] != [1], [1] != [2], nil != nil);
fn f() { return 1; }
let g = f;
print(f == g, f == fn () { return 1; }, f != g);
print(true == true, false == false, true == false);
let a = [1, 2];
let b = a;
print(a == b, a == [1, 2]);
