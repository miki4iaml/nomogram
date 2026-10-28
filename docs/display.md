# Displaying formulas

Every formulation of the catalog can be displayed as a LaTeX equation, a
matplotlib label, a Markdown block, or a row of a Markdown table. All
derive from one LaTeX string, itself derived from the formula's
expression: nothing is written twice.

## In a notebook

A rendering left at the end of a cell displays itself (it provides
`_repr_markdown_`); so does a table:

```python
from nomogram.catalog import catalog
from nomogram.display import render, table

c = catalog()
magnus = c.formulations["sonntag1990_magnus"]
render(magnus)  # name, equation, meaning and unit of each symbol
table(c.formulations_of("SaturationVapourPressureOverIce"))
```

nomogram does not import IPython: the Markdown string works anywhere,
for instance with `IPython.display.display_markdown(text, raw=True)`,
on GitHub, or in Sphinx and MkDocs pages. A formulation alone also
displays its equation, through `_repr_latex_`.

## The pieces

```python
rendering = render(magnus)
rendering.latex  # the equation, without dollar signs
rendering.mathtext  # the same between dollar signs, for matplotlib
rendering.markdown  # name, equation and legend of the symbols
magnus.latex()  # shortcut for render(magnus).latex
```

For a plot, `symbol` labels a variable, in a notation if wanted:

```python
from nomogram.display import symbol

wmo = c.notations["wmo"]
label = symbol(magnus.output, wmo)  # "$e_{\mathrm{w}}$/hPa"
```

`nomogram.plot.plot_values` labels its y axis with the name of the
output kind, this symbol (in the notation given) and the unit, in the
style below.

### Axis labels

Axis labels follow the option `axis_labels`, set like the others
(`display_options(axis_labels="simple")`, or for one call):

| `axis_labels` | Celsius temperature on ITS-90 | Saturation vapour pressure |
|---|---|---|
| `"si"` (default) | Celsius temperature t₉₀/°C | e_w/hPa |
| `"explicit"` | Celsius temperature - t [°C] {ITS-90} | e_w [hPa] |
| `"simple"` | Celsius temperature t [°C] | e_w [hPa] |

- `"si"` writes the quotient of the quantity by its unit, as the SI
  Brochure (9th edition, 5.4.1) labels table columns and graph axes, so
  that ticks are plain numbers; a compound unit goes in parentheses
  (`ρ_v/(g/m³)`), a number has no unit. A unit is never qualified by
  information on the quantity (5.4.2): the conventional scale of the
  values marks the symbol, as the ITS-90 writes t₉₀ and T₉₀.
- `"explicit"` gives the name, the symbol, the unit in brackets and the
  short name of the scale in braces.
- `"simple"` gives the name, the symbol and the unit in brackets, without
  scale: enough for a technical note where scales would only add to the
  reader's burden.

The scale shown is the reference scale of the quantity kind, on which
nomogram takes inputs and returns results (read from the bundled
catalog). A comparison made with `scale="ignore"` shows none: each
formulation took the values as given, on the scale it was fitted on.
The mark joins a subscript of the symbol, braced or not (`T_d` gives
T_d,90). A temperature axis follows the values plotted: in °C a Celsius
temperature t, in K or °R a thermodynamic temperature T, in °F simply a
temperature; another temperature point takes the letter of its unit too
(a dew point t_d in °C, T_d in K). Names are in sentence case, as the SI and ISO 80000 write
them ("Celsius temperature"); units take the catalog's symbols (a
temperature difference in °C, never Δ°C).

```python
from nomogram.display import axis_label, display_options, reference_scale

its90 = reference_scale("CelsiusTemperature")
axis_label("Celsius temperature", "t", "°C", scale=its90)
# "Celsius temperature $t_{90}$/°C"
with display_options(axis_labels="simple"):
    simple = axis_label("Celsius temperature", "t", "°C", scale=its90)
# "Celsius temperature $t$ [°C]"
```

