# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

import nomogram


def test_hello() -> None:
    assert nomogram.hello() == "Hello from nomogram!"
