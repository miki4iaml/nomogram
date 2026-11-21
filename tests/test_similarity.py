# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Profile functions derived from gradient functions, and back."""

from typing import Any

import mpmath
import numpy as np
import pytest

from nomogram.catalog import catalog, load_catalog
from nomogram.model import Formulation, Variable
from nomogram.similarity import DerivationError, gradient_function, profile_function
from nomogram.systems import CONVERGED, Equation, System
from nomogram.units import Q_

F = catalog().formulations
ONE = "dimensionless"
UNSTABLE = np.linspace(-10.0, -0.001, 101)
STABLE = np.linspace(0.001, 2.0, 101)


def values(formulation: Formulation, zeta: Any, name: str = "zeta") -> Any:
    given: dict[str, Any] = {name: Q_(zeta, ONE)}
    return formulation.evaluate(outside="ignore", **given).magnitude


def assert_same(mine: Any, theirs: Any, tolerance: float = 1e-12) -> None:
    deviation = np.abs(mine - theirs) / np.maximum(1.0, np.abs(theirs))
    assert np.nanmax(deviation) <= tolerance


@pytest.fixture(scope="module")
def ifs_momentum() -> Formulation:
    return profile_function(F["ecmwf_ifs_gradient_function_momentum_unstable"])


def test_the_integral_of_businger_dyer_is_the_form_of_paulson(
    ifs_momentum: Formulation,
) -> None:
    assert ifs_momentum.output.kind == "ProfileFunctionForMomentum"
    assert ifs_momentum.output.identifier == "Psi_M"
    assert ifs_momentum.derivation is not None
    assert ifs_momentum.derivation.method == "integration"
    assert (
        ifs_momentum.derivation.source
        == "ecmwf_ifs_gradient_function_momentum_unstable"
    )
    assert (
        ifs_momentum.key
        == "ecmwf_ifs_gradient_function_momentum_unstable_profile_function"
    )
    paulson = F["ecmwf_ifs_profile_function_momentum_unstable"]
    assert_same(values(ifs_momentum, UNSTABLE), values(paulson, UNSTABLE))
    heat = profile_function(F["ecmwf_ifs_gradient_function_heat_unstable"])
    assert heat.output.kind == "ProfileFunctionForHeat"
    assert_same(
        values(heat, UNSTABLE),
        values(F["ecmwf_ifs_profile_function_heat_unstable"], UNSTABLE),
    )


def test_the_round_trip_gives_back_the_gradient_function(
    ifs_momentum: Formulation,
) -> None:
    back = gradient_function(ifs_momentum)
    assert back.output.kind == "GradientFunctionForMomentum"
    assert back.derivation is not None
    assert back.derivation.method == "differentiation"
    phi = F["ecmwf_ifs_gradient_function_momentum_unstable"]
    assert_same(values(back, UNSTABLE), values(phi, UNSTABLE))


@pytest.mark.parametrize(
    ("gradient", "profile"),
    [
        # The profile functions of the IFS in stable conditions integrate
        # those of Beljaars and Holtslag (1991).
        (
            "beljaars_holtslag1991_gradient_function_momentum_stable",
            "ecmwf_ifs_profile_function_momentum_stable",
        ),
        (
            "beljaars_holtslag1991_gradient_function_heat_stable",
            "ecmwf_ifs_profile_function_heat_stable",
        ),
        (
            "grachev2007_gradient_function_heat_stable",
            "grachev2007_profile_function_heat_stable",
        ),
        (
            "cheng_brutsaert2005_gradient_function_momentum_stable",
            "cheng_brutsaert2005_profile_function_momentum_stable",
        ),
        (
            "businger1985_gradient_function_heat_stable",
            "businger1985_profile_function_heat_stable",
        ),
    ],
)
def test_profile_functions_that_integrate_their_gradient_functions(
    gradient: str, profile: str
) -> None:
    derived = profile_function(F[gradient])
    assert_same(values(derived, STABLE), values(F[profile], STABLE))


