"""Model files of the manufacturers, made readable for ngspice.

The manufacturers write their models for PSpice. ngspice reads most of that
dialect in its compatibility mode, with a few exceptions that are plain
matters of form. :func:`normalize_pspice` removes them without touching a
value, and :func:`prepared_copy` keeps the result beside the decks of a run:
the file of the manufacturer itself is never changed, and never becomes part
of the repository.
"""

from __future__ import annotations

import codecs
import pathlib
import re

from circuit_sim.errors import ModelError

VENDOR_FOLDER = "vendor"
"""Folder inside the models folder that holds the files of the manufacturers."""

# The mark that some editors put in front of a file in UTF-8, as it reads
# once the file is decoded.
_BYTE_ORDER_MARK = codecs.BOM_UTF8.decode("utf-8")

# ".param name value" without the equals sign that ngspice asks for.
_BARE_PARAM = re.compile(r"^(\.param\s+)([A-Za-z_]\w*)\s+(?!=)(\S.*)$", re.IGNORECASE)

# The keyword in front of the parameters of a subcircuit, written twice or
# more in a row.
_DOUBLED_PARAMS = re.compile(r"\b(params:)(?:\s*params:)+", re.IGNORECASE)


def is_vendor(library: str) -> bool:
    """Whether a model file of the model map is a file of a manufacturer."""
    return pathlib.PurePosixPath(library).parts[:1] == (VENDOR_FOLDER,)


def normalize_pspice(text: str) -> str:
    """The text of a PSpice model file in the form that ngspice reads.

    Five changes of form, none of a value:

    - a byte order mark at the start of the text goes: with it the first
      line is not the comment or the statement that it is meant to be;
    - tabs become spaces;
    - blanks in front of a line go (ngspice takes a line that starts with a
      blank for a continuation of nothing);
    - a ``.param name value`` line gets its equals sign;
    - the keyword ``PARAMS:`` written twice or more in a row on a line, in
      any letter case, is written once, as its first writing has it.
    """
    lines = []
    for raw in text.removeprefix(_BYTE_ORDER_MARK).replace("\t", " ").splitlines():
        line = raw.strip()
        match = _BARE_PARAM.match(line)
        if match is not None:
            line = f"{match.group(1)}{match.group(2)}={match.group(3)}"
        lines.append(_DOUBLED_PARAMS.sub(r"\1", line))
    return "\n".join(lines) + "\n"


def prepared_copy(models_dir: pathlib.Path, library: str, workdir: pathlib.Path) -> pathlib.Path:
    """Write the normalized copy of a vendor file beside the decks of a run.

    Args:
        models_dir: The models folder.
        library: The file as the model map names it (``vendor/<file>``).
        workdir: The folder in which the decks run.

    Returns:
        The path of the copy, inside ``workdir``.

    Raises:
        ModelError: When the file of the manufacturer is not present.
    """
    source = models_dir / library
    if not source.is_file():
        raise ModelError(
            f"the model file {library} of the manufacturer is not present: such files "
            "are not part of the repository"
        )
    target = workdir / VENDOR_FOLDER / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    text = normalize_pspice(source.read_text(encoding="utf-8", errors="replace"))
    target.write_text(text, encoding="utf-8", newline="\n")
    return target
