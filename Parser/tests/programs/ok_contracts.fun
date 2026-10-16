function max(a: int, b: int) returns (m: int)
requires true
ensures m >= a and m >= b
ensures m == a or m == b
{
    if (a > b) m = a; else m = b;
}

function noop() { }
