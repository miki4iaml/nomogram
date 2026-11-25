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
    assert len(blocks) == 3
    for block in blocks:
        # Whole statements, not a truncated call.
        ast.parse(block)
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

    # The system of the catalog against the outputs of COARE.
    assert round(deviation(by_coare["u_s"], m["usr"]), 2) == 0.02
    assert round(deviation(by_coare["z_0M"], m["zo"]), 2) == 0.04
    assert round(deviation(by_coare["L"], m["L"]), 1) == 0.5
    assert round(deviation(by_coare["q_s"], m["qsr"]), 1) == 0.8
    assert round(deviation(by_coare["T_s"], m["tsr"]), 2) == 0.01
    assert round(float(np.max(np.abs(by_coare["T_s"] - m["tsr"]))), 6) == 2.3e-5

    def median(ratio: Any) -> int:
        return round(100 * float(np.median(ratio - 1)))

    # The IFS against COARE, on the same measurements.
    assert round(float(np.median(by_ifs["z_0M"] / by_coare["z_0M"]))) == 2
    assert median(by_ifs["u_s"] / by_coare["u_s"]) == 6
    assert median(by_ifs["L"] / by_coare["L"]) == 20
    assert median(by_ifs["T_s"] / by_coare["T_s"]) == -6
    assert median(by_ifs["q_s"] / by_coare["q_s"]) == -3
    # The Charnock coefficients the comparison states.
    from nomogram.catalog import catalog
    from nomogram.units import Q_

    formulations = catalog().formulations
    edson = formulations["edson2013_charnock_coefficient"]
    assert round(float(edson.evaluate(U_10N=Q_(10.0, "m/s")).magnitude), 3) == 0.012
    roughness = formulations["ecmwf_ifs_roughness_length_momentum_sea"]
    assert {c.identifier: c.value for c in roughness.coefficients}["alpha_Ch"] == 0.018

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
    assert median(paulus_jeske) == 64
    assert (
        round(100 * (paulus_jeske.min() - 1)),
        round(100 * (paulus_jeske.max() - 1)),
    ) == (
        46,
        75,
    )


def test_evaporation_duct_guide_lists_the_references_of_its_chain(
    duct: Any, duct_results: dict[str, Any]
) -> None:
    text = DUCT_GUIDE.read_text(encoding="utf-8")
    section = text.split("\n## References\n", 1)[1]
    listed = [line for line in section.splitlines() if line.startswith("- ")]
    assert listed == duct.bibliography(duct_results["called"])
    assert any("COARE 3.6 bulk flux algorithm" in line for line in listed)


COARE_SCRIPT = ROOT / "docs" / "examples" / "coare_system.py"
COARE_GUIDE = ROOT / "docs" / "coare-system.md"
SUPERSCRIPTS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def scientific(value: float) -> str:
    """A value as the guide writes it, two significant digits: 5.6 × 10⁻⁷."""
    mantissa, exponent = f"{value:.1e}".split("e")
    return f"{mantissa} × 10{str(int(exponent)).translate(SUPERSCRIPTS)}"


