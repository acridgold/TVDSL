function ctl(x: int) returns bool {
    bool r = false;
    if (x > 0)
        if (x > 10) r = true; else r = false;
    {
        assert not r or x > 10;
        assume (x + 1) * 2 != 0;
    }
    helper(x, r);
    return r;
}
