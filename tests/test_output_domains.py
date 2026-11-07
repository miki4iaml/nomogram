# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Validity domains that bound the output, and domains with an open end.

The test formulations compute a pressure, a kind without bounds of its
own, so that only the domains written here bound their values.
"""

import math

import numpy as np
import pytest

from nomogram.catalog import CatalogError, _reaches_domain, load_catalog
from nomogram.display import table
from nomogram.inversion import NumericalInverse, invert
from nomogram.model import Formulation, OutOfDomainError, ValidityWarning, Variable
from nomogram.relations import _stated_extent
from nomogram.units import Q_

SOURCE = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[references.other]
authors = "Other, O."
title = "Another title"
status = "verified"
"""

HEAD = """
[formulations.{key}]
label = "{key}"
expression = "{expression}"
fixed_units = true
output = {{ identifier = "{output}", kind = "Pressure", unit = "HectoPA", description = "out" }}
inputs = [{{ identifier = "{input}", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }}]
coefficients = {{ a = {a} }}
"""


def formulation(
    key: str = "f",
    expression: str = "a * t",
    output: str = "e",
    input: str = "t",
    a: float = 2.0,
) -> str:
    return HEAD.format(key=key, expression=expression, output=output, input=input, a=a)


def citation(key: str, reference: str, bounds: str, criterion: bool = True) -> str:
    text = f"""
[[formulations.{key}.citations]]
reference = "{reference}"

[[formulations.{key}.citations.domains]]
bounds = {{ {bounds} }}
"""
    if criterion:
        text += 'criterion = "What the source states."\n'
    return text


def physical(key: str, bounds: str) -> str:
    return f"""
[[formulations.{key}.domains]]
bounds = {{ {bounds} }}
criterion = "What physics allows."
"""


def load(*documents: str) -> dict[str, Formulation]:
    return dict(load_catalog([SOURCE + "".join(documents)]).formulations)


def values(f: Formulation | NumericalInverse, **inputs: object) -> np.ndarray:
    return np.asarray(f.evaluate(**inputs).magnitude)  # type: ignore[arg-type]


T = Q_(np.array([-1.0, 2.0, 4.0, 6.0]), "degC")  # a t: -2, 4, 8, 12 hPa


def test_a_stated_bound_on_the_output_masks_the_results_beyond() -> None:
    f = load(formulation(), citation("f", "src", "e = [0, 10]"))["f"]
    assert np.isnan(values(f, t=T)).tolist() == [True, False, False, True]
    with pytest.warns(ValidityWarning, match="2 value"):
        f.evaluate(t=T, outside="warn")
    with pytest.raises(OutOfDomainError):
        f.evaluate(t=T, outside="raise")
    assert values(f, t=T, outside="ignore").tolist() == [-2.0, 4.0, 8.0, 12.0]


def test_a_physical_bound_on_the_output_with_an_open_end() -> None:
    f = load(formulation(), physical("f", "e = [0, inf]"))["f"]
    t = Q_([-1.0, 1e6], "degC")
    assert np.isnan(values(f, t=t, basis="physical")).tolist() == [True, False]
    assert not np.isnan(values(f, t=t)).any()  # physical domains on request
    assert f.physical_domains[0].bounds["e"] == (0.0, math.inf)


def test_an_open_end_on_an_input() -> None:
    f = load(formulation(), physical("f", "t = [-inf, 3]"))["f"]
    assert np.isnan(values(f, t=T, basis="all")).tolist() == [False, False, True, True]


def test_citations_combine_the_output_apart_from_the_inputs() -> None:
    # A citation bounding only the output does not widen the inputs another
    # bounds; bounds on the output combine by union between citations.
    f = load(
        formulation(),
        citation("f", "src", "e = [0, 10]"),
        citation("f", "other", "t = [0, 3]"),
    )["f"]
    assert np.isnan(values(f, t=T)).tolist() == [True, False, True, True]
    g = load(
        formulation("g", a=3.0),
        citation("g", "src", "e = [0, 10]"),
        citation("g", "other", "e = [0, 20]"),
    )["g"]
    assert np.isnan(values(g, t=T)).tolist() == [True, False, False, False]


