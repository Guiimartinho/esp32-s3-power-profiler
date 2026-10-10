from __future__ import annotations

import pytest

from board_figures.errors import BoardError, BoardFiguresError, DefinitionError, DumpError


@pytest.mark.parametrize("error", [BoardError, DefinitionError, DumpError])
def test_every_error_derives_from_one_base(error: type[Exception]) -> None:
    assert issubclass(error, BoardFiguresError)

    with pytest.raises(BoardFiguresError, match="what went wrong"):
        raise error("what went wrong")
