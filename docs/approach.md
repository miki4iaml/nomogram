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
  own, with an expression, its LaTeX, the validity domain carried
  through the function, and a record of its origin. The Magnus form
  gives back the classical dew point formula,
  t_d = B ln(e/C) / (A − ln(e/C)), with no hand-written formula;
- **when there is none** (the IAPWS equation, Goff-Gratch...), the
  inverse is solved numerically, and says so. This is not meant for
  production: it makes the comparison between a production
  approximation and the exact inverse of the reference possible.

Inverting a formulation over ice gives the frost point the same way.

A piecewise definition (over ice below 0 degC, over water above) is
inverted branch by branch, with a clear limit: **each branch must be
monotonic on its interval**. nomogram checks it on samples, solves each
branch, and takes the image of each interval as the condition of its
inverse branch (e < 6.112 hPa, then e ≥ 6.112 hPa); a gap between two
images, where no temperature gives the vapour pressure, has no inverse
(NaN). A branch that is not monotonic, has no closed form, or whose image
overlaps another's makes the whole inverse numerical. Most formulas of
the field meet the condition: saturation pressures, mixed-phase
fractions, layers of a standard atmosphere.
Every inverse is tested **both ways**, for all thirteen formulations
over water (f(f⁻¹(e)) = e, below), and the ten over ice through the
frost point (f⁻¹(f(t)) = t):

| Test | Tolerance | Why this tolerance |
|---|---|---|
| f⁻¹(f(t)) = t | 10⁻⁶ K | limited by the conversion between temperature scales (a fixed-point iteration); four orders of magnitude below the 0.05 K rounding of temperatures reported to a tenth of a degree |
| f(f⁻¹(e)) = e | 10⁻⁹, relative | the bisection runs to machine precision; nothing else intervenes |

The numerical inverse of IAPWS also reproduces its published table:
101 325 Pa gives back 373.1243 K.

## 7. What the tests guarantee, and what they do not

They guarantee that:

- every entry of the catalog loads and is consistent (declared
  identifiers, units applicable to their quantity kinds, references
  present, dimensional homogeneity of quantity equations, a unit for
  every coefficient, consistent with the expression);
- formulations reproduce the published values cited above;
- derived formulations invert their source, both ways;
- the Python examples of the README and of the guides run (those of the
  sea water guide give the values their comments state), and the README
  code is the code that drew its plot.

They do not guarantee that:

- a reference marked `to-confirm` is right: that is why it says so;
- a secondary source quoted its original correctly;
- a formulation is physically meaningful outside its domain;
- a numerical inverse is unique: the source is assumed monotonic over
  the interval searched.

## Contributing to this effort

Pointing to a source, confirming a `to-confirm` reference, or reporting
a discrepancy are among the most valuable contributions: see the
[ways to contribute](../.github/CONTRIBUTING.md#ways-to-contribute) and
the [catalog guide](catalog.md).
