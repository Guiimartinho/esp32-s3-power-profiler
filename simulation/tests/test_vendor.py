from __future__ import annotations

import codecs
from pathlib import Path

import pytest

from circuit_sim.errors import ModelError
from circuit_sim.vendor import VENDOR_FOLDER, is_vendor, normalize_pspice, prepared_copy

# The byte order mark that some editors put in front of a file in UTF-8.
MARK = codecs.BOM_UTF8.decode("utf-8")
LOST = chr(0xFFFD)

# The head of a model as a manufacturer writes it for PSpice: tabs, lines
# that start with blanks, and parameters without their equals sign.
PSPICE = (
    "* OPA365 - Rev. B\r\n"
    "\t.SUBCKT OPA365 IN+ IN- VCC VEE OUT\r\n"
    "  .PARAM  GBW  50MEG\r\n"
    ".param\tvos\t100u ; typical\r\n"
    "   + PARAMS: RL=10k\r\n"
    "\r\n"
    "R1\tIN+\tIN-\t1e12  \r\n"
    ".ENDS"
)


@pytest.mark.parametrize(
    "library", ["vendor/ti-opa365.lib", "vendor/ti/opa365.lib", "vendor/OPAx197.LIB", "vendor"]
)
def test_a_file_in_the_vendor_folder_is_a_file_of_a_manufacturer(library: str) -> None:
    assert is_vendor(library)


@pytest.mark.parametrize(
    "library", ["opamps.lib", "open/vendor/opa365.lib", "vendors/opa365.lib", "Vendor/x.lib", ""]
)
def test_any_other_file_is_a_model_of_the_repository(library: str) -> None:
    assert not is_vendor(library)
    assert VENDOR_FOLDER == "vendor"


def test_a_pspice_file_is_brought_into_the_form_that_ngspice_reads() -> None:
    assert normalize_pspice(PSPICE) == (
        "* OPA365 - Rev. B\n"
        ".SUBCKT OPA365 IN+ IN- VCC VEE OUT\n"
        ".PARAM  GBW=50MEG\n"
        ".param vos=100u ; typical\n"
        "+ PARAMS: RL=10k\n"
        "\n"
        "R1 IN+ IN- 1e12\n"
        ".ENDS\n"
    )


def test_a_file_in_that_form_already_is_left_as_it_is() -> None:
    clean = normalize_pspice(PSPICE)

    assert normalize_pspice(clean) == clean
    assert normalize_pspice("") == "\n"


@pytest.mark.parametrize(
    ("line", "read"),
    [
        (".param ron 0.05", ".param ron=0.05"),
        (".PARAM VTH 1.7", ".PARAM VTH=1.7"),
        (".Param _k1 {2*pi*1k}", ".Param _k1={2*pi*1k}"),
        (".param gain {a + b}", ".param gain={a + b}"),
        (".param   x2   -3.3e-6", ".param   x2=-3.3e-6"),
    ],
)
def test_a_parameter_without_its_equals_sign_gets_one(line: str, read: str) -> None:
    assert normalize_pspice(line) == read + "\n"


@pytest.mark.parametrize(
    "line",
    [
        ".param ron=0.05",
        ".param ron = 0.05",
        ".param ron  =  0.05",
        ".param ron= 0.05",
        ".PARAM A=1 B=2",
        ".param f(x) = {2*x}",
        ".param ron",
        ".param",
        ".params ron 0.05",
        "* .param ron 0.05",
        "+ ron 0.05",
        "R1 a b 0.05",
        ".model D1N4148 D(IS=2.52n RS=0.568)",
    ],
)
def test_every_other_line_keeps_its_text(line: str) -> None:
    assert normalize_pspice(line) == line + "\n"


def test_no_value_is_changed() -> None:
    values = "1e12 50MEG 100u 0.568 2.52n {2*pi*1k} 3.3E-6 1.5K 10k"

    read = normalize_pspice(
        f"\t.param  total  {values}\n  X1\ta\tb\t{values.replace(' ', chr(9))}\n"
    )

    assert read == f".param  total={values}\nX1 a b {values}\n"


def test_a_byte_order_mark_at_the_start_of_the_text_is_dropped() -> None:
    model = "* LMR62014\n.SUBCKT LMR62014 1 2\n.ENDS\n"

    assert normalize_pspice(MARK + model) == model
    assert normalize_pspice(MARK + "\t  " + model) == model
    assert normalize_pspice(MARK) == "\n"
    # A text without the mark loses nothing at its start.
    assert normalize_pspice(model) == model


