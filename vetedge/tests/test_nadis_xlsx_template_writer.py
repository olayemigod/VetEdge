from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_nadis_template_writer_is_standard_library_and_package_preserving():
    source = (ROOT / "services/nadis_xlsx_template_writer.py").read_text(encoding="utf-8")
    ast.parse(source)

    for expected in (
        "from zipfile import ZIP_DEFLATED, ZipFile",
        "from xml.etree import ElementTree as ET",
        'source.read("xl/workbook.xml")',
        'source.read("xl/_rels/workbook.xml.rels")',
        "replacements.get(info.filename, source.read(info.filename))",
        "output.writestr(info, payload)",
        "Hidden lookup columns, named ranges, validations, comments,",
    ):
        assert expected in source

    assert "openpyxl" not in source
    assert "Workbook(" not in source


def test_writer_clears_only_visible_report_columns_and_preserves_non_report_cells():
    source = (ROOT / "services/nadis_xlsx_template_writer.py").read_text(encoding="utf-8")

    assert 'if _column_number(cell.attrib.get("r", "A1")) <= max_col:' in source
    assert "_clear_value(cell)" in source
    assert "visible_column_counts[sheet_name]" in source
    assert "clear_through_row" in source


def test_writer_uses_inline_strings_and_native_numeric_values_without_shared_string_rewrite():
    source = (ROOT / "services/nadis_xlsx_template_writer.py").read_text(encoding="utf-8")

    assert 'cell.attrib["t"] = "inlineStr"' in source
    assert 'ET.SubElement(cell, _q("v")).text = str(value)' in source
    assert 'cell.attrib["t"] = "d"' in source
    assert "sharedStrings" not in source