The Markdown legend of a single formulation gives the unit of every
coefficient and where it comes from: from the source, added by nomogram
when the entry was written, or inferred by nomogram from the expression
(for the Magnus form, B = 243.12 °C and C = 6.112 hPa, both inferred, so
that a reader comparing with the source knows they are nomogram's). For a formulation with fixed units, it also
gives the units its coefficients hold for. Tables and plot labels never
show where units come from.

### How much plot labels say

Two options set how much a plot says, from a figure that needs room for
its curves to one that must stand alone: `axis_detail` for both axes,
`legend_detail` for the legend. Each is `"short"`, `"standard"` (default)
or `"full"`, independently of the other:

| Detail | x axis (`axis_detail`) | Deviation axis (`axis_detail`) | Legend entry (`legend_detail`) |
|---|---|---|---|
| `"short"` | t₉₀/°C | δ/% | Bechtold (2015), eq. 54 |
| `"standard"` (default) | Celsius temperature t₉₀/°C | Relative deviation from IAPWS (1992) δ/% | Magnus form in kelvins (Bechtold 2015) |
| `"full"` | the same, then *on the International Temperature Scale of 1990 (ITS-90)* | the same, then the label of the reference | the label, then *Bechtold (2015), eq. 54* |

- A short entry is the first citation of the formulation: its authors
  (a body keeps its whole name, *IOC, SCOR and IAPSO*), the year and the
  equation when the catalog records it. A formulation keeps its label
  when it cites nothing, when its first source is not in the bundled
  catalog (a personal one), or when another formulation of the plot
  would share the entry (Buck (1981) gives two). A legend of more than
  ten short entries, none longer than 30 characters, takes two columns.
- A full label takes a second line: the scale of an axis spelled out,
  the full label of the reference, the first citation of a formulation.
  It suits a plot of a few curves.
- An axis keeps its name, even short, when it has no symbol.

```python
import numpy as np

import nomogram as nomo
from nomogram.units import Q_

table = nomo.comparison.compare(
    c.formulations_of("SaturationVapourPressureOverWater"),
    c.formulations["iapws_sr1_86"],
    {"ThermodynamicTemperature": Q_(np.linspace(-60, 110, 341), "degC")},
)
with display_options(axis_detail="full", legend_detail="short"):
    ax = nomo.plot.plot_deviations(table)  # extra viz
```

### Scales of the plots

`plot_deviations` draws off scale a curve whose largest deviation
exceeds those of all the others by more than three times: the y axis
holds the others, the curve still leaves through it, and its legend
entry says how far it goes (*off scale, up to 26.7 %*). The largest
deviations, sorted, are split at their largest such jump in the upper
half, so at least half of the curves stay on scale. In the figure of the
README, the two forms with a constant latent heat reach 27 %, and the
others stay within 4.3 %. `off_scale=False` holds every curve. Keyword
arguments set properties of the axes once the curves are drawn
(`Axes.set` of matplotlib): `ylim=(-1, 1)` zooms in, and every curve
leaving these limits is off scale, its legend entry saying how far it
goes; `xlim=(0, 40)` narrows the x axis, and the y axis then holds what
the curves show within it; `title` and the others likewise. With the
display option `off_scale_notes=False`, legend entries say nothing of
the curves off scale, which still leave the axis. On axes
given through `ax`, which may hold curves of one's own, the limits are
left as they are unless `off_scale=True`; `plot_values` likewise leaves
their scale unless `yscale` names one.

`plot_values` plots on a logarithmic scale values that are all positive
and span more than two decades, a saturation vapour pressure from −60 to
110 °C for instance; `yscale="linear"` or `"log"` chooses. A deviation
has a sign, and points of an interval scale (temperatures in °C) have no
ratio: both stay on a linear scale. The relative deviation of values in
°C is computed in kelvins, where a ratio means something.

### Signature

The figures that `plot_values` and `plot_deviations` create take the
tight layout of matplotlib, which makes room for labels of two lines
whatever size the figure is given later, and are signed with the logo,
at the right edge, on the line of the x-axis label: the signature
follows that label and stays below the tick labels whatever the layout.
A figure saved with `bbox_inches="tight"` keeps it whole. `signature=False` leaves it out, and a figure given through
`ax` is never signed, so that a plot keeps its place in a layout of one's
own. `sign` signs any figure, and returns the signature: an artist, which
`remove()` takes off. Its colours follow the background of the figure,
light or dark, and it changes no setting of matplotlib.

```python
import matplotlib.pyplot as plt

from nomogram.plot import sign

figure, ax = plt.subplots()
mark = sign(figure)  # bottom right corner; sign(figure, axes=ax) follows its x label
mark.remove()  # unsigned again
```

### Option sets

An option set is a `DisplayOptions`, one of nomogram's presets or one of
one's own, given to `display_options` for a block, with fields to change
if need be. `DisplayOptions.DOCUMENTATION` is the set of the figures of
nomogram's documentation, the README's included: full axes, short legend
entries, and curves off scale without a note (`off_scale_notes=False`),
so that a figure stands alone without crowding.

```python
from nomogram.display import DisplayOptions

with display_options(DisplayOptions.DOCUMENTATION, legend_detail="standard"):
    ax = nomo.plot.plot_deviations(table, xlim=(0, 40))
```

The options cover what nomogram decides or adds to a figure: labels,
legend entries, curves off scale. The rest stays with matplotlib and the
caller. The visual style (colours, fonts, sizes, grid) follows
matplotlib's style sheets and `rcParams`, which nomogram leaves as they
are; the limits, the title and the other properties of the axes are
keyword arguments of the call; the axes returned take everything else,
the place of the legend included, which depends too much on each figure
to be chosen for it.

## Typography

By default:

- every product shows a multiplication sign, ×: a juxtaposition such as
  RH is then never a product R × H, whether or not the reader knows the
  conventions. The SI Brochure (9th edition, section 5.4.6) accepts ab,
  a b, a · b and a × b between quantity symbols, but only × between
  numbers, and × or parentheses between values of quantities: × suits
  every case. A power of ten, like any product of two numbers, is
  always written with ×, whatever the option chosen;
- descriptive subscripts and abbreviations are upright, as ISO 80000-2
  recommends (e_s is written with an upright s, RH upright); numeric
  indices and Greek letters keep their usual rendering, and a notation
  of the catalog always takes priority;
- the decimal separator is a period;
- coefficients appear as symbols, listed with their values below the
  equation.

These are options, named after the SymPy printer settings they are
passed to where one exists (`mul_symbol`, `decimal_separator`), plus
`upright` and `values`. They can be changed at three levels, highest
priority first:

```python
from nomogram.display import DisplayOptions, display_options

render(magnus, mul_symbol="dot")  # 1. for one call
compact = DisplayOptions(mul_symbol=None, upright=False)
render(magnus, options=compact)  # 2. a reusable set
with display_options(decimal_separator="comma", values=True):
    french = render(magnus).latex  # 3. for a block
```

`DisplayOptions.SYMPY` gives SymPy's own rendering, numbers still
joined by ×. The block form
works as `numpy.printoptions` does: it holds its options in a context
variable, so it applies to the current thread or task only and is
undone when the block ends. There is no global setting.

## Which LaTeX

MathJax (JupyterLab, GitHub), KaTeX (VS Code) and matplotlib's mathtext
do not accept exactly the same commands. nomogram only emits a small
subset common to the three, `nomogram.expression.LATEX_COMMANDS`, checked
against their documentation; the tests check every formula of the
catalog against it, in every notation, and parse each one with mathtext.
Notation symbols written in the catalog are checked against the same
subset when it is loaded.

The same LaTeX is accepted by the three engines; the result is not
identical to the pixel, since fonts differ (`\epsilon`, for instance, is
drawn ϵ or ε depending on the font).
