# What a verdict on a stated relation guarantees

This page is only about the relations that sources state between two
formulations (`[relations]` in the catalog, see the
[catalog guide](catalog.md#relations)), and the verdicts
`nomogram.relations.verify` gives on them. It says what each verdict
guarantees, and where it stops. The other checks of nomogram (units,
dimensions, the catalog itself) are described in
[How nomogram earns trust](approach.md).

## Equivalences: proved, or not

An equivalence is proved with SymPy: coefficients become exact rationals,
the object's inputs are replaced as the relation says, and the difference
must simplify to zero.

- **proven**: the difference simplifies to zero. This is a proof.
- **refuted**: SymPy does not conclude, and a point is found where the
  two sides differ. This is a counterexample.
- **unproven**: SymPy does not conclude, and no counterexample is found
  among random points. Nothing is guaranteed either way: equivalence of
  expressions with exponentials and logarithms is undecidable in general.

## Approximations: checked on points, never proved

An approximation states a maximum relative deviation over a domain. It
is checked numerically:

1. a regular grid over the domain, with a budget of 200 000 evaluations,
   that is `per_axis(d)` points per axis for `d` input variables;
2. a local refinement around the five best points of the grid, by
   successive zooms, down to 10⁻⁹ of the domain.

The verdict compares the maximum found with the stated one: **reproduced**
(equal at the precision published), **held** (smaller) or **exceeded**
(larger). Its `method` gives the points per axis, the final resolution
and the number of evaluations.

| Input variables | Points per axis | Step of the grid, in fraction of the domain |
|---|---|---|
| 1 | 9 001 | 1.1 × 10⁻⁴ |
| 2 | 447 | 2.2 × 10⁻³ |
| 3 | 58 | 1.8 × 10⁻² |
| 4 | 21 | 5 × 10⁻² |
| 5 | 11 | 0.1 |
| 6 | 7 | 0.17 |

**What to rely on**

- With **one or two variables, and three in most cases**, the grid is
  fine enough and the refinement finds the maximum at the resolution
  given in the verdict. The corners of the domain, where maxima often
  lie, are always on the grid.
- With **more variables**, the grid becomes coarse: a narrow maximum
  falling between its points may be missed, and the refinement, which
  only climbs from the best points of the grid, may settle on a lower
  one. The verdict is then an **estimate, given as an aid to the user**;
  nomogram does not vouch for it.
- In every case the verdict is a check on points: an approximation is
  never *proven*. A guaranteed bound would require interval arithmetic
  over the domain, which nomogram does not implement.

## What is never verified

Deviations nomogram computes without a source
(`nomogram.comparison.compare`) are observations, not claims: they are
not relations and carry no verdict.
