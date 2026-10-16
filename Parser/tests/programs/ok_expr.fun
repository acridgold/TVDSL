function expr(a: int[], b: bool) returns bool {
    x = 1 + 2 * 3 - 4 / 2 - 1;
    y = -x * -(2 + 3);
    z = a[0] + a[a[1]] * length(a);
    b = not b and x < y or x >= z and true;
    return b == false;
}
