# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The documentation examples run, so that they never go stale."""

import ast
import importlib.util
import math
import re
from pathlib import Path
from typing import Any

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "docs" / "examples" / "saturation_vapour_pressure.py"
HUMIDITY = ROOT / "docs" / "examples" / "humidity_between_levels.py"
READMES = [ROOT / "README.md", ROOT / "README.fr.md"]
DISPLAY = ROOT / "docs" / "display.md"


def python_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", text, flags=re.DOTALL)


def code_lines(block: str) -> list[str]:
    lines = (line.split("  #", 1)[0].strip() for line in block.splitlines())
    return [line for line in lines if line]


def test_saturation_vapour_pressure_example_writes_its_plot(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("saturation_vapour_pressure", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "plot.png"
    module.main(str(output))
    assert output.read_bytes().startswith(b"\x89PNG")


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_readme_example_is_the_script_that_draws_the_image(readme: Path) -> None:
    script = code_lines(SCRIPT.read_text(encoding="utf-8"))
    for line in code_lines(python_blocks(readme)[0]):
        assert any(line in candidate for candidate in script), line


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_readme_code_runs(readme: Path) -> None:
    import matplotlib.pyplot as plt

    namespace: dict[str, object] = {}
    for block in python_blocks(readme):
        exec(compile(block, str(readme), "exec"), namespace)  # noqa: S102
    plt.close("all")
    assert "table" in namespace
    assert "ha" in namespace
    # The interpolation scheme, its levels fixed: a function of p alone.
    in_ln_p = namespace["in_ln_p"]
    at_700 = in_ln_p.evaluate(p=namespace["Q_"](700, "hPa"))  # type: ignore[attr-defined, operator]
    assert magnitude(at_700.to("K")) == pytest.approx(268.49, abs=0.005)


def test_display_guide_code_runs() -> None:
    namespace: dict[str, object] = {}
    for block in python_blocks(DISPLAY):
        exec(compile(block, str(DISPLAY), "exec"), namespace)  # noqa: S102
    assert namespace["label"] == r"$e_{\mathrm{w}}$/hPa"
    assert namespace["simple"] == "Celsius temperature $t$ [°C]"
    assert "6{,}112" in str(namespace["french"])


def test_vertical_guide_code_gives_the_values_it_states() -> None:
    import matplotlib.pyplot as plt

    guide = ROOT / "docs" / "vertical.md"
    namespace: dict[str, object] = {}
    for block in python_blocks(guide):
        exec(compile(block, str(guide), "exec"), namespace)  # noqa: S102
    plt.close("all")
    assert magnitude(namespace["at_500_hPa"]) == pytest.approx(5574.44, abs=0.005)
    # MetPy's mixed parcel: its docstring prints 28.750033 and 18.1504239 degC.
    parcel_t = namespace["parcel_t"].to("degC")  # type: ignore[attr-defined]
    parcel_t_d = namespace["parcel_t_d"].to("degC")  # type: ignore[attr-defined]
    assert magnitude(parcel_t) == pytest.approx(28.750033, abs=5e-7)
    assert magnitude(parcel_t_d) == pytest.approx(18.1504235, abs=5e-8)
    assert magnitude(parcel_t_d) == pytest.approx(18.1504239, abs=5e-7)
    # The relative humidity at 700 hPa, by each practice.
    relative = namespace["tables"][2]  # type: ignore[index]
    at_700 = 60  # 850 to 500 hPa by steps of 2.5 hPa
    values = {
        key.split("(")[0]: 100 * float(value.to("").magnitude[at_700])
        for key, value in relative.values.items()
    }
    assert values.pop(relative.reference) == pytest.approx(47.34, abs=0.005)
    assert values == pytest.approx(
        {
            "metpy171_relative_humidity_dew_point_log_pressure": 50.01,
            "metpy171_relative_humidity_dew_point_pressure": 49.76,
            "pressure_interpolation_relative_humidity": 49.76,
            "metpy171_relative_humidity_isentropic": 59.54,
            "metpy171_relative_humidity_specific_humidity_log_pressure": 60.72,
            "relative_humidity_log_specific_humidity_log_pressure": 47.36,
        },
        abs=0.005,
    )


def test_humidity_example_is_the_script_that_draws_the_image() -> None:
    script = code_lines(HUMIDITY.read_text(encoding="utf-8"))
    blocks = python_blocks(ROOT / "docs" / "vertical.md")
    shown = next(b for b in blocks if "plot_profiles(tables" in b)
    for line in code_lines(shown):
        assert any(line in candidate for candidate in script), line


def test_humidity_example_writes_its_plot(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("humidity_between_levels", HUMIDITY)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "plot.png"
    module.main(str(output))
    assert output.read_bytes().startswith(b"\x89PNG")


def test_search_guide_code_runs() -> None:
    guide = ROOT / "docs" / "search.md"
    namespace: dict[str, object] = {}
    for block in python_blocks(guide):
        exec(compile(block, str(guide), "exec"), namespace)  # noqa: S102
    assert "c" in namespace


#: A number at the start of a comment: the value the line gives, to its last
#: digit (rounded, or truncated when "..." follows).
COMMENTED_VALUE = re.compile(r"#\s*\(?(-?\d+(?:\.\d+)?)")


def magnitude(value: object) -> float:
    """The number a commented line shows: a magnitude, or a tuple's first item."""
    if isinstance(value, tuple):
        value = value[0]
    return float(getattr(value, "magnitude", value))  # type: ignore[arg-type]


def test_sea_water_guide_code_gives_the_values_it_states() -> None:
    guide = ROOT / "docs" / "sea-water.md"
    namespace: dict[str, object] = {}
    checked = []
    for block in python_blocks(guide):
        lines = block.splitlines()
        for statement in ast.parse(block).body:
            code = compile(ast.Module([statement], []), str(guide), "exec")
            if not isinstance(statement, ast.Expr):
                exec(code, namespace)  # noqa: S102
                continue
            value = eval(
                compile(ast.Expression(statement.value), str(guide), "eval"),
                namespace,
            )
            found = COMMENTED_VALUE.search(lines[statement.lineno - 1])
            if found is None:
                continue
            stated = found.group(1)
            digits = len(stated.partition(".")[2])
            assert magnitude(value) == pytest.approx(
                float(stated), abs=10.0**-digits
            ), lines[statement.lineno - 1]
            checked.append(stated)
    assert checked == ["34.99997", "0.981205", "0.98", "0.98", "3110.56", "0.351"]


def test_catalog_guide_personal_catalog_code_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nomogram.catalog import catalog

    # The file the guide assumes: a family of one formulation, my_key.
    (tmp_path / "my_family.toml").write_text(
        """
[catalog]
name = "my_family"
format = 2
requires = ["water-vapour"]

[references."my_family:src"]
authors = "A"
title = "T"
status = "verified"

[formulations."my_family:my_key"]
label = "A Magnus form"
expression = "C * exp(A * t / (B + t))"
fixed_units = true
output = { identifier = "e_s", kind = "SaturationVapourPressureOverWater", unit = "HectoPA", description = "e_s" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }]
coefficients = { A = 17.0, B = 240.0, C = 6.0 }

[[formulations."my_family:my_key".citations]]
reference = "my_family:src"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    guide = ROOT / "docs" / "catalog.md"
    blocks = python_blocks(guide)
    assert len(blocks) == 1
    namespace: dict[str, object] = {}
    exec(compile(blocks[0], str(guide), "exec"), namespace)  # noqa: S102
    mine = namespace["mine"]
    assert "my_family:my_key" in mine.formulations  # type: ignore[attr-defined]
    assert "my_family:my_key" not in catalog().formulations


ALOFT = ROOT / "docs" / "examples" / "humidity_aloft.py"
ALOFT_GUIDE = ROOT / "docs" / "humidity-aloft.md"


def test_humidity_aloft_example_is_the_script_that_draws_the_image() -> None:
    script = code_lines(ALOFT.read_text(encoding="utf-8"))
    (shown,) = python_blocks(ALOFT_GUIDE)
    for line in code_lines(shown):
        assert any(line in candidate for candidate in script), line


def test_humidity_aloft_example_writes_its_plot(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("humidity_aloft", ALOFT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "plot.png"
    module.main(str(output))
    assert output.read_bytes().startswith(b"\x89PNG")


def test_humidity_aloft_guide_gives_the_values_it_states() -> None:
    import matplotlib.pyplot as plt

    namespace: dict[str, Any] = {}
    for block in python_blocks(ALOFT_GUIDE):
        exec(compile(block, str(ALOFT_GUIDE), "exec"), namespace)  # noqa: S102
    plt.close("all")
    at_11_km = 110  # 0 to 12 km by steps of 0.1 km

    def at_11(mapping: Any) -> dict[str, Any]:
        return {key.split("[")[0]: value[at_11_km] for key, value in mapping.items()}

    def percent(table: Any) -> dict[str, float]:
        deviations = at_11(table.relative_deviations)
        return {key: round(100 * float(value), 2) for key, value in deviations.items()}

    def pascals(table: Any) -> dict[str, float]:
        return {
            key: value.to("Pa").magnitude for key, value in at_11(table.values).items()
        }

    saturation = percent(namespace["saturation"])
    assert saturation["hardy1998_water"] == -0.02
    assert saturation["metpy171_saturation_vapour_pressure"] == -0.64
    assert saturation["bolton1980"] == -2.33
    assert saturation["tetens1930"] == -7.75
    assert saturation["buck1996"] == -1.11
    assert saturation["murphy_koop2005_water"] == -3.36
    # Each curve stops where its source does: below 0, -45 and -50 degC.
    stopped = ("hyland_wexler1983", "sonntag1990_magnus", "goff_gratch1946")
    assert all(math.isnan(saturation[key]) for key in stopped)
    saturated = {
        key: round(value, 3) for key, value in pascals(namespace["saturation"]).items()
    }
    assert saturated["sonntag1990"] == 3.001
    assert saturated["hardy1998_water"] == 3.001
    assert saturated["metpy171_saturation_vapour_pressure"] == 2.982
    assert saturated["bolton1980"] == 2.931
    assert saturated["tetens1930"] == 2.769
    assert saturated["buck1996"] == 2.968
    assert saturated["murphy_koop2005_water"] == 2.900
    # Hyland and Wexler, extrapolated below 0 degC, gives 0.17 % more.
    f, Q_ = namespace["f"], namespace["Q_"]
    cold = Q_(-56.5, "degC").to("K")
    extrapolated = f["hyland_wexler1983"].evaluate(T=cold, outside="ignore")
    sonntag = f["sonntag1990"].evaluate(T=cold)
    assert round(100 * float(extrapolated / sonntag - 1), 2) == 0.17

    # The round trip: e = 0.50 f(T), Td = f^-1(e), then g(Td) and g(Td)/g(T).
    start = 0.5 * pascals(namespace["saturation"])["sonntag1990"]
    dew_point = namespace["inverse"].evaluate(e=Q_(start, "Pa"))
    assert round(dew_point.to("degC").magnitude, 1) == -62.1
    back = pascals(namespace["decoded"])
    assert abs(back["sonntag1990"] / start - 1) < 1e-9  # the strict round trip
    taken = {key: round(value, 3) for key, value in back.items()}
    assert taken["sonntag1990"] == 1.501
    assert taken["hardy1998_water"] == 1.500
    assert taken["metpy171_saturation_vapour_pressure"] == 1.488
    assert taken["bolton1980"] == 1.449
    assert taken["tetens1930"] == 1.349
    assert math.isnan(taken["sonntag1990_magnus"])
    decoded = percent(namespace["decoded"])
    assert decoded["hardy1998_water"] == -0.02
    assert decoded["metpy171_saturation_vapour_pressure"] == -0.84
    assert decoded["bolton1980"] == -3.46
    assert decoded["tetens1930"] == -10.07
    # The round trip widens the gap of the saturation 1.3 to 1.5 times.
    names = ("hardy1998_water", "metpy171_saturation_vapour_pressure", "bolton1980")
    gap_back = at_11(namespace["decoded"].relative_deviations)
    gap_air = at_11(namespace["saturation"].relative_deviations)
    widening = [gap_back[key] / gap_air[key] for key in (*names, "tetens1930")]
    assert (round(min(widening), 1), round(max(widening), 1)) == (1.3, 1.5)

    def humidity_back(table: Any, humidity: float) -> dict[str, float]:
        """g(Td)/g(T) in %, from the deviations of g(Td) and of g(T)."""
        at_dew_point = at_11(table.relative_deviations)
        at_air = at_11(namespace["saturation"].relative_deviations)
        return {
            key: round(100 * humidity * (1 + at_dew_point[key]) / (1 + at_air[key]), 2)
            for key in at_dew_point
            if key in at_air
        }

    humidities = humidity_back(namespace["decoded"], 0.5)
    assert humidities["sonntag1990"] == 50.00
    assert humidities["hardy1998_water"] == 50.00
    assert humidities["metpy171_saturation_vapour_pressure"] == 49.90
    assert humidities["bolton1980"] == 49.42
    assert humidities["tetens1930"] == 48.74
    # With Tetens' form, wider on e' in drier air, about the same in %RH.
    tetens = namespace["along"]("tetens1930", "Tetens (1930)", namespace["dew_point"])
    reference = namespace["back"]

    def tetens_at(humidity: float) -> Any:
        inputs = {
            **namespace["grid"],
            "RelativeHumidity": namespace["Q_"](humidity, ""),
        }
        return namespace["compare"]([reference, tetens], reference, inputs)

    assert percent(tetens_at(0.2))["tetens1930"] == -13.66
    assert percent(tetens_at(0.05))["tetens1930"] == -20.11
    gaps = [
        round(humidity_back(tetens_at(h), h)["tetens1930"] - 100 * h, 1)
        for h in (0.2, 0.3, 0.4, 0.6)
    ]
    assert (min(gaps), max(gaps)) == (-1.4, -1.1)
    junctions = percent(namespace["junctions"])
    assert junctions["iapws_r14_08_sublimation"] == -42.59
    assert junctions["metpy171_saturation_vapour_pressure_auto"] == -43.03
    assert junctions["ecmwf_ifs_saturation_mixed_phase"] == -42.66


DUCT = ROOT / "docs" / "examples" / "evaporation_duct.py"
DUCT_GUIDE = ROOT / "docs" / "evaporation-duct.md"


@pytest.fixture(scope="module")
def duct() -> Any:
    spec = importlib.util.spec_from_file_location("evaporation_duct", DUCT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def duct_results(duct: Any) -> dict[str, Any]:
    """The chain computed once for the module (some seconds)."""
    results: dict[str, Any] = duct.compute()
    return results


def test_evaporation_duct_guide_shows_lines_of_its_script() -> None:
    script = code_lines(DUCT.read_text(encoding="utf-8"))
    blocks = python_blocks(DUCT_GUIDE)
    assert len(blocks) == 2
    for block in blocks:
        for line in code_lines(block):
            assert any(line in candidate for candidate in script), line


def test_evaporation_duct_example_writes_its_plot(
    duct: Any,
    duct_results: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(duct, "compute", lambda: duct_results)
    output = tmp_path / "plot.png"
    duct.main(str(output))
    assert output.read_bytes().startswith(b"\x89PNG")


def test_evaporation_duct_guide_gives_the_values_it_states(
    duct_results: dict[str, Any],
) -> None:
    import numpy as np

    m, by_coare, by_ifs = (duct_results[k] for k in ("m", "coare", "ifs"))
    assert m["u"].size == 109
    assert (round(m["lat"].min()), round(m["lat"].max())) == (13, 16)
    assert round(float(np.median(m["tsnk"] - m["ta"])), 1) == 1.1
    assert (round(m["L"].min()), round(m["L"].max(), 1)) == (-326, -4.5)
    assert (round(m["u"].min(), 1), round(m["u"].max(), 1)) == (2.3, 12.4)

    def deviation(mine: Any, theirs: Any) -> float:
        return 100 * float(np.median(np.abs(mine / theirs - 1)))

    # The fixed point over the catalog against the outputs of COARE.
    assert round(deviation(by_coare["u_s"], m["usr"]), 2) == 0.02
    assert round(deviation(by_coare["z_0M"], m["zo"]), 2) == 0.05
    assert round(deviation(by_coare["L"], m["L"]), 1) == 0.6
    assert round(deviation(by_coare["q_s"], m["qsr"]), 1) == 0.8
    assert round(deviation(by_coare["T_s"], m["tsr"]), 1) == 0.9
    assert round(float(np.max(np.abs(by_coare["T_s"] - m["tsr"]))), 3) == 0.003

    def median(ratio: Any) -> int:
        return round(100 * float(np.median(ratio - 1)))

    # The IFS against COARE, on the same measurements.
    assert round(float(np.median(by_ifs["z_0M"] / by_coare["z_0M"]))) == 2
    assert median(by_ifs["u_s"] / by_coare["u_s"]) == 5
    assert median(by_ifs["L"] / by_coare["L"]) == 18
    assert median(by_ifs["T_s"] / by_coare["T_s"]) == -6
    assert median(by_ifs["q_s"] / by_coare["q_s"]) == -3

    heights = duct_results["heights"]
    lowest = heights["minimum of M, COARE 3.6"]
    assert (round(lowest.min(), 1), round(lowest.max(), 1)) == (7.7, 19.0)
    fairall = heights["z* of Fairall et al., COARE 3.6"]
    assert median(fairall / lowest) == 11
    assert median(heights["z* of Frederickson et al., COARE 3.6"] / lowest) == 9
    with_ifs = heights["z* of Fairall et al., IFS"]
    assert median(with_ifs / lowest) == 13
    assert median(with_ifs / fairall) == 1
    paulus_jeske = heights["Paulus-Jeske, measurements at 6 m"] / lowest
    assert median(paulus_jeske) == 65
    assert (
        round(100 * (paulus_jeske.min() - 1)),
        round(100 * (paulus_jeske.max() - 1)),
    ) == (
        46,
        74,
    )
