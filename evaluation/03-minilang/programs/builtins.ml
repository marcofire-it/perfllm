print(type(1), type(true), type("s"), type([]), type(nil), type(print), type(fn () { return 0; }));
print(str(1), str(true), str(false), str(nil), str("abc"), str([1, "a", nil]), str(-5));
print(int("42"), int("-7"), int(0), int(-3), int("007"));
print(len("hello"), len(""), len([1, 2]), len([]));
print(str(1) + str(2), int(str(99)) + 1);
let r = push([], 1);
print(r, type(r));
print(len(str(12345)), type(str(1)), type(int("1")));
print(range(3) == [0, 1, 2], type(range(1)));
