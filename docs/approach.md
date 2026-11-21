# How nomogram earns trust

nomogram gathers alternative formulations of the same physical quantity
and lets you compare, chain and plot them. That is only useful if you
can trust what is in the catalog without rereading every line of code.
This page describes the approach: what is checked, how, against what,
and where the limits are.

The running example is the **saturation vapour pressure of water**, and
the humidity quantities derived from it. It is a classic: a dozen
formulations in daily use, a reference equation, decades of
approximations, and as many traps (units, temperature scales, ambiguous
terms, misattributions).

## 1. Sources are read, not assumed

A formulation is written once; each source that gives it is a
**citation**, which records what that source states: its equation
number, its symbols, the units and the validity domain it gives, the
accuracy it claims, the temperature scale. A detail never floats free of
its source. Every reference carries a status:

- **`verified`**: the detail was read in the source itself (an equation,
  a coefficient, a validity range, a table);
- **`to-confirm`**: anything else, with a note saying what remains to
  check.

A formula quoted by a review is entered as quoted, and the review is
cited too. For the saturation vapour pressure, the IAPWS release on
saturation properties (SR1-86, 1992) was read in full: its equation, its
coefficients, its range (273.16 K to 647.096 K) and its verification
table. Several Magnus forms were taken from the report of Alduchov and
Eskridge (1996), others from Vömel's review of saturation vapour
pressure formulations; their original papers stay `to-confirm` until
read.

**Disagreements are recorded, not smoothed over.** Reading the sources
side by side brought out several of them, now noted in the catalog:

- the constant of Tetens' formula differs between secondary sources;
- the same formulation is dated Sonntag 1990 by one source and Sonntag
  1994 by another;
- the triple point form of the Goff-Gratch equation is called Goff
  (1957) by one source and GG46 by another, which also writes `ln` where
  the numbers require a decimal logarithm;
- "absolute humidity" means a mass per volume of moist air in
  meteorology, and a mass per mass of dry air in engineering: the term
  is recorded as ambiguous, pointing to two unambiguous quantity kinds
  (see [rosetta.md](rosetta.md)).

## 2. Values are checked against published values

A formula is never tested against itself. Tests compare it with values
published by an independent source:

- the IAPWS equation reproduces the verification table of its release:
  611.657 Pa at 273.16 K and 101 325 Pa at 373.1243 K, to the six
  significant figures given;
- at usual temperatures it gives 23.392 hPa at 20 °C and 73.851 hPa at
  40 °C, and 1014.18 hPa at 100 °C (not 1013.25: on ITS-90, water boils
  at 99.974 °C under standard pressure);
- the deviations of the Magnus forms from the reference match those
  reported in the literature: about -0.28 % at 20 °C for Sonntag's
  coefficients, 2 to 3 % too high at 100 °C, outside their range;
- the maximum relative errors that Alduchov and Eskridge (1996, Table
  III) give for five Magnus forms against GG46 and SO90 are recorded as
  relations and verified: ten of twelve are reproduced to the third
  decimal, at the temperature they give, once the formulas are compared
  as given (each on its own temperature scale), as the authors did, and
  GG46 taken in its triple-point form; for Sonntag's Magnus
  coefficients (SA90) we find 0.610 % against GG46 where the table gives
  0.597 %, and 0.315 % against SO90 where it gives 0.328 %, with the same
  coefficients as their Table II: the disagreement is recorded;
- over ice, the IAPWS sublimation equation (R14-08, 2011) reproduces
  the table of its release (8.94735 × 10⁻⁶ MPa at 230 K) and meets the
  equation over water at the triple point; the formulations quoted by
  Vömel keep the deviations he describes, from Goff-Gratch, 0.15 to
  0.27 % below, to Murray's Magnus-Tetens form, 11 % too low at -80 °C;
- the saturation mixing ratio, computed from the IAPWS equation with
  the ideal gas formula, is compared with ASHRAE's table: it stays 0.4 to
  0.6 % below, always on the same side. The tolerance is stated, and so
  is the likely reason (the table accounts for non-ideal moist air):
  a systematic gap is documented, not hidden by a loose tolerance.

