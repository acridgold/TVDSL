function fib(n) returns int {
    assume n >= 0;
    x = 0;
    y = 1;
    while (n != 0) {
        z = x + y;
        x = y;
        y = z;
        n = n - 1;
    }
    assert x >= 0; // sanity check
    return x;
}
