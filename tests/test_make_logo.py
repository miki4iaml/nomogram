# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the logo script ``scripts/make_logo.py``."""

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from nomogram import _logo

SCRIPT = Path(__file__).parents[1] / "scripts" / "make_logo.py"
SPEC = importlib.util.spec_from_file_location("make_logo", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
make_logo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(make_logo)

IMAGES = Path(__file__).parents[1] / "docs" / "images"
SVG = "{http://www.w3.org/2000/svg}"


def test_the_images_are_those_the_script_draws() -> None:
    # Generated, never edited by hand: run the script after changing it.
    for name, text in make_logo.files().items():
        assert (IMAGES / name).read_text(encoding="utf-8") == text, name


@pytest.mark.parametrize("name", sorted(make_logo.files()))
def test_each_image_is_a_titled_svg(name: str) -> None:
    root = ET.fromstring(make_logo.files()[name])
    assert root.tag == f"{SVG}svg"
    title = root.find(f"{SVG}title")
    assert title is not None
    assert title.text == "nomogram"


def test_the_reading_line_crosses_the_diagonal_at_u_over_v() -> None:
    width, height = 64.0, _logo.H
    _, left, right = _logo.n_chart(0.0, 0.0, width)
    # The diagonal runs from (0, 0) to (width, height); the line through both
    # reading points meets it at a fraction s of its length, where w = s / (1 - s).
    slope = (right[1] - left[1]) / (right[0] - left[0])
    s = left[1] / (height - slope * width)
    assert s / (1 - s) == pytest.approx(_logo.U / _logo.V)


def test_the_logo_follows_the_theme_and_the_banners_do_not() -> None:
    files = make_logo.files()
    assert "prefers-color-scheme" in files["logo.svg"]
    for theme in ("light", "dark"):
        banner = files[f"banner-{theme}.svg"]
        assert "prefers-color-scheme" not in banner
        assert _logo.THEMES[theme]["ink"] in banner


def test_the_favicon_has_no_graduations() -> None:
    files = make_logo.files()
    assert 'class="fine"' in files["logo-icon.svg"]
    assert 'class="fine"' not in files["logo-favicon.svg"]


def test_main_writes_every_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    given = tmp_path / "given"
    assert make_logo.main(["make_logo.py", str(given)]) == 0
    assert sorted(p.name for p in given.iterdir()) == sorted(make_logo.files())
    # Without a directory, the default one (docs/images, here redirected).
    monkeypatch.setattr(make_logo, "DEFAULT_OUTPUT", tmp_path / "default")
    assert make_logo.main(["make_logo.py"]) == 0
    assert len(list((tmp_path / "default").iterdir())) == len(make_logo.files())
    assert "wrote" in capsys.readouterr().out
