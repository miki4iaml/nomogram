# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The evaporation duct from shipboard measurements, by the formulations of
the catalog: the surface layer of COARE 3.6 and of the IFS, the radio
refractivity of ITU-R P.453, and four ways to the height of the duct.

The lines shown in ``docs/evaporation-duct.md`` are lines of this script (a
test checks it); ``main`` only formats and saves the figure besides.

Run from the repository (extra ``viz`` installed)::

    uv run python docs/examples/evaporation_duct.py docs/images/evaporation-duct.png
"""

import math
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

import nomogram as nomo
from nomogram.catalog import catalog
from nomogram.units import Q_

mpl.use("Agg")  # render to a file, without a display

#: One row in 20 of the test data of COARE 3.6 (see data/NOTICE.md).
DATA = Path(__file__).parent / "data" / "coare36_test.csv"
CATALOG = catalog()
F = CATALOG.formulations
#: The keys of the formulations the chain calls, for its references.
CALLED: set[str] = set()
ONE = "dimensionless"
#: Heights of the profiles of refractivity, from 0.1 m to 100 m.
HEIGHTS = np.geomspace(0.1, 100.0, 3000)


def value(key: str, unit: str, **inputs: Any) -> np.ndarray:
    """The values of a formulation of the catalog, in ``unit``."""
    CALLED.add(key)
    return np.asarray(F[key].evaluate(**inputs).to(unit).magnitude)


def measurements() -> dict[str, np.ndarray]:
    """The columns of the test data, by name."""
    lines = DATA.read_text(encoding="utf-8").splitlines()
    rows = [line.split(",") for line in lines if not line.startswith("#")]
    table = np.array(rows[1:], dtype=float)
    return {name: table[:, i] for i, name in enumerate(rows[0])}


def air(m: dict[str, np.ndarray]) -> dict[str, Any]:
    """What the two algorithms take from the measurements."""
    g = value("wmo_normal_gravity_wgs84", "m/s**2", phi=Q_(m["lat"], "deg"))
    p_t = value(  # the pressure at the height of the thermometer
        "wmo_hypsometric_pressure",
        "hPa",
        p_1=Q_(m["P"], "hPa"),
        dZ=Q_(m["zt"], "m"),
        T_v=Q_(m["ta"], "degC").to("K"),
    )
    e_s = value("buck1981", "hPa", t=Q_(m["ta"], "degC"))  # the form COARE takes
    q = value(
        "ecmwf_ifs_specific_humidity_from_vapour_pressure",
        "kg/kg",
        e=Q_(m["rh"] / 100 * e_s, "hPa"),
        p=Q_(p_t, "hPa"),
    )
    t = m["ta"]
    nu = value("coare36_kinematic_viscosity_of_air", "m**2/s", t=Q_(t, "degC"))
    return {
        "g": Q_(g, "m/s**2"),
        "T": Q_(t + 273.16, "K"),  # as COARE converts
        "T_surf": Q_(m["T_skin"] + 273.16, "K"),  # COARE's skin, warm layer included
        "q": Q_(q, "kg/kg"),
        "q_surf": Q_(m["Qs"], "g/kg"),
        "nu": Q_(nu, "m**2/s"),
    }


def coare(m: dict[str, np.ndarray], a: dict[str, Any]) -> dict[str, np.ndarray]:
    """The scales of COARE 3.6: a fixed point over its formulations."""
    u, zu, zt, zq = m["u"], Q_(m["zu"], "m"), Q_(m["zt"], "m"), Q_(m["zq"], "m")
    gust = np.full_like(u, 0.5)  # m/s, COARE's first guess
    u_s = 0.035 * u
    z_0M = np.full_like(u, 1e-4)
    length = np.full_like(u, -100.0)
    for _ in range(10):  # as COARE iterates
        s = np.hypot(u, gust)  # the wind and the convective gust
        u_10n = u_s / 0.4 * u / s * np.log(10.0 / z_0M)
        # Below 2.94 m/s, the line gives a negative coefficient, beyond the
        # bounds of its kind: NaN unless asked. COARE takes it, the smooth
        # flow term keeping the roughness length positive.
        alpha = value(
            "coare36_charnock_coefficient",
            ONE,
            U_10N=Q_(u_10n, "m/s"),
            outside="ignore",
        )
        z_0M = value(
            "edson2013_roughness_length_momentum",
            "m",
            alpha=Q_(alpha, ONE),
            u_s=Q_(u_s, "m/s"),
            nu=a["nu"],
            g=a["g"],
            outside="ignore",  # the coefficient taken below 2.94 m/s
        )
        r_r = Q_(z_0M * u_s / a["nu"].magnitude, ONE)
        z_0T = value("coare36_roughness_length_heat", "m", R_r=r_r)
        z_0Q = value("coare36_roughness_length_humidity", "m", R_r=r_r)
        at = {"L": Q_(length, "m")}
        u_s = value(
            "coare36_friction_velocity",
            "m/s",
            S=Q_(s, "m/s"),
            z_u=zu,
            z_0M=Q_(z_0M, "m"),
            **at,
        )
        t_s = value(
            "coare36_temperature_scale",
            "K",
            T_surf=a["T_surf"],
            T=a["T"],
            z_t=zt,
            z_0T=Q_(z_0T, "m"),
            g=a["g"],
            **at,
        )
        q_s = value(
            "coare36_humidity_scale",
            "kg/kg",
            q_surf=a["q_surf"],
            q=a["q"],
            z_q=zq,
            z_0Q=Q_(z_0Q, "m"),
            **at,
        )
        length = value(
            "coare36_obukhov_length",
            "m",
            T=a["T"],
            u_s=Q_(u_s, "m/s"),
            T_s=Q_(t_s, "K"),
            q_s=Q_(q_s, "kg/kg"),
            g=a["g"],
        )
        flux = value(  # the virtual temperature flux, positive upward
            "coare36_virtual_temperature_flux",
            "K*m/s",
            u_s=Q_(u_s, "m/s"),
            T_s=Q_(t_s, "K"),
            q_s=Q_(q_s, "kg/kg"),
            q=a["q"],
            T=a["T"],
        )
        gust = value(
            "coare36_convective_gust",
            "m/s",
            T=a["T"],
            Q_0v=Q_(flux, "K*m/s"),
            z_i=Q_(m["zi"], "m"),
            g=a["g"],
        )
    return {"u_s": u_s, "T_s": t_s, "q_s": q_s, "L": length, "z_0M": z_0M}


def ifs(m: dict[str, np.ndarray], a: dict[str, Any]) -> dict[str, np.ndarray]:
    """The scales of the IFS: a fixed point, L from Ri_b (equation 3.25).

    One model level: the wind at 18 m, the temperature and humidity at 17 m
    taken there; the free convection velocity added to the wind (3.19, 3.20).
    """
    u, z_n = m["u"], Q_(m["zu"], "m")
    c_p = Q_(1004.67, "J/(kg*K)")
    theta = a["T"] + a["g"] / c_p * Q_(m["zt"], "m")
    theta_v = theta * (1 + 0.61 * a["q"].magnitude)
    surface_v = a["T_surf"] * (1 + 0.61 * a["q_surf"].to("kg/kg").magnitude)
    u_s = 0.035 * u
    wind = u
    for _ in range(15):
        richardson = value(
            "ecmwf_ifs_bulk_richardson_number",
            ONE,
            theta_v=theta_v,
            z_n=z_n,
            theta_vn=theta_v,
            theta_vsurf=surface_v,
            U_n=Q_(wind, "m/s"),
        )
        z_0 = {
            name: Q_(
                value(f"ecmwf_ifs_roughness_length_{key}_sea", "m", u_s=Q_(u_s, "m/s")),
                "m",
            )
            for name, key in (
                ("z_0M", "momentum"),
                ("z_0H", "heat"),
                ("z_0Q", "humidity"),
            )
        }
        # The implicit equation 3.25, solved for L. Its sign is that of Ri_b:
        # the search keeps to that side, away from the pole at L = 0.
        length = np.full_like(u, np.nan)
        for side, search in (
            (richardson < 0, (-1e6, -0.01)),
            (richardson > 0, (0.01, 1e6)),
        ):
            if side.any():
                length[side] = value(
                    "ecmwf_ifs_obukhov_length_from_bulk_richardson_number",
                    "m",
                    Ri_b=Q_(richardson[side], ONE),
                    z_n=z_n[side],
                    z_0M=z_0["z_0M"][side],
                    z_0H=z_0["z_0H"][side],
                    search=search,
                )
        at = {"z_n": z_n, "z_0M": z_0["z_0M"], "L": Q_(length, "m")}
        c_m = value("ecmwf_ifs_transfer_coefficient_momentum", ONE, **at)
        u_s = value(
            "ecmwf_ifs_friction_velocity", "m/s", C_M=Q_(c_m, ONE), U_n=Q_(wind, "m/s")
        )
        c_h = value("ecmwf_ifs_transfer_coefficient_heat", ONE, z_0H=z_0["z_0H"], **at)
        c_q = value(
            "ecmwf_ifs_transfer_coefficient_humidity", ONE, z_0Q=z_0["z_0Q"], **at
        )
        # The scales of the IFS take the sign of the upward flux.
        upward_s = c_h * wind * (c_p * (a["T_surf"] - theta)).to("J/kg").magnitude
        upward_q = c_q * wind * (a["q_surf"] - a["q"]).to("kg/kg").magnitude
        flux = value(
            "ecmwf_ifs_virtual_temperature_flux",
            "K*m/s",
            u_s=Q_(u_s, "m/s"),
            s_s=Q_(upward_s / u_s, "J/kg"),
            q_s=Q_(upward_q / u_s, "kg/kg"),
            T_n=a["T"],
        )
        w_s = value(  # NaN where the surface cools the air: no gust there
            "ecmwf_ifs_free_convection_velocity_scale",
            "m/s",
            T_n=a["T"],
            Q_0v=Q_(flux, "K*m/s"),
        )
        wind = value(
            "ecmwf_ifs_wind_speed_free_convection",
            "m/s",
            u_n=Q_(u, "m/s"),
            v_n=Q_(0.0, "m/s"),
            w_s=Q_(np.nan_to_num(w_s), "m/s"),
        )
    # The scales of the profiles, positive when the quantity increases upwards.
    t_s = -upward_s / c_p.magnitude / u_s
    q_s = -upward_q / u_s
    return {
        "u_s": u_s,
        "T_s": t_s,
        "q_s": q_s,
        "L": length,
        "z_0M": z_0["z_0M"].magnitude,
    }


def modified_refractivity(
    m: dict[str, np.ndarray], a: dict[str, Any], scales: dict[str, np.ndarray]
) -> np.ndarray:
    """M(z) of ITU-R P.453 along the profiles of COARE, one row per case."""
    column = {k: v[:, None] for k, v in scales.items()}
    at = {"z_r": Q_(HEIGHTS[None, :], "m"), "L": Q_(column["L"], "m")}
    t = value(
        "coare36_temperature_at_height",
        "K",
        T=a["T"][:, None],
        T_s=Q_(column["T_s"], "K"),
        z_t=Q_(m["zt"][:, None], "m"),
        g=a["g"][:, None],
        **at,
    )
    q = value(
        "coare36_specific_humidity_at_height",
        "kg/kg",
        q=a["q"][:, None],
        q_s=Q_(column["q_s"], "kg/kg"),
        z_q=Q_(m["zq"][:, None], "m"),
        z_t=Q_(m["zt"][:, None], "m"),
        **at,
    )
    p = value(
        "wmo_hypsometric_pressure",
        "hPa",
        p_1=Q_(m["P"][:, None], "hPa"),
        dZ=Q_(HEIGHTS[None, :], "m"),
        T_v=Q_(t * (1 + 0.61 * q), "K"),
    )
    e = value(
        "wmo_vapour_pressure_definition", "hPa", r=Q_(q / (1 - q), ONE), p=Q_(p, "hPa")
    )
    n = value(
        "itu_r_p453_refractivity_total_pressure",
        "ppm",
        P=Q_(p, "hPa"),
        e=Q_(e, "hPa"),
        T=Q_(t, "K"),
    )
    return value(
        "itu_r_p453_modified_refractivity",
        "ppm",
        N=Q_(n, "ppm"),
        h=Q_(HEIGHTS[None, :], "m"),
    )


def lowest(profiles: np.ndarray) -> np.ndarray:
    """The height of the minimum of M; NaN at the lowest height (no duct)."""
    index = np.argmin(profiles, axis=1)
    return np.where(index > 0, HEIGHTS[index], np.nan)


def duct_heights(
    a: dict[str, Any], scales: dict[str, np.ndarray]
) -> dict[str, np.ndarray]:
    """z* of Fairall et al. (1978) and of Frederickson et al. (1994)."""
    q = a["q"].magnitude
    # Fairall et al. take the scale of the mixing ratio r = q/(1 - q), whose
    # derivative gives dq/(1 - q)^2; Frederickson et al. that of q.
    mixing = Q_(scales["q_s"] / (1 - q) ** 2, "kg/kg")
    length, t_s = Q_(scales["L"], "m"), Q_(scales["T_s"], "K")
    return {
        "fairall": value(
            "fairall1978_evaporation_duct_height", "m", q_s=mixing, T_s=t_s, L=length
        ),
        "frederickson": value(
            "frederickson1994_evaporation_duct_height",
            "m",
            q_s=Q_(scales["q_s"], "kg/kg"),
            T_s=t_s,
            L=length,
        ),
    }


def paulus_jeske(t_a: float, t_s: float, rh: float, u: float) -> float:
    """The six steps of NOSC TD 1596 (section 3.0), from one measurement.

    Temperatures in degC, relative humidity in %, wind speed in knots; the
    measurements taken at its reference height, 6 m, whatever theirs.
    """
    if u < 0.01:  # step 1: no wind, no duct
        return 0.0
    z_1 = Q_(6.0, "m")

    def saturation(t_k: float) -> float:
        return float(
            value("paulus1989_saturation_vapour_pressure", "hPa", T=Q_(t_k, "K"))
        )

    def refractivity(t_k: float, e: float) -> float:
        n = value(
            "paulus1989_potential_refractivity", "ppm", T=Q_(t_k, "K"), e=Q_(e, "hPa")
        )
        return float(n)

    def height(t_ak: float, t_sk: float, e: float, e_0: float) -> float:
        ri_b = float(
            value(
                "paulus1989_bulk_richardson_number",
                ONE,
                T_a=Q_(t_ak, "K"),
                T_s=Q_(t_sk, "K"),
                u=Q_(max(u, 1.0), "knot"),
            )
        )
        ri_b = min(ri_b, 1.0)  # step 2
        delta_n = float(
            value(
                "paulus1989_potential_refractivity_difference",
                "ppm",
                N_A=Q_(refractivity(t_ak, e), "ppm"),
                N_S=Q_(refractivity(t_sk, e_0), "ppm"),
            )
        )
        length = float(value("paulus1989_obukhov_length", "m", Ri_b=Q_(ri_b, ONE)))
        common = {
            "Delta_N_p": Q_(delta_n, "ppm"),
            "L": Q_(length, "m"),
            "outside": "ignore",
        }
        if ri_b < 0:  # step 5, unstable
            psi = value("paulus1989_profile_function", ONE, zeta=z_1 / Q_(length, "m"))
            entry = "paulus1989_evaporation_duct_height_unstable"
            delta = float(value(entry, "m", Psi_H=Q_(psi, ONE), **common))
            return 0.0 if math.isnan(delta) or delta_n >= 0 else delta
        delta = float(value("paulus1989_evaporation_duct_height_stable", "m", **common))
        if delta < 0 or delta / length > 1:  # step 4 (c), limited
            entry = "paulus1989_evaporation_duct_height_limited"
            return float(
                value(entry, "m", Delta_N_p=common["Delta_N_p"], outside="ignore")
            )
        return delta

    t_ak, t_sk = t_a + 273.2, t_s + 273.2  # step 1, as the source converts
    e_0 = saturation(t_sk)
    if t_a - t_s > -1:  # p. 7: computed at T_a = T_s and T_a = T_s - 1
        at_sea = height(t_sk, t_sk, rh / 100 * e_0, e_0)
        below = height(t_sk - 1, t_sk, rh / 100 * saturation(t_sk - 1), e_0)
        if at_sea > below:
            return min(below, 40.0)
    return min(height(t_ak, t_sk, rh / 100 * saturation(t_ak), e_0), 40.0)


def compute() -> dict[str, Any]:
    """The cases, the scales of both algorithms, M(z) and the duct heights."""
    m = measurements()
    a = air(m)
    by_coare, by_ifs = coare(m, a), ifs(m, a)
    profiles = modified_refractivity(m, a, by_coare)
    z_star = duct_heights(a, by_coare)
    heights = {
        "minimum of M, COARE 3.6": lowest(profiles),
        "z* of Fairall et al., COARE 3.6": z_star["fairall"],
        "z* of Frederickson et al., COARE 3.6": z_star["frederickson"],
        "z* of Fairall et al., IFS": duct_heights(a, by_ifs)["fairall"],
        "Paulus-Jeske, measurements at 6 m": np.array(
            [
                paulus_jeske(t_a, t_s, rh, u / 0.514444)  # wind in knots
                for t_a, t_s, rh, u in zip(
                    m["ta"], m["tsnk"], m["rh"], m["u"], strict=True
                )
            ]
        ),
    }
    return {
        "m": m,
        "coare": by_coare,
        "ifs": by_ifs,
        "profiles": profiles,
        "heights": heights,
        "called": sorted(CALLED),
    }


def bibliography(called: Iterable[str]) -> list[str]:
    """The references of the formulations called, and of what they use.

    Followed through the links of the catalog (``Catalog.uses``): the
    formulations a formulation calls or is made of, and the constants it
    takes, each with its own references; one Markdown line per reference.
    """
    queue = [f"formulations.{key}" for key in called]
    seen: set[str] = set()
    cited: set[str] = set()
    while queue:
        entry = queue.pop()
        if entry in seen:
            continue
        seen.add(entry)
        for ref in CATALOG.uses(entry).refs:
            section, _, key = ref.partition(".")
            if section == "references":
                cited.add(key)
            elif section in ("formulations", "constants"):
                queue.append(ref)
    lines = []
    for reference in sorted(
        (CATALOG.references[key] for key in cited),
        key=lambda r: (r.authors.casefold(), r.year or 0),
    ):
        link = f"https://doi.org/{reference.doi}" if reference.doi else reference.url
        container = f" {reference.container}." if reference.container else ""
        lines.append(
            f"- {reference.authors} ({reference.year}). *{reference.title}*."
            f"{container}" + (f" <{link}>" if link else "")
        )
    return lines


def main(output: str) -> None:
    """Write the profile of one case and the duct heights along the series."""
    results = compute()
    m, by_coare, profiles = results["m"], results["coare"], results["profiles"]
    heights = results["heights"]

    # Formatting only: the panels, their labels, the size and the signature;
    # the labels and the grid follow the preset of the documentation.
    documentation = nomo.display.DisplayOptions.DOCUMENTATION
    figure, (left, right) = plt.subplots(1, 2, gridspec_kw={"width_ratios": [1, 2]})
    case = 0
    left.plot(profiles[case], HEIGHTS, color="black")
    styles = ("-", "--", ":", "-.", (0, (1, 3)))
    for index, ((label, h), style) in enumerate(
        zip(heights.items(), styles, strict=True)
    ):
        color = f"C{index}"
        left.axhline(h[case], color=color, linestyle=style, linewidth=1, label=label)
        right.plot(m["jd"], h, color=color, linestyle=style, marker=".", label=label)
    left.set_yscale("log")
    label = nomo.display.axis_label
    left.set_xlabel(label("Modified refractivity", "M", "ppm", options=documentation))
    left.set_ylabel(label("Height", "z", "m", options=documentation))
    left.set_title(f"Day {m['jd'][case]:.2f}, L = {by_coare['L'][case]:.0f} m")
    right.set_xlabel(label("Day of the year", None, "", options=documentation))
    right.set_ylabel(label("Evaporation duct height", None, "m", options=documentation))
    right.set_title("Duct height along the test data of COARE 3.6")
    right.legend(fontsize="small")
    if documentation.grid:
        for axes in (left, right):
            axes.grid(alpha=0.3)
    figure.set_size_inches(14, 6)
    figure.tight_layout()
    nomo.plot.sign(figure, axes=right)
    # No metadata in the image (the image metadata hook refuses it).
    figure.savefig(output, dpi=90, metadata={"Software": None})


if __name__ == "__main__":
    main(sys.argv[1])
