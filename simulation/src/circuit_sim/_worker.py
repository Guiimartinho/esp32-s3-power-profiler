"""Child process that runs one deck in the ngspice shared library.

Usage: python -m circuit_sim._worker <deck.cir> <out.npz> <library> [--psa]
                                     [--codemodels <dir>]

The library keeps its state in the process that loads it and can take the
process down with it, so every deck runs in a process of its own. The deck is
loaded with ``source``; its ``.control`` section runs the analyses. Afterward
every vector of every plot is written to the output file under the name
``<plot>/<vector>``, and one line of JSON with the log goes to standard
output. The exit code is 0 when the library accepted the deck and 3 when it
did not; what the log says is judged by the caller.

This module is the only one that touches the library. It is outside the
coverage measurement because it cannot run on a machine without ngspice.
"""

from __future__ import annotations

import ctypes
import json
import os
import pathlib
import sys

import numpy as np

# The code models of XSPICE that the decks may use. The transmission line
# models are left out: the bundle of KiCad 10 fails to load them.
_CODE_MODELS = ("spice2poly", "analog", "digital", "xtradev", "xtraevt", "table")

_REAL = 1
_COMPLEX = 2

# The callbacks that the library is given: for what it prints and for its
# progress, for its wish to leave, and for the state of its background thread.
_PRINTER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_LEAVER = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p
)
_RUNNER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)


class _Complex(ctypes.Structure):
    _fields_ = (("real", ctypes.c_double), ("imag", ctypes.c_double))


class _VectorInfo(ctypes.Structure):
    _fields_ = (
        ("name", ctypes.c_char_p),
        ("type", ctypes.c_int),
        ("flags", ctypes.c_short),
        ("real", ctypes.POINTER(ctypes.c_double)),
        ("complex", ctypes.POINTER(_Complex)),
        ("length", ctypes.c_int),
    )


def _names(pointer: ctypes._Pointer[ctypes.c_char_p] | None) -> list[str]:
    """The strings of a NULL-terminated array that the library returned."""
    names: list[str] = []
    if not pointer:
        return names
    index = 0
    while pointer[index]:
        names.append(pointer[index].decode("utf-8", "replace"))
        index += 1
    return names


def _word(name: str) -> str:
    """A file name as one word of a command of the library.

    A name with a blank in it goes in single quotes, the only way of quoting
    that the library takes for a file name: KiCad installs itself under
    ``Program Files`` on Windows. Any other name stays as it is.
    """
    return f"'{name}'" if any(char.isspace() for char in name) else name


def main(argv: list[str]) -> int:
    """Run the deck named on the command line and write its vectors."""
    flags = {arg for arg in argv if arg.startswith("--") and arg != "--codemodels"}
    codemodels: pathlib.Path | None = None
    if "--codemodels" in argv:
        codemodels = pathlib.Path(argv[argv.index("--codemodels") + 1])
        argv = [arg for i, arg in enumerate(argv) if i not in (argv.index("--codemodels") + 1,)]
    args = [arg for arg in argv if not arg.startswith("--")]
    deck, out, library = (pathlib.Path(arg).resolve() for arg in args[:3])

    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(library.parent))
    ng = ctypes.CDLL(str(library))
    log: list[str] = []

    def on_char(text: bytes, _ident: int, _user: object) -> int:
        line = text.decode("utf-8", "replace")
        for prefix in ("stdout ", "stderr "):
            if line.startswith(prefix):
                line = line[len(prefix) :]
                break
        log.append(line)
        return 0

    def on_stat(_text: bytes, _ident: int, _user: object) -> int:
        return 0

    def on_exit(_status: int, _immediate: bool, _quit: bool, _ident: int, _user: object) -> int:
        return 0

    def on_background(_running: bool, _ident: int, _user: object) -> int:
        return 0

    # The library keeps these pointers for as long as it is loaded: they stay
    # in names of this function, which does not return before the run is over.
    printer, progress = _PRINTER(on_char), _PRINTER(on_stat)
    leaver, runner = _LEAVER(on_exit), _RUNNER(on_background)
    ng.ngSpice_Init(printer, progress, leaver, None, None, runner, None)
    ng.ngSpice_Command.argtypes = [ctypes.c_char_p]
    ng.ngSpice_AllPlots.restype = ctypes.POINTER(ctypes.c_char_p)
    ng.ngSpice_AllVecs.argtypes = [ctypes.c_char_p]
    ng.ngSpice_AllVecs.restype = ctypes.POINTER(ctypes.c_char_p)
    ng.ngGet_Vec_Info.argtypes = [ctypes.c_char_p]
    ng.ngGet_Vec_Info.restype = ctypes.POINTER(_VectorInfo)

    def command(text: str) -> int:
        return int(ng.ngSpice_Command(text.encode("utf-8")))

    if codemodels is not None:
        for name in _CODE_MODELS:
            path = codemodels / f"{name}.cm"
            if path.exists():
                command(f"codemodel {_word(path.as_posix())}")
    if "--psa" in flags:
        command("set ngbehavior=psa")
    command("version -f")
    version = next((line for line in log if "ngspice-" in line), "")
    os.chdir(deck.parent)
    status = command(f"source {_word(deck.name)}")

    vectors: dict[str, np.ndarray] = {}
    for plot in _names(ng.ngSpice_AllPlots()):
        if plot == "const":
            continue
        for name in _names(ng.ngSpice_AllVecs(plot.encode("utf-8"))):
            info = ng.ngGet_Vec_Info(f"{plot}.{name}".encode())
            if not info or info.contents.length <= 0:
                continue
            length = info.contents.length
            if info.contents.flags & _COMPLEX and info.contents.complex:
                raw = np.ctypeslib.as_array(
                    ctypes.cast(info.contents.complex, ctypes.POINTER(ctypes.c_double)),
                    shape=(2 * length,),
                )
                vectors[f"{plot}/{name}"] = raw[0::2] + 1j * raw[1::2]
            elif info.contents.real:
                vectors[f"{plot}/{name}"] = np.ctypeslib.as_array(
                    info.contents.real, shape=(length,)
                ).copy()
    np.savez_compressed(out, **vectors)  # type: ignore[arg-type]
    report = {"version": version.strip(" *"), "status": status, "log": log}
    sys.stdout.write(json.dumps(report) + "\n")
    sys.stdout.flush()
    return 0 if status == 0 else 3


if __name__ == "__main__":
    # The library does not always let the interpreter leave in an orderly way.
    os._exit(main(sys.argv[1:]))