## 3. Formulations are compared with a reference

`compare` evaluates every formulation of a quantity on the same inputs
and gives its relative deviation from a reference, in one vectorised
pass. The plot of the README is exactly that. It shows at a glance which
formulations agree, where they drift, and where they stop.

When another implementation of a formulation exists, its values are
recorded once as a **cross-check** (implementation, version, date,
points), and the tests compute them again: ITU-R P.453 against ITU-Rpy
agrees on every point tried, to the last digit, or within 10⁻¹² when the
value went through (n − 1) × 10⁶ (see the
[catalog guide](catalog.md#cross-checks-against-other-implementations)).

## 4. Units and temperature scales are explicit

- **Units** come from QUDT and are checked against pint: each unit's
  dimension, multiplier and offset are tested.
- **Points and differences**: a Celsius temperature is a point on an
  interval scale; a temperature difference is not. Adding two
  temperature points is refused.
- **Formulas with fixed units**: the coefficients of an empirical fit
  only hold in its units. They are never converted; the inputs are,
  before evaluation (a Fahrenheit point becomes a Celsius point).
- **Units of coefficients**: sources often give coefficients as bare
  numbers. Dimensional analysis of the expression gives them their unit
  (the B of the Magnus form is a temperature difference in °C, its C a
  pressure in hPa; the a₂ of Sonntag's formulation is in K⁻¹). Every
  coefficient of the catalog has one, declared or inferred, and every
  declared unit is checked against the expression. Two methods find
  these units, local propagation through the expression tree and linear
  algebra on the exponents of the dimensions; the tests check that they
  agree on the whole catalog and on formulas generated at random.
- **Temperature scales**: a formula fitted on IPTS-68 expects IPTS-68
  temperatures. Between 0 and 100 °C the two scales differ by up to
  0.026 K, which shifts the saturation vapour pressure by up to about
  0.09 %, as much as the deviations between good formulations. Each
  formulation records its scale and how that is known: stated by the
  source, inferred from the publication date only (weak: ITS-90 itself
  took years to be applied), or inferred from numbers. Inputs and
  results are on ITS-90; conversions are done by default. Temperature
  scales were the first conventional reference scales (VIM 1.29) of the
  catalog; the same mechanism serves salinity (see
  [sea-water.md](sea-water.md)) and will serve other quantities defined
  by agreement (heights, time scales...).

The last category came from the data itself: the Hyland and Wexler
coefficients published in 1983 (the IPTS-68 era), as given today by
ASHRAE, agree with IAPWS within 0.022 % without conversion and drift to
0.09 % with the IPTS-68 conversion. They behave as ITS-90, and are
recorded so, with the evidence.

## 5. Validity domains are objective

nomogram records only objective domains: **physical**, or **stated** by
the author or the cited publication, with the criterion behind it (for
instance a maximum deviation of 0.384 % from three reference
formulations between -40 and 50 °C, for Alduchov and Eskridge). A
domain that suits a given application is the user's business.

Outside its domain, a formulation returns **NaN by default**, which
leaves gaps in plots instead of silently extrapolating. It can also
warn, raise, or compute anyway (for comparisons): this is a parameter,
never a hidden choice.

## 6. Derived formulations are checked both ways

nomogram derives new formulations by symbolic computation. Inverting
each saturation vapour pressure formulation e_s = f(T) gives the dew
point t_d = f⁻¹(e):

- **when SymPy finds a closed form**, it becomes a formulation of its
  own, with an expression, its LaTeX, the validity domains carried over,
  and a record of its origin: the interval of the temperature becomes
  that of the dew point, the inverse's output, and its image through
  the function that of the vapour pressure, its input. The Magnus form
  gives back the classical dew point formula,
  t_d = B ln(e/C) / (A − ln(e/C)), with no hand-written formula;
- **when there is none** (the IAPWS equation, Goff-Gratch...), the
  inverse is solved numerically, and says so. It searches the validity
  domain a source states; when none does, or the domain is open on one
  side, nomogram does not choose the interval, the caller gives it
  (`search=`). This is not meant for production: it makes the
  comparison between a production approximation and the exact inverse
  of the reference possible.

Inverting a formulation over ice gives the frost point the same way.

A numerical inverse is unique only if its source is **monotonic** over
the interval searched, and nomogram **proves** it before solving, by
interval arithmetic (mpmath's `iv`, whose bounds are rigorous): the
derivative, bounded on sub-intervals halved until its bounds exclude
zero, keeps one sign, and the function stays finite there (no pole).
Where no proof concludes (a derivative that vanishes at a point, as
that of x³ at 0), it checks samples: the grid of the solver of implicit
equations, geometric near each end and around zero, and 2001 evenly
spaced points. A derivative that changes sign, proven or on the
samples, refuses the inverse; the verdict goes with the inverse
(`NumericalInverse.monotonicity`), and the bisection follows the
direction proven. The junctions of a piecewise definition are measured
too: the published coefficients of ITU-R P.835 join the layers of its
standard atmosphere to about 10⁻⁵ (226.3206 hPa at the top of the first,
226.3226 hPa at the bottom of the second), so its pressure steps back by
9 × 10⁻⁶ of its value where it should keep decreasing. A pressure within
the step has two altitudes, and how far apart depends on the slope: the
step divided by the slope of the branches there, 5.6 cm of altitude at
11 km, 10.3 cm at 71 km, where the pressure falls more slowly for the
same relative step. nomogram gives both, the step relative to the value
and this width on the input (`steps`, `widths`). The inverse accepts a
step up to 10⁻⁴ of the value by default (`STEP_BACK_TOLERANCE`); the
caller may set instead the width accepted on the solved variable, in its
unit (`step_back=`, an altitude within 10 cm, say).

The same proof is open to the caller:
`nomogram.monotonicity.monotonicity(formulation, input, over)` says
whether a formulation is monotonic in one input over a box the caller
chooses: proven, refuted (with a counterexample), or unproven, with its
method. KEYPS, below, is proven increasing in ζ over ζ ≤ 0. It is a
property nomogram computes, with its box, never a validity domain.
SymPy's `is_monotonic` does not serve: read in SymPy 1.14, it answers
no for x³ over [−1, 1], and yes for a function that jumps down.

A piecewise definition (over ice below 0 degC, over water above) is
inverted branch by branch, with a clear limit: **each branch must be
strictly monotonic on its interval**. nomogram proves it, or checks it
on samples where no proof concludes, solves each branch, and takes the image of each interval as the
condition of its inverse branch (e < 6.112 hPa, then e ≥ 6.112 hPa); a
gap between two images, where no temperature gives the vapour pressure,
has no inverse (NaN). A branch that is not strictly monotonic, has no
closed form, or whose image overlaps another's makes the whole inverse
numerical. Most formulas of the field meet the condition: saturation
pressures, layers of a standard atmosphere. A constant branch does not:
the 0 and 1 of a mixed-phase fraction are each reached on a whole
interval of temperatures, and the numerical inverse returns one end of
it, within the interval searched.
Every inverse is tested **both ways**, for every formulation over water
(f(f⁻¹(e)) = e, below), and every formulation over ice through the
frost point (f⁻¹(f(t)) = t):

| Test | Tolerance | Why this tolerance |
|---|---|---|
| f⁻¹(f(t)) = t | 10⁻⁶ K | limited by the conversion between temperature scales (a fixed-point iteration); four orders of magnitude below the 0.05 K rounding of temperatures reported to a tenth of a degree |
| f(f⁻¹(e)) = e | 10⁻⁹, relative | the bisection runs to machine precision; nothing else intervenes |

The numerical inverse of IAPWS also reproduces its published table:
101 325 Pa gives back 373.1243 K.

Some sources give no explicit formula at all, only an equation its
output solves (VIM 2.48, note 1: h(Y, X₁, …, Xₙ) = 0). The KEYPS formula
of Businger et al. (1971), φm⁴ − γ₁ ζ φm³ = 1, is written as printed,
`==` between its members, and solved for φm, never rearranged by hand.
nomogram does not choose between roots: it seeks the root where the
physical domains on the output and the bounds of its kind allow (φm ≥ 0,
the shear of a wind increasing with height, rules out the negative
root), and returns it only if it is the one root there. Otherwise, no
root, several, or a residual undefined around one, the value is NaN and
a warning says which. Each bracket of a root is narrowed to adjacent
floats by Chandrupatla's method (1997: inverse quadratic interpolation
where it is safe, halving otherwise). A root is kept where the residual
falls, from the ends of its bracket, to a millionth of its size there:
across
a jump between pieces it does not fall, at a pole it grows. Solved this way, KEYPS is tested against its form
explicit in ζ, ζ = (φm⁴ − 1)/(γ₁ φm³), to 10⁻¹², against the slope
γ₁/4 = 2.25 at neutral the source gives (p. 184), and against the
explicit formula it compares with (equation 8).

Some sources iterate several coupled formulas until they agree: the
surface layer of COARE 3.6 takes the friction velocity from the Obukhov
length, the length from the scales, the scales from the roughness
lengths, and loops ten times. nomogram writes such a model as a system
(`nomogram.systems.System`), a multivariate measurement model in the
words of JCGM 102:2011 (3.8): equations, each given by a formulation of
the catalog, listed in the order the source computes them; the
variables read before they are given are its unknowns, the others are
computed from them. It solves them by Newton's method, damped by a line
search, with an exact Jacobian: SymPy derives each formulation, and the
chain rule assembles the derivatives through units and conventional
scales, so that a linear system is solved in one step. Newton's method
finds a solution near its start, the first guess of the source: nomogram
says converged, never unique; the unknown of an implicit equation stays
where its root is sought, as for the formulation alone. Without
convergence, or with a singular Jacobian, the values are NaN and a
warning counts them; inputs outside a domain are not solved. The passes the
source iterates remain available (`method="fixed-point"`), to compare
with its own procedure.

## 7. What the tests guarantee, and what they do not

They guarantee that:

- every entry of the catalog loads and is consistent (declared
  identifiers, units applicable to their quantity kinds, references
  present, dimensional homogeneity of quantity equations, a unit for
  every coefficient, consistent with the expression);
- formulations reproduce the published values cited above;
- derived formulations invert their source, both ways;
- a numerical inverse is solved over an interval where its source is
  monotonic, proven, or found so on samples;
- the root of an implicit equation is the one root in the interval
  searched, or NaN with a warning;
- the solution of a system satisfies each of its equations to 10⁻¹²,
  relative to the size of its terms (10⁻⁸ where the rounding of terms
  that nearly cancel stops Newton's method), or is NaN with a warning;
- the Python examples of the README and of the guides run (those of the
  sea water guide give the values their comments state), and the README
  code is the code that drew its plot.

They do not guarantee that:

- a reference marked `to-confirm` is right: that is why it says so;
- a secondary source quoted its original correctly;
- a formulation is physically meaningful outside its domain;
- a numerical inverse is unique where the monotonicity of its source was
  found on samples only: between two samples, a turn goes unseen;
- the solution of a system is its only one: Newton's method finds the
  one near its start;
- every root of an implicit equation is seen: two roots closer than the
  step of the search grid, or a double root, where the residual does not
  change sign, escape it; and a jump between pieces smaller than a
  millionth of the residual's change around it is taken for a root.

## Contributing to this effort

Pointing to a source, confirming a `to-confirm` reference, or reporting
a discrepancy are among the most valuable contributions: see the
[ways to contribute](../.github/CONTRIBUTING.md#ways-to-contribute) and
the [catalog guide](catalog.md).
