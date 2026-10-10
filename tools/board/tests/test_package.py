from __future__ import annotations

import re
from importlib import metadata, resources

import board_figures


def test_the_version_is_the_one_of_the_repository_before_or_at_a_release() -> None:
    # One version covers firmware, host software and tools; between releases
    # it carries a development suffix, as the host package does.
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", board_figures.__version__)


def test_the_installed_distribution_has_the_same_version() -> None:
    assert metadata.version("board-figures") == board_figures.__version__


def test_the_package_ships_its_type_marker() -> None:
    assert resources.files("board_figures").joinpath("py.typed").is_file()