def test_the_ifs_in_stable_conditions() -> None:
    # Its gradient functions are not those its profile functions
    # integrate: at zeta = 0.1, +1.6 % for momentum, +78 % for heat.
    for kind, deviation in (("momentum", 1.6), ("heat", 78.3)):
        derived = profile_function(F[f"ecmwf_ifs_gradient_function_{kind}_stable"])
        mine = values(derived, 0.1)
        theirs = values(F[f"ecmwf_ifs_profile_function_{kind}_stable"], 0.1)
        assert round(100 * (mine / theirs - 1), 1) == deviation
    # The domain the IFS states on its gradient function for momentum,
    # zeta <= 0.5, bounds its integral too.
    momentum = profile_function(F["ecmwf_ifs_gradient_function_momentum_stable"])
    assert np.isnan(momentum.evaluate(zeta=Q_(1.0, ONE)).magnitude)


def test_sheba_for_momentum_has_no_closed_form_in_the_syntax() -> None:
    # SymPy writes its integral with complex roots of unity; the profile
    # function of SHEBA is its integral all the same, by quadrature.
    gradient = F["grachev2007_gradient_function_momentum_stable"]
    with pytest.raises(DerivationError, match="with complex numbers"):
        profile_function(gradient)

    def integrand(x: Any) -> float:
        phi = float(np.asarray(gradient._raw({"zeta": np.array(float(x))})))
        return (1 - phi) / float(x)

    for zeta in (0.1, 1.0, 5.0):
        quadrature = mpmath.quad(integrand, [0, zeta])
        psi = values(F["grachev2007_profile_function_momentum_stable"], zeta)
        assert float(quadrature) == pytest.approx(psi, rel=1e-10)


def test_a_piecewise_gradient_function_branch_by_branch() -> None:
    gradient = F["fairall1978_gradient_function_momentum"]
    derived = profile_function(gradient)
    assert derived.expression.startswith("piecewise(")
    unstable = profile_function(F["fairall1978_gradient_function_momentum_unstable"])
    assert_same(values(derived, UNSTABLE), values(unstable, UNSTABLE))
    assert_same(values(derived, STABLE), -4.7 * STABLE)
    back = gradient_function(derived)
    assert_same(
        values(back, np.concatenate([UNSTABLE, STABLE])),
        values(gradient, np.concatenate([UNSTABLE, STABLE])),
    )
    # A profile function by branches differentiates branch by branch.
    ifs = gradient_function(F["ecmwf_ifs_profile_function_momentum"])
    assert_same(
        values(ifs, UNSTABLE),
        values(F["ecmwf_ifs_gradient_function_momentum_unstable"], UNSTABLE),
    )


def test_the_domains_of_the_source_on_zeta_are_carried() -> None:
    derived = profile_function(
        F["cheng_brutsaert2005_gradient_function_momentum_stable"]
    )
    assert [dict(d.bounds) for d in derived.domains] == [{"zeta": (0.0, 5.0)}]
    assert derived.coefficients == ()
    kept = gradient_function(F["grachev2007_profile_function_momentum_stable"])
    assert {c.identifier for c in kept.coefficients} == {"a_m", "b_m"}


SOURCE = """
[references.test_source]
authors = "A."
title = "T"
status = "verified"

[kinds.StabilityParameter]
label = "StabilityParameter"
specialization_of = "DimensionlessRatio"

[kinds.GradientFunctionForMomentum]
label = "GradientFunctionForMomentum"
specialization_of = "DimensionlessRatio"

[kinds.ProfileFunctionForMomentum]
label = "ProfileFunctionForMomentum"
specialization_of = "DimensionlessRatio"

[kinds.ProfileFunctionForHeat]
label = "ProfileFunctionForHeat"
specialization_of = "DimensionlessRatio"
"""


def synthetic(
    expression: str, kind: str = "GradientFunctionForMomentum"
) -> Formulation:
    document = (
        SOURCE
        + f"""
[formulations.f]
label = "f"
expression = "{expression}"
fixed_units = true
output = {{ identifier = "y", kind = "{kind}", unit = "UNITLESS", description = "y" }}
inputs = [{{ identifier = "zeta", kind = "StabilityParameter", unit = "UNITLESS", description = "zeta" }}]

[[formulations.f.citations]]
reference = "test_source"
"""
    )
    return load_catalog([document]).formulations["f"]