@pytest.fixture(scope="module")
def coare() -> Any:
    spec = importlib.util.spec_from_file_location("coare_system", COARE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def coare_results(coare: Any) -> dict[str, Any]:
    """The system solved once for the module."""
    results: dict[str, Any] = coare.compute()
    return results


def test_coare_guide_gives_the_values_it_states(
    coare: Any, coare_results: dict[str, Any]
) -> None:
    import numpy as np

    text = COARE_GUIDE.read_text(encoding="utf-8")
    # The equations of the table, in the order of the system, as nomogram
    # writes them in the notation of the page.
    rows = re.findall(r"\| `([a-z0-9_]+)` \|$", text, flags=re.MULTILINE)
    assert rows == [e.formulation.key for e in coare.SYSTEM.equations]
    for equation in coare.equations():
        assert f"$`{equation}`$" in text, equation
    assert len(coare.SYSTEM.unknowns) == 5
    assert text.count("**unknown**") == 5
    assert len(coare.SYSTEM.inputs) == 11
    m, solution = coare_results["m"], coare_results["solution"]
    assert m["u"].size == 109
    assert round(float(m["u"][coare.EXAMPLE]), 1) == 12.1
    # Three steps for most measurements, four at most.
    steps = np.asarray(solution.iterations)
    assert int(steps.max()) == 4
    assert np.sum(steps == 3) > np.sum(steps == 4)
    assert float(np.max(solution.residual)) <= 1e-12
    assert round(math.log10(coare_results["passes"][-1])) == -10
    for name, (column, _) in coare.COMPARED.items():
        largest, median = coare_results["deviations"][name]
        code, mine = (v.replace("-", "\u2212") for v in coare_results["example"][name])
        row = (
            f"| `{column}` | {code} | {mine} | {scientific(largest)} | "
            f"{scientific(median)} |"
        )
        assert row in text, row
    assert (round(float(m["tsr"].min()), 2), round(float(m["tsr"].max()), 3)) == (
        -0.10,
        -0.002,
    )
    assert (round(m["L"].min()), round(m["L"].max(), 1)) == (-326, -4.5)


def test_coare_guide_points_to_its_script_and_figure() -> None:
    text = COARE_GUIDE.read_text(encoding="utf-8")
    assert "(examples/coare_system.py)" in text
    assert re.search(r"!\[[^]]+\]\(images/coare-system\.png\)", text)
    assert (ROOT / "docs" / "images" / "coare-system.png").exists()
    assert python_blocks(COARE_GUIDE) == []


def test_coare_example_writes_its_plot(
    coare: Any,
    coare_results: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(coare, "compute", lambda: coare_results)
    output = tmp_path / "plot.png"
    coare.main(str(output))
    assert output.read_bytes().startswith(b"\x89PNG")


GRAPH_FIGURES = ROOT / "docs" / "examples" / "graph_figures.py"
IMAGES = ROOT / "docs" / "images"
FIGURES = {
    "coare-loop": ROOT / "docs" / "coare-system.md",
    "kinds-relative-humidity": ROOT / "docs" / "graphs.md",
    "kinds-contrail": ROOT / "docs" / "contrails.md",
    "contrail-chain": ROOT / "docs" / "contrails.md",
}


def projection(svg: str) -> list[tuple[str, ...]]:
    """What a figure shows, without where: each element with its colours,
    its dashes, its text and its tooltip. Graphviz measures text with the fonts of the
    workstation, so that positions and sizes differ from one system to
    another; what is drawn does not."""
    from xml.etree import ElementTree

    rows: list[tuple[str, ...]] = []
    for element in ElementTree.fromstring(svg).iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "image":
            rows.append((tag,))
            continue
        rows.append(
            (
                tag,
                element.get("fill", ""),
                element.get("stroke", ""),
                element.get("stroke-dasharray", ""),
                (element.text or "").strip(),
                element.get("{http://www.w3.org/1999/xlink}title", ""),
            )
        )
    return rows


@pytest.fixture(scope="module")
def drawn(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The figures drawn anew, in a process of their own: a crash of
    Graphviz then fails the tests instead of the whole run."""
    import subprocess
    import sys

    directory = tmp_path_factory.mktemp("figures")
    done = subprocess.run(
        [sys.executable, str(GRAPH_FIGURES), str(directory)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return directory


@pytest.mark.parametrize("name", sorted(FIGURES))
@pytest.mark.parametrize("suffix", ["", "-dark"])
def test_figures_of_the_graphs_are_those_the_script_draws(
    drawn: Path, name: str, suffix: str
) -> None:
    file = f"{name}{suffix}.svg"
    committed = (IMAGES / file).read_text(encoding="utf-8")
    assert projection((drawn / file).read_text(encoding="utf-8")) == projection(
        committed
    )
    assert f"images/{file}" in FIGURES[name].read_text(encoding="utf-8")


def test_the_loop_figure_follows_the_table_of_the_guide(drawn: Path) -> None:
    from xml.etree import ElementTree

    from nomogram.catalog import catalog

    system = catalog().systems["coare36_surface_layer"]
    root = ElementTree.fromstring(
        (drawn / "coare-loop.svg").read_text(encoding="utf-8")
    )
    texts = [(e.text or "").strip() for e in root.iter() if e.tag.endswith("}text")]
    # Each equation numbered as the row of the table that gives its variable.
    for rank, equation in enumerate(system.equations, start=1):
        assert any(t.startswith(f"({rank}) {equation.output}") for t in texts), rank
    assert any(f"{system.iterations} passes in the code" in t for t in texts)
    # The seven reads that close the loop are the dashed edges of the figure.
    dashed = [
        group
        for group in root.iter()
        if group.get("class") == "edge"
        and group.get("id", "").startswith("figure-")
        and any(e.get("stroke-dasharray") for e in group)
    ]
    assert len(dashed) == 7


CONTRAILS = ROOT / "docs" / "examples" / "contrails.py"
CONTRAILS_GUIDE = ROOT / "docs" / "contrails.md"


@pytest.fixture(scope="module")
def contrails() -> Any:
    spec = importlib.util.spec_from_file_location("contrails", CONTRAILS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def contrail_results(contrails: Any) -> dict[str, Any]:
    """The values computed once for the module (some seconds)."""
    results: dict[str, Any] = contrails.compute()
    return results


def test_contrails_guide_shows_lines_of_its_script() -> None:
    script = code_lines(CONTRAILS.read_text(encoding="utf-8"))
    blocks = python_blocks(CONTRAILS_GUIDE)
    assert len(blocks) == 3
    for block in blocks:
        ast.parse(block)
        for line in code_lines(block):
            assert any(line in candidate for candidate in script), line


def test_contrails_example_writes_its_plots(
    contrails: Any,
    contrail_results: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contrails, "compute", lambda: contrail_results)
    contrails.main(str(tmp_path))
    for name in ("diagram", "profile", "appleman"):
        figure = tmp_path / f"contrails-{name}.png"
        assert figure.read_bytes().startswith(b"\x89PNG")
        assert f"images/contrails-{name}.png" in CONTRAILS_GUIDE.read_text(
            encoding="utf-8"
        )


def test_contrails_guide_gives_the_values_it_states(
    contrail_results: dict[str, Any],
) -> None:
    import numpy as np

    d = contrail_results["diagram"]
    stated = {
        "T_LM": -42.91,
        "T_LC": -50.64,
        "T_IM": -39.76,
        "T_IC": -45.67,
        "L1": -32.42,
        "L2": -57.93,
        "I1": -27.88,
        "I2": -58.77,
    }
    assert {name: round(d[name], 2) for name in stated} == stated
    layers = contrail_results["profile"]["layers"]
    assert tuple(round(v, 1) for v in layers[0.0]) == (10.1, 14.0)
    assert {u: round(layers[u][0], 1) for u in (0.3, 0.6, 1.0)} == {
        0.3: 9.9,
        0.6: 9.6,
        1.0: 8.2,
    }
    a = contrail_results["appleman"]
    gap = {f_w: a["highest"][f_w] - a["tangent"][f_w] for f_w in (0, 60, 90, 100)}
    assert max(float(np.abs(v).max()) for v in gap.values()) < 0.23
    below = max(float(gap[f_w].max()) for f_w in (0, 60, 90))
    assert round(below, 2) == 0.18
    assert round(float(gap[100].min()), 2) == -0.22
    assert (gap[100] < 0).all()


def test_contrails_guide_lists_the_references_of_its_formulations(
    contrails: Any, contrail_results: dict[str, Any]
) -> None:
    text = CONTRAILS_GUIDE.read_text(encoding="utf-8")
    section = text.split("\n## References\n", 1)[1]
    listed = [line for line in section.splitlines() if line.startswith("- ")]
    assert listed == contrails.bibliography(contrail_results["called"])
    assert any("Douglas, T. B." in line for line in listed)
