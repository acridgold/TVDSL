function fill(a: int[], n: int) returns int[]
uses sorted, permutation
requires n <= length(a)
ensures length(a) == n
{
    int i = 0;
    while (i < n)
        invariant 0 <= i
        invariant i <= n
    {
        a[i] = i * 2;
        a[i + 1] = a[i] + a[length(a) - 1];
        i = i + 1;
    }
    return a;
}
