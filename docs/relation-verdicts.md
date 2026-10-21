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
each side is brought into its output unit, the object's inputs are
replaced as the relation says (`given`) or by the subject inputs that
feed them, and the difference must simplify to zero.

- **proven**: the difference simplifies to zero. This is a proof.
- **refuted**: SymPy does not conclude, and a point is found where the
  two sides differ. This is a counterexample.
- **unproven**: SymPy does not conclude, and no counterexample is found
  among random points. Nothing is guaranteed either way: equivalence of
  expressions with exponentials and logarithms is undecidable in general.
  Points where a side is not a real number (the logarithm of a negative
  value) are left aside; the verdict's `method` says how many samples
  remained.
- **unverified**: the claim cannot be checked as it stands, for a
  reason the verdict's `method` gives (different scales, below).

The proof compares the **expressions as written**. It means something
only if both formulations work in the same units: loading refuses an
equivalence whose outputs, or whose inputs and the subject inputs feeding
them (matched, or used by `given`), are in different units. Conversions
inside `given` are not supported: write both formulations in the same
units. An input of the object matched by its quantity kind (`Q` fed by
the subject's `P`, the only pressure) takes the subject's symbol. A
quantity equation gives its result in the units of its inputs, then
nomogram converts it into the output unit
(`Formulation.output_factor`); that factor is part of the expression
compared, so that a quantity equation and a numerical value equation
giving the same values are proven equivalent.

**Conventional scales.** The proof cannot convert a temperature between
scales either. With `scale = "convert"` (the default), which evaluates
each formulation on the scale it was fitted on, an equivalence whose
outputs, or whose inputs and the subject inputs feeding them, are on
different scales is **unverified**: the expressions agree as written,
but their evaluations do not. No scale and the reference scale of the
kind (ITS-90, Reference Salinity) count as the same, since both are
evaluated without conversion. To state that the expressions agree as
written, a relation says `scale = "ignore"`: the verdict can then be
**proven**, and its `method` names the scales ignored. Loading does not
refuse such a relation, so that the claim of a source stays recorded
with its verdict.

### A stated equivalence: ITU-R P.453, equations 2 and 6

P.453-14 writes the radio refractivity from the dry pressure P_d
(equation 2), then says: "Since P_d = P − e, equation (2) can be
rewritten as" equation 6, from the total pressure P. The catalog records
that claim (`itu_r_p453_total_pressure_form`, with
`given = { P_d = "P - e" }`), and `verify` proves it:

```
  77.6 (P - e)/T + 72 e/T + 3.75e5 e/T²      (equation 2, P_d = P - e)
- (77.6 P/T - 5.6 e/T + 3.75e5 e/T²)         (equation 6)
= (-77.6 + 72 + 5.6) e/T = 0
```

- **Exact rationals matter.** The coefficients become 388/5, 72 and
  28/5, whose sum is exactly zero. In binary floating point,
  `77.6 - 72` is `5.599999999999994`, not `5.6`: a comparison of floats
  would need a tolerance, and could not tell a proof from a near miss.
- **Units agree.** Both formulations take pressures in hPa and the
  temperature in K, so the expressions can be compared as written. The
  units inferred for the coefficients (`coefficient_units`) agree too:
  77.6, 72 and 5.6 are all in ppm K/hPa, which is why 77.6 − 72 = 5.6
  is a relation between quantities and not a numerical coincidence.

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
   successive zooms, down to 10⁻⁹ of the domain with one or two inputs
   (coarser beyond: 2 × 10⁻⁸ with three, 3 × 10⁻⁵ with four; the verdict
   gives the resolution reached).

The verdict compares the maximum found with the stated one: **reproduced**
(equal at the precision published), **held** (smaller) or **exceeded**
(larger). Its `method` gives the points per axis, the final resolution
and the number of evaluations.

A point where the deviation is not a finite number (a formulation
undefined there, or a value beyond the bounds of a scale conversion) is
not compared. When the grid has some, the `method` gives the share of
the grid compared: the verdict holds for that part of the domain only.
When it has nothing else, the verdict is **unverified**, without a
value.

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
