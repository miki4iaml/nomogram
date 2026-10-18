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

### What SymPy settles, and what it does not

These pairs were run through `verify` (inputs are real numbers, not
assumed positive; without stated bounds, the counterexample is looked
for between 0.5 and 2):

| Pair | Verdict | Why |
|---|---|---|
| `A * x / (B + x)` and `A - A * B / (B + x)` | proven | rational algebra: `simplify` reduces the difference to zero |
| `(x + 1) ** 2` and `x ** 2 + 2 * x + 1` | proven | polynomial expansion |
| `exp(x + y)` and `exp(x) * exp(y)` | proven | holds for every real x and y |
| `log10(x * y)` and `log10(x) + log10(y)` | unproven | true for positive x and y only; SymPy does not assume positivity, and no counterexample exists among positive samples |
| `(x * y) ** 0.5` and `x ** 0.5 * y ** 0.5` | unproven | same reason: true when x and y are not negative |
| `sqrt(x ** 2)` and `x` | unproven | SymPy keeps `Abs(x) - x`; positive samples cannot tell |
| the same, with `bounds = { x = [-2.0, -0.5] }` | refuted | on negative values, `Abs(x) - x` is not zero |
| `x + 0.001 * x ** 2` and `x` | refuted | an approximation is not an equivalence: the difference `x**2/1000` is found |
| `exp(ln(x))` and `x` | not a relation | SymPy writes both as `x`: the second formulation is refused as identical to the first when the catalog is loaded |

Two lessons. An **unproven** verdict does not mean false, nor true: the
logarithm of a product is right for the positive quantities of physics,
the square root of a square is wrong for negative ones. And stating the
**bounds** of the inputs, when the source gives them, lets the search for
a counterexample look where the formula is used.

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

## Recorded verdicts

Verifying a relation takes time (a proof, or a grid of thousands of
points). The verdicts on the relations of the bundled catalog are kept in
a registry, `src/nomogram/data/catalog/verifications.json`, generated and
never edited by hand:

- each verdict is filed under a **fingerprint** (SHA-256) of everything
  it depends on: the relation as written, the signatures of its two
  formulations (expression, coefficients, kinds and units), the
  conventional scales of their variables, the budget of the check and
  the version of the method (`VERIFIER`);
- `nomogram.relations.verdict` reads the registry when the fingerprint
  matches, and computes the verdict otherwise; any change to a relation
  or to one of its formulations changes the fingerprint, so a recorded
  verdict never outlives what it was computed for;
- `uv run python -m nomogram.catalog verify --record` computes only what
  is missing, reuses the rest and drops entries matching no relation: a
  contributor checks locally the new relations alone;
- the continuous integration recomputes every verdict and compares it
  with the registry: it has the last word.

A personal catalog can keep its own registry
(`nomogram.relations.record(catalog, path)`), or none: verdicts are then
computed on demand.

## What is never verified

Deviations nomogram computes without a source
(`nomogram.comparison.compare`) are observations, not claims: they are
not relations and carry no verdict.
