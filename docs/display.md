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
catalog). A temperature axis follows the values plotted: in °C a Celsius
temperature t, in K or °R a thermodynamic temperature T, in °F simply a
temperature. Names are in sentence case, as the SI and ISO 80000 write
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

## Typography

By default:

- every product shows a multiplication sign, ×: a juxtaposition such as
  RH is then never a product R × H, whether or not the reader knows the
  conventions. The SI Brochure (9th edition, section 5.4.6) accepts ab,
  a b, a · b and a × b between quantity symbols, but only × between
  numbers, and × or parentheses between values of quantities: × suits
  every case. A power of ten is always written with ×, whatever the
  option chosen;
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

`DisplayOptions.SYMPY` gives SymPy's own rendering. The block form
works as `numpy.printoptions` does: it holds its options in a context
variable, so it applies to the current thread or task only and is
undone when the block ends. There is no global setting.

## Which LaTeX

MathJax (JupyterLab), KaTeX (VS Code, GitHub) and matplotlib's mathtext
do not accept exactly the same commands. nomogram only emits a small
subset common to the three, `nomogram.expression.LATEX_COMMANDS`, checked
against their documentation; the tests check every formula of the
catalog against it, in every notation, and parse each one with mathtext.
Notation symbols written in the catalog are checked against the same
subset when it is loaded.

The same LaTeX is accepted by the three engines; the result is not
identical to the pixel, since fonts differ (`\epsilon`, for instance, is
drawn ϵ or ε depending on the font).
