"""Public check of conditional refinement budgets; no lattice calculation.

Only 0 < Delta <= 1 is supported by the tail enclosure used here.
Decimal arithmetic rounds every interval operation outwards. For n > N,
A_n <= A_N, hence integral tests give
  sum w_n <= A_N / [2(2N+Delta)],
  sum w_n**2 <= A_N**2 / [6(2N+Delta)**3].
The omitted splitting coefficient is bounded by one. No infinite-series
summation accelerator or imported CFT normalization is used in the bounds.
"""
from decimal import Decimal as D, Context, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction
from math import isqrt
from pathlib import Path
import json
import argparse

if not __debug__:
    raise SystemExit('Run without -O: assertions are part of the scientific checks')


class Intervals:
    def __init__(self, precision):
        self.down = Context(prec=precision, rounding=ROUND_FLOOR)
        self.up = Context(prec=precision, rounding=ROUND_CEILING)

    @staticmethod
    def exact(value):
        x = D(value)
        return x, x

    def add(self, a, b):
        return self.down.add(a[0], b[0]), self.up.add(a[1], b[1])

    def sub(self, a, b):
        return self.down.subtract(a[0], b[1]), self.up.subtract(a[1], b[0])

    def mul(self, a, b):
        assert a[0] >= 0 and b[0] >= 0
        return self.down.multiply(a[0], b[0]), self.up.multiply(a[1], b[1])

    def div(self, a, b):
        assert a[0] >= 0 and b[0] > 0
        return self.down.divide(a[0], b[1]), self.up.divide(a[1], b[0])

    def square(self, a):
        return self.mul(a, a)


