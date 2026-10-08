from __future__ import annotations

import importlib
from importlib import metadata, resources

import pytest

import s3_power_profiler

DISTRIBUTION = "s3-power-profiler"


def test_version_matches_the_installed_distribution() -> None:
    assert s3_power_profiler.__version__ == metadata.version(DISTRIBUTION)


def test_package_declares_that_it_is_typed() -> None:
    assert resources.files("s3_power_profiler").joinpath("py.typed").is_file()


def test_console_script_points_to_the_command_line_entry() -> None:
    scripts = metadata.entry_points(group="console_scripts")

    assert scripts["s3pp"].value == "s3_power_profiler.cli:main"


@pytest.mark.parametrize(
    "module_name",
    [
        "s3_power_profiler",
        "s3_power_profiler.capture",
        "s3_power_profiler.device",
        "s3_power_profiler.protocol",
        "s3_power_profiler.sim",
        "s3_power_profiler.transport",
    ],
)
def test_every_exported_name_exists(module_name: str) -> None:
    module = importlib.import_module(module_name)

    assert len(set(module.__all__)) == len(module.__all__)
    assert all(hasattr(module, name) for name in module.__all__)