@pytest.mark.parametrize(
    ("bounds", "criterion", "message"),
    [
        ("e = [0, 10]", False, "a bound on the output e states its criterion"),
        ("e = [-inf, inf]", True, r"bounds\.e: a domain bounds at least one end"),
        ("e = [0, nan]", True, r"bounds\.e\[1\]: expected a finite number or inf"),
        ("x = [0, 1]", True, "'x' is not an input nor the output"),
        ("e = [10, 0]", True, "empty interval"),
    ],
)
def test_invalid_bounds_are_refused(bounds: str, criterion: bool, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load(formulation(), citation("f", "src", bounds, criterion))


def test_the_bounds_of_a_relation_stay_finite() -> None:
    relation = """
[relations.r]
kind = "approximates"
subject = "g"
object = "f"
citation = "src"
accuracy = 1.0
bounds = { t = [0, inf] }
"""
    with pytest.raises(
        CatalogError, match=r"relations\.r\.bounds\.t\[1\]: expected a finite"
    ):
        load(formulation(), formulation("g", a=3.0), relation)


INNER = """
[formulations.g]
label = "g"
expression = "x - b"
fixed_units = true
output = { identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }
inputs = [{ identifier = "x", kind = "CelsiusTemperature", unit = "DEG_C", description = "x" }]
coefficients = { b = 1.0 }
"""


def test_a_part_of_a_composition_gives_a_value_inside_its_domains() -> None:
    composed = """
[formulations.c]
label = "composed"
composition = { outer = "f", inner = { t = "g" } }
output = { identifier = "p", kind = "Pressure", unit = "HectoPA", description = "p" }
"""
    loaded = load(
        formulation(),
        physical("f", "e = [0, 10]"),
        INNER,
        physical("g", "t = [0, inf]"),
        composed,
    )
    c = loaded["c"]
    x = Q_(np.array([0.5, 3.0, 7.0]), "degC")  # t: -0.5, 2, 6; e: -1, 4, 12
    assert np.isnan(values(c, x=x, basis="all")).tolist() == [True, False, True]
    # The bound on the inner output bounds an intermediate value: not one of
    # the composed formulation's own; that on the outer output is renamed.
    assert [dict(d.bounds) for d in c.physical_domains] == [{"p": (0.0, 10.0)}]


def test_a_bound_on_the_output_of_a_composition_keeps_the_domains_of_its_parts() -> (
    None
):
    composed = """
[formulations.c]
label = "composed"
composition = { outer = "f", inner = { t = "g" } }
"""
    loaded = load(
        formulation(),
        INNER,
        citation("g", "src", "x = [0, 5]"),
        composed,
        citation("c", "other", "e = [0, 100]"),
    )
    x = Q_(np.array([3.0, 7.0]), "degC")
    assert np.isnan(values(loaded["c"], x=x)).tolist() == [False, True]


def test_the_domains_of_a_branch_bound_its_output_where_it_holds() -> None:
    negative = formulation("n", "a * t", a=-1.0).replace("a = -1.0", "b = -1.0")
    negative = negative.replace('expression = "a * t"', 'expression = "b * t"')
    branches = """
[formulations.both]
label = "both"
branches = [{ formulation = "n", where = "t < 0" }, { formulation = "f", where = "t >= 0" }]
output = { identifier = "e", kind = "Pressure", unit = "HectoPA", description = "e" }
"""
    both = load(negative, formulation(), citation("f", "src", "e = [0, 10]"), branches)[
        "both"
    ]
    t = Q_(np.array([-20.0, 3.0, 6.0]), "degC")
    assert np.isnan(values(both, t=t)).tolist() == [False, False, True]


def test_inversion_exchanges_the_domains_of_the_input_and_the_output() -> None:
    f = load(formulation(), citation("f", "src", "t = [0, 50]"))["f"]
    inverse = invert(
        f,
        "t",
        output=Variable("T", "ThermodynamicTemperature", "K", "T"),
        input=Variable("e", "Pressure", "HectoPA", "e"),
    )
    assert isinstance(inverse, Formulation)
    (domain,) = inverse.domains
    assert domain.bounds["T"] == pytest.approx((273.15, 323.15))
    assert domain.bounds["e"] == pytest.approx((0.0, 100.0))
    result = values(inverse, e=Q_(np.array([20.0, 120.0]), "hPa"))
    assert result[0] == pytest.approx(283.15)
    assert math.isnan(result[1])


def test_a_numerical_inverse_keeps_the_bound_on_the_output_of_its_source() -> None:
    f = load(
        formulation(),
        citation("f", "src", "t = [0, 50]"),
        citation("f", "other", "e = [0, 10]"),
    )["f"]
    inverse = invert(
        f,
        "t",
        output=Variable("t", "CelsiusTemperature", "DEG_C", "t"),
        input=Variable("e", "Pressure", "HectoPA", "e"),
        method="numerical",
    )
    assert isinstance(inverse, NumericalInverse)
    result = values(inverse, e=Q_(np.array([8.0, 12.0]), "hPa"))
    assert result[0] == pytest.approx(4.0)
    assert math.isnan(result[1])


def test_an_open_domain_is_not_a_search_interval() -> None:
    f = load(formulation(), citation("f", "src", "t = [0, inf]"))["f"]
    output = Variable("t", "CelsiusTemperature", "DEG_C", "t")
    vapour = Variable("e", "Pressure", "HectoPA", "e")
    with pytest.raises(ValueError, match="states no finite validity domain on t"):
        invert(f, "t", output=output, input=vapour, method="numerical")
    inverse = invert(
        f, "t", output=output, input=vapour, method="numerical", search=(0.0, 50.0)
    )
    assert values(inverse, e=Q_(8.0, "hPa")) == pytest.approx(4.0)


def test_a_bound_on_the_output_alone_counts_as_no_domain_of_use() -> None:
    # Neither in the extent compared nor in the indicators of the goals.
    loaded = load(
        formulation(),
        citation("f", "src", "e = [0, 10]"),
        formulation("g", a=3.0),
        citation("g", "src", "t = [0, 3]"),
    )
    assert _stated_extent(loaded["f"]) == {}
    assert _stated_extent(loaded["g"]) == {"t": (0.0, 3.0)}
    assert not _reaches_domain(loaded["f"])
    assert _reaches_domain(loaded["g"])


def test_an_open_end_reads_in_the_table() -> None:
    f = load(formulation(), physical("f", "e = [0, inf]"))["f"]
    assert "0 or more hPa (physical)" in table([f]).to_markdown()
    g = load(formulation("g", a=3.0), physical("g", "t = [-inf, 3]"))["g"]
    assert "3 or less" in table([g]).to_markdown()