@pytest.mark.parametrize(
    ("line", "read"),
    [
        (
            "X_U2_U31         U2_N16667136 U2_N16667346 one_shot PARAMS: PARAMS:  T=20  ",
            "X_U2_U31         U2_N16667136 U2_N16667346 one_shot PARAMS:  T=20",
        ),
        ("X1 a b sub params: params: r=1k", "X1 a b sub params: r=1k"),
        ("X1 a b sub Params:\tPARAMS: r=1k", "X1 a b sub Params: r=1k"),
        ("+ PARAMS:PARAMS: r=1k c=1n", "+ PARAMS: r=1k c=1n"),
        (
            ".SUBCKT one_shot in out PARAMS: PARAMS: params: T=100",
            ".SUBCKT one_shot in out PARAMS: T=100",
        ),
    ],
)
def test_a_keyword_for_parameters_written_twice_in_a_row_is_written_once(
    line: str, read: str
) -> None:
    assert normalize_pspice(line) == read + "\n"


@pytest.mark.parametrize(
    "line",
    [
        "X1 a b sub PARAMS: r=1k",
        "X1 a b sub PARAMS: params=5",
        "X1 a b sub MYPARAMS: PARAMS: r=1k",
        "* PARAMS: the values after PARAMS: are those of the datasheet",
        ".SUBCKT sub a b PARAMS: r=1k",
    ],
)
def test_a_keyword_for_parameters_that_stands_once_is_left_alone(line: str) -> None:
    assert normalize_pspice(line) == line + "\n"


def test_the_copy_of_a_vendor_file_that_starts_with_a_byte_order_mark_starts_with_its_text(
    tmp_path: Path,
) -> None:
    (tmp_path / "vendor").mkdir()
    marked = (
        codecs.BOM_UTF8 + b"* LMR62014\r\n.SUBCKT LMR62014 1 2 PARAMS: PARAMS: T=20\r\n.ENDS\r\n"
    )
    (tmp_path / "vendor" / "lmr62014.lib").write_bytes(marked)

    copy = prepared_copy(tmp_path, "vendor/lmr62014.lib", tmp_path / "work")

    assert copy.read_bytes() == b"* LMR62014\n.SUBCKT LMR62014 1 2 PARAMS: T=20\n.ENDS\n"


def test_the_copy_of_a_vendor_file_is_written_beside_the_decks(tmp_path: Path) -> None:
    models = tmp_path / "models"
    work = tmp_path / ".work" / "vendor" / "chain"
    (models / "vendor").mkdir(parents=True)
    source = models / "vendor" / "ti-opa365.lib"
    source.write_bytes(PSPICE.encode("utf-8"))

    copy = prepared_copy(models, "vendor/ti-opa365.lib", work)

    assert copy == work / "vendor" / "ti-opa365.lib"
    assert copy.read_bytes() == normalize_pspice(PSPICE).encode("utf-8")
    # The file of the manufacturer itself is never changed.
    assert source.read_bytes() == PSPICE.encode("utf-8")
    # A second deck of the same run finds the folder there and writes the copy again.
    assert prepared_copy(models, "vendor/ti-opa365.lib", work) == copy


def test_a_vendor_file_in_another_encoding_is_still_read(tmp_path: Path) -> None:
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "old.lib").write_bytes(
        "* 10 µA, © 1998\n.param ib 10u\n".encode("latin-1")
    )

    copy = prepared_copy(tmp_path, "vendor/old.lib", tmp_path / "work")

    # The two letters that are no UTF-8 are shown as lost; the rest is read.
    assert copy.read_text(encoding="utf-8") == f"* 10 {LOST}A, {LOST} 1998\n.param ib=10u\n"


def test_a_vendor_file_that_is_not_present_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "vendor" / "ti-opa365.lib").mkdir(parents=True)

    with pytest.raises(
        ModelError,
        match=r"the model file vendor/mchp-mcp6561\.lib of the manufacturer is not present: "
        "such files are not part of the repository",
    ):
        prepared_copy(tmp_path, "vendor/mchp-mcp6561.lib", tmp_path / "work")
    # A folder of that name is not the file either.
    with pytest.raises(
        ModelError, match=r"vendor/ti-opa365\.lib of the manufacturer is not present"
    ):
        prepared_copy(tmp_path, "vendor/ti-opa365.lib", tmp_path / "work")
    assert not (tmp_path / "work").exists()