@pytest.mark.parametrize(
    ("formulation", "message"),
    [
        (lambda: F["businger1971_keyps"], "an implicit equation"),
        (lambda: F["coare36_friction_velocity"], "takes one input"),
        (lambda: synthetic("2 + zeta"), "diverges unless phi tends to 1"),
        (lambda: synthetic("1 + zeta", "DimensionlessRatio"), "give the output"),
        (
            lambda: synthetic(
                "1 + 2 * piecewise((zeta, zeta < 0), (zeta / 2, zeta >= 0))"
            ),
            "inside an expression",
        ),
        (lambda: synthetic("piecewise((1 + zeta, zeta > 1))"), "no branch holds"),
        (lambda: synthetic("1 + zeta * exp(zeta ** 2)"), "outside the syntax"),
    ],
)
def test_derivations_refused(formulation: Any, message: str) -> None:
    with pytest.raises(DerivationError, match=message):
        profile_function(formulation())


def test_gradient_functions_refused() -> None:
    with pytest.raises(DerivationError, match="give the output"):
        gradient_function(synthetic("zeta", "DimensionlessRatio"))
    with pytest.raises(DerivationError, match="inside an expression"):
        gradient_function(
            synthetic(
                "2 * piecewise((zeta, zeta < 0), (zeta / 2, zeta >= 0))",
                "ProfileFunctionForMomentum",
            )
        )
    with pytest.raises(DerivationError, match="an implicit equation"):
        gradient_function(F["businger1971_keyps"])


def test_an_output_given_explicitly() -> None:
    output = Variable("psi", "ProfileFunctionForHeat", "UNITLESS", "A profile function")
    derived = profile_function(
        synthetic("1 + zeta", "DimensionlessRatio"), output=output, key="k", label="l"
    )
    assert (derived.key, derived.label, derived.output) == ("k", "l", output)
    assert values(derived, 0.5) == pytest.approx(-0.5)


def test_fairall_s_printed_profile_function_and_equation_20_as_a_system() -> None:
    printed = {
        "momentum": F["fairall1978_profile_function_momentum"],
        "heat": F["fairall1978_profile_function_heat"],
    }
    # The printed function departs from the integral of phi_U and phi_T,
    # as the notes of the catalog state.
    for kind, expected in (("momentum", (-9, -18, -21)), ("heat", (-5, -5, -25))):
        gradient = F[f"fairall1978_gradient_function_{kind}"]
        derived = profile_function(gradient)
        found = []
        for xi in (-0.1, -1.0, 0.1):
            phi = values(gradient, xi)
            mine = values(printed[kind], phi, printed[kind].inputs[0].identifier)
            found.append(round(100 * (mine / values(derived, xi) - 1)))
        assert tuple(found) == expected
    # Equation 20, implicit in xi, solved with the derived profile functions.
    system = System(
        "fairall1978_bulk",
        "Equation 20 of Fairall et al. (1978)",
        (
            Equation(
                profile_function(F["fairall1978_gradient_function_momentum"]),
                bind={"zeta": "xi"},
            ),
            Equation(
                profile_function(F["fairall1978_gradient_function_heat"]),
                bind={"zeta": "xi"},
            ),
            Equation(F["fairall1978_stability_parameter"]),
        ),
        start={"xi": "xi_0"},
    )
    assert system.unknowns == ("xi",)
    solution = system.evaluate(
        xi_0=Q_(np.array([-1.0, 0.1]), ONE), C_UN=Q_(1.2e-3, ONE), C_TN=Q_(1.1e-3, ONE)
    )
    assert (solution.status == CONVERGED).all()
    assert solution["xi"].magnitude == pytest.approx([-0.89724, 0.10505], abs=1e-5)


# --- Found in review ------------------------------------------------------


def test_the_input_must_be_the_stability_parameter() -> None:
    # The gradient function of Fleagle and Businger takes Ri; the printed
    # profile function of Fairall et al. takes the gradient function.
    with pytest.raises(DerivationError, match="not of Ri"):
        profile_function(F["fleagle_businger1980_gradient_function_momentum_unstable"])
    with pytest.raises(DerivationError, match="not of Phi_M"):
        gradient_function(F["fairall1978_profile_function_momentum"])
    named = Variable("zeta", "ProfileFunctionForMomentum", "UNITLESS", "psi")
    with pytest.raises(DerivationError, match="named after its input"):
        profile_function(F["ecmwf_ifs_gradient_function_momentum_stable"], output=named)


