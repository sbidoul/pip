"""Basic CLI functionality checks.
"""
from textwrap import dedent

import pytest

from tests.lib import PipTestEnvironment


@pytest.mark.parametrize(
    "entrypoint",
    [
        ("fake_pip = pip._internal.main:main",),
        ("fake_pip = pip._internal:main",),
        ("fake_pip = pip:main",),
    ],
)
def test_entrypoints_work(entrypoint: str, script: PipTestEnvironment) -> None:
    if script.zipapp:
        pytest.skip("Zipapp does not include entrypoints")

    fake_pkg = script.temp_path / "fake_pkg"
    fake_pkg.mkdir()
    fake_pkg.joinpath("setup.py").write_text(
        dedent(
            """
    from setuptools import setup

    setup(
        name="fake-pip",
        version="0.1.0",
        entry_points={{
            "console_scripts": [
                {!r}
            ]
        }}
    )
    """.format(
                entrypoint
            )
        )
    )

    # expect_temp because pip install will generate fake_pkg.egg-info
    script.pip("install", "-vvv", str(fake_pkg), expect_temp=True)
    result = script.pip("-V")
    result2 = script.run("fake_pip", "-V", allow_stderr_warning=True)
    assert result.stdout == result2.stdout
    assert "old script wrapper" in result2.stderr