def multiplicities(p, q, r, s, nmax):
    partitions = [1] + [0] * nmax
    for k in range(1, nmax + 1):
        for n in range(k, nmax + 1):
            partitions[n] += partitions[n - k]
    base = (q * r - p * s) ** 2
    # This exceeds both roots of the quadratic shift <= nmax.
    klim = isqrt(nmax // (p * q)) + 3
    terms = []
    for k in range(-klim, klim + 1):
        for sign, weight in [(-1, 1), (1, -1)]:
            numerator = (2 * p * q * k + q * r + sign * p * s) ** 2 - base
            assert numerator % (4 * p * q) == 0
            shift = numerator // (4 * p * q)
            if 0 <= shift <= nmax:
                terms.append((shift, weight))
    result = [sum(weight * partitions[n - shift]
                  for shift, weight in terms if shift <= n)
              for n in range(nmax + 1)]
    assert all(x >= 1 for x in result)
    return result


def enclose(delta_text, character, nmax=400, precision=60):
    delta = D(delta_text)
    if not 0 < delta <= 1 or nmax < 12:
        raise ValueError('Tail method requires 0 < Delta <= 1 and N >= 12')
    c = Intervals(precision)
    e = c.exact
    z, one = e(0), e(1)
    d = multiplicities(*character, nmax)
    A, s1, s2, sb, sbplain = one, z, z, z, z
    first = []
    for n in range(nmax + 1):
        if n:
            ratio = c.div(c.add(e(n - 1), e(delta)), e(n))
            A = c.mul(A, c.square(ratio))
        gap = c.add(e(2 * n), e(delta))
        w = c.div(A, c.square(gap))
        w2 = c.square(w)
        s1, s2 = c.add(s1, w), c.add(s2, w2)
        if n < 4:
            first.append(w)
        if d[n] >= 2:
            factor = c.sub(one, c.div(one, e(d[n] ** 2)))
            sb = c.add(sb, c.mul(factor, w2))
            sbplain = c.add(sbplain, w2)
    gap = c.add(e(2 * nmax), e(delta))
    t1 = c.div(A, c.mul(e(2), gap))[1]
    t2 = c.div(c.square(A), c.mul(e(6), c.mul(c.square(gap), gap)))[1]
    W1 = s1[0], c.up.add(s1[1], t1)
    W2 = s2[0], c.up.add(s2[1], t2)
    Bnum = sb[0], c.up.add(sb[1], t2)
    Bpnum = sbplain[0], c.up.add(sbplain[1], t2)
    result = {'Delta': delta_text, 'N': nmax, 'precision': precision,
              'd_first_12': d[:12], 'W1': W1, 'W2': W2,
              'K': c.div(W2, c.square(W1)),
              'B': c.div(Bnum, c.square(W1)),
              'B_plain': c.div(Bpnum, c.square(W1)),
              'W1_tail_upper': t1, 'W2_tail_upper': t2}
    three = c.add(c.add(first[0], first[1]), first[2])
    result['first_three_mass'] = c.div(three, W1)
    result['first_four_mass'] = c.div(c.add(three, first[3]), W1)
    n_ge_1_num = c.sub(W2, c.square(first[0]))
    result['all_n_ge_1_squared'] = c.div(n_ge_1_num, c.square(W1))
    return result


def free_fermion_ising(nmax):
    # Independent character oracle: distinct half-odd fermion modes,
    # odd fermion number, energy n+1/2 (all energies doubled).
    counts = [[0, 0] for _ in range(2 * nmax + 2)]
    counts[0][0] = 1
    for mode in range(1, 2 * nmax + 2, 2):
        for energy in range(2 * nmax + 1, mode - 1, -1):
            for parity in [0, 1]:
                counts[energy][parity] += counts[energy - mode][1 - parity]
    return [counts[2 * n + 1][1] for n in range(nmax + 1)]


def check_lemma():
    # Nontrivial grouping, saturation, leakage and an oscillating allocation.
    f = Fraction
    groups = [[f(1, 4), f(1, 4)], [f(1, 3), f(1, 6)], []]
    coarse = sum(sum(g) ** 2 for g in groups)
    fine = sum(x * x for g in groups for x in g)
    upper = sum((1 - f(1, len(g))) * sum(g) ** 2 for g in groups if g)
    assert 0 <= coarse - fine <= upper
    assert f(1, 2) ** 2 - 2 * f(1, 4) ** 2 == f(1, 2) ** 2 / 2
    # q=(1), pi=(1), support budget M=1, omitted mass eta=1/4.
    assert 1 - 2 * f(1, 4) <= f(3, 4) ** 2 + f(1, 4) ** 2 <= 1
    # H1 exactly true while fine concentration alternates between two values.
    assert sum(x*x for x in [f(1), f(0)]) != sum(x*x for x in [f(1,2), f(1,2)])


def check_reference_bound():
    """Exact rational tests of the two-error finite-size reference inequality."""
    f = Fraction
    cases = [
        # Equal splitting saturates the lower bound without matching errors.
        ([[f(1, 4), f(1, 4)], [f(1, 4), f(1, 4)]],
         [[0, 1], [0, 1]], [f(1, 2), f(1, 2)], [2, 2]),
        # Nonzero grouped mismatch and actual outside-support mass.
        ([[f(1, 4), f(1, 4)], [f(1, 3), f(1, 6)]],
         [[0, 1], [0]], [f(3, 5), f(2, 5)], [2, 1]),
    ]
    for groups, chosen, reference, budgets in cases:
        assert sum(sum(group) for group in groups) == 1
        assert sum(reference) == 1
        assert all(0 < len(indices) <= budget
                   for indices, budget in zip(chosen, budgets))
        q = [sum(group) for group in groups]
        outside = sum(sum(weight for i, weight in enumerate(group)
                          if i not in indices)
                      for group, indices in zip(groups, chosen))
        grouped_error = sum(abs(actual - target)
                            for actual, target in zip(q, reference))
        k_fine = sum(weight * weight for group in groups for weight in group)
        k_star = sum(weight * weight for weight in reference)
        budget = sum((1 - f(1, count)) * weight * weight
                     for weight, count in zip(reference, budgets))
        assert k_star - budget - 2 * (grouped_error + outside) <= k_fine
        assert k_fine <= k_star + 2 * grouped_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        help='Write a regenerated JSON receipt to this path')
    args = parser.parse_args()
    assert multiplicities(3, 4, 2, 1, 24) == free_fermion_ising(24)
    assert multiplicities(5, 6, 2, 1, 11) == [1,1,1,2,3,4,6,8,11,15,20,26]
    check_lemma()
    check_reference_bound()
    records = {}
    for name, delta, char, cap in [
            ('Ising', '1', (3,4,2,1), D('0.000168')),
            ('Potts', '0.8', (5,6,2,1), D('0.0000404'))]:
        runs = [enclose(delta, char, n, p) for n,p in [(200,60),(400,60),(400,90)]]
        for result in runs:
            assert result['B'][0] > 0
            assert result['B'][1] < cap
            if name == 'Ising':
                assert result['K'][0] * 3 < 2 < result['K'][1] * 3
            else:
                # Independent archived oracle, not used in computing intervals.
                assert result['K'][0] < D('0.8514956201179281748625366353') < result['K'][1]
        assert runs[1]['B'][1] - runs[1]['B'][0] < runs[0]['B'][1] - runs[0]['B'][0]
        assert max(runs[1]['B'][0],runs[2]['B'][0]) <= min(runs[1]['B'][1],runs[2]['B'][1])
        records[name] = runs
    for bad in ['0', '1.2']:
        try:
            enclose(bad, (3,4,2,1))
        except ValueError:
            pass
        else:
            raise AssertionError('invalid tail domain accepted')
    output = {'status':'PASS', 'method':'outward Decimal intervals and analytic integral tails',
              'scope':'conditional mathematical constants, not lattice matching',
              'checks':['Ising exact 2/3 enclosure','Potts archived oracle enclosure',
                        'Ising free-fermion character through n=24','tail cutoff refinement',
                        '60/90-digit overlap','splitting saturation/leakage/nonconvergence examples',
                        'invalid domain rejected'], 'results':records}
    serialized = json.dumps(output, indent=2, default=str) + '\n'
    expected = Path(__file__).with_name('expected_bound_enclosures.json')
    if json.loads(serialized) != json.loads(expected.read_text(encoding='utf-8')):
        raise AssertionError('computed intervals differ from the reviewed receipt')
    if args.output:
        if args.output.resolve() == expected.resolve():
            parser.error('the reviewed receipt cannot be overwritten')
        args.output.write_text(serialized, encoding='utf-8')
    for name in records:
        print(name, 'B enclosure:', *records[name][-1]['B'])
    print('PASS; reviewed receipt matched', expected.name)


if __name__ == '__main__':
    main()