def test_a_condition_bounded_by_a_coefficient() -> None:
    document = (
        SOURCE
        + """
[formulations.f]
label = "f"
expression = "piecewise((-5 * zeta, zeta < z_c), (-zeta - 4 * z_c, zeta >= z_c))"
fixed_units = true
output = { identifier = "y", kind = "ProfileFunctionForMomentum", unit = "UNITLESS", description = "y" }
inputs = [{ identifier = "zeta", kind = "StabilityParameter", unit = "UNITLESS", description = "zeta" }]
coefficients = { z_c = 0.5 }

[[formulations.f.citations]]
reference = "test_source"
"""
    )
    derived = gradient_function(load_catalog([document]).formulations["f"])
    assert "z_c" in derived.expression
    assert values(derived, np.array([0.2, 1.0])) == pytest.approx([2.0, 2.0])


def test_a_source_by_branches_keeps_the_domains_of_each() -> None:
    document = (
        SOURCE
        + """
[formulations.unstable]
label = "unstable"
expression = "(1 - 16 * zeta) ** (-1 / 4)"
fixed_units = true
output = { identifier = "Phi_M", kind = "GradientFunctionForMomentum", unit = "UNITLESS", description = "phi" }
inputs = [{ identifier = "zeta", kind = "StabilityParameter", unit = "UNITLESS", description = "zeta" }]

[[formulations.unstable.citations]]
reference = "test_source"
assumptions = ["Unstable conditions."]

[formulations.stable]
label = "stable"
expression = "1 + 5 * zeta"
fixed_units = true
output = { identifier = "Phi_M", kind = "GradientFunctionForMomentum", unit = "UNITLESS", description = "phi" }
inputs = [{ identifier = "zeta", kind = "StabilityParameter", unit = "UNITLESS", description = "zeta" }]

[[formulations.stable.citations]]
reference = "test_source"
equation = "7"

[[formulations.stable.citations.domains]]
bounds = { zeta = [0.0, 0.5] }

[formulations.both]
label = "both"
output = { identifier = "Phi_M", kind = "GradientFunctionForMomentum", unit = "UNITLESS", description = "phi" }
branches = [
  { formulation = "unstable", where = "zeta < 0" },
  { formulation = "stable", where = "zeta >= 0" },
]
"""
    )
    gradient = load_catalog([document]).formulations["both"]
    derived = profile_function(gradient)
    assert derived.derived
    assert [b.condition for b in derived.branches] == ["zeta < 0", "zeta >= 0"]
    stable = derived.branches[1].formulation
    assert stable.citations[0].equation is None
    assert [dict(d.bounds) for d in stable.domains] == [{"zeta": (0.0, 0.5)}]
    assert derived.branches[0].formulation.citations[0].assumptions == (
        "Unstable conditions.",
    )
    found = derived.evaluate(zeta=Q_(np.array([-1.0, 0.2, 1.0]), ONE)).magnitude
    assert found[1] == pytest.approx(-1.0)
    assert np.isnan(found[2])


def test_branches_with_a_gap_are_refused_a_point_left_out_is_not() -> None:
    with pytest.raises(DerivationError, match="do not follow one another"):
        profile_function(
            synthetic("piecewise((1 - 2 * zeta, zeta < -1), (1 + zeta, zeta >= 0))")
        )
    strict = profile_function(
        synthetic("piecewise((1 - zeta, zeta < 0), (1 + zeta, zeta > 0))")
    )
    # psi = zeta on one side, -zeta on the other.
    assert values(strict, np.array([-0.5, 0.5])) == pytest.approx([-0.5, -0.5])


def test_every_branch_is_checked_far_from_0() -> None:
    from nomogram.similarity import _points_inside

    points = _points_inside(20.0, float("inf"), [])
    assert points
    assert all(p > 20.0 for p in points)
    inside = sorted(_points_inside(-1.0, 1.0, [(0.0, 0.5)]))
    assert inside == pytest.approx([0.0, 0.125, 0.25, 1 / 3, 0.375])


def test_a_domain_without_0_is_carried_and_said() -> None:
    derived = profile_function(F["ecmwf_ifs_gradient_function_momentum_unstable"])
    assert {d.bounds["zeta"] for d in derived.domains} == {(-1.0, -0.01)}
    assert derived.note is not None
    assert "does not hold zeta = 0.0" in derived.note
    citation = derived.citations[0]
    assert (citation.equation, citation.accuracy) == (None, None)
    assert citation.note is not None
    assert "from which nomogram derived" in citation.note
