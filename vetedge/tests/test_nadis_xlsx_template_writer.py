from __future__ import annotations

import ast
import importlib.util
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
WRITER_PATH = ROOT / "services/nadis_xlsx_template_writer.py"


def _load_writer_module():
    spec = importlib.util.spec_from_file_location("nadis_xlsx_template_writer_under_test", WRITER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _official_style_template_bytes() -> bytes:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    mc_ns = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    x14ac_ns = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{main_ns}" xmlns:r="{rel_ns}">'
        '<sheets><sheet name="Vaccinations" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    ).encode()
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{pkg_rel_ns}">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    ).encode()
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{main_ns}" xmlns:r="{rel_ns}" '
        f'xmlns:mc="{mc_ns}" xmlns:x14ac="{x14ac_ns}" mc:Ignorable="x14ac">'
        '<dimension ref="A1:B20"/>'
        '<sheetData><row r="5"><c r="A5" s="1" t="inlineStr"><is><t>old</t></is></c>'
        '<c r="B5" s="2" t="inlineStr"><is><t>old-2</t></is></c></row></sheetData>'
        f'<extLst><ext uri="test"><x14ac:absPath xmlns:x14ac="{x14ac_ns}" url="C:/NADIS"/>'
        '</ext></extLst></worksheet>'
    ).encode()

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
        archive.writestr("docProps/custom.xml", b"official-package-part")
    return output.getvalue()


def _outside_sheet_data(xml: bytes) -> tuple[bytes, bytes]:
    start = xml.index(b"<sheetData")
    closing = b"</sheetData>"
    end = xml.index(closing, start) + len(closing)
    return xml[:start], xml[end:]


def test_nadis_template_writer_is_standard_library_and_package_preserving():
    source = WRITER_PATH.read_text(encoding="utf-8")
    ast.parse(source)

    for expected in (
        "from zipfile import ZIP_DEFLATED, ZipFile",
        "from xml.etree import ElementTree as ET",
        'source.read("xl/workbook.xml")',
        'source.read("xl/_rels/workbook.xml.rels")',
        "replacements.get(info.filename, source.read(info.filename))",
        "output.writestr(info, payload)",
        "Hidden lookup columns, named ranges, validations, comments,",
        "_replace_sheet_data_xml(sheet_xml, sheet_data)",
    ):
        assert expected in source

    assert "openpyxl" not in source
    assert "Workbook(" not in source
    assert 'ET.tostring(root, encoding="utf-8", xml_declaration=True)' not in source


def test_writer_clears_only_visible_report_columns_and_preserves_non_report_cells():
    source = WRITER_PATH.read_text(encoding="utf-8")

    assert 'if _column_number(cell.attrib.get("r", "A1")) <= max_col:' in source
    assert "_clear_value(cell)" in source
    assert "visible_column_counts[sheet_name]" in source
    assert "clear_through_row" in source


def test_writer_uses_inline_strings_and_native_numeric_values_without_shared_string_rewrite():
    source = WRITER_PATH.read_text(encoding="utf-8")

    assert 'cell.attrib["t"] = "inlineStr"' in source
    assert 'ET.SubElement(cell, _q("v")).text = str(value)' in source
    assert 'cell.attrib["t"] = "d"' in source
    assert "sharedStrings" not in source


def test_writer_preserves_excel_namespace_envelope_and_untouched_package_parts():
    writer = _load_writer_module()
    template = _official_style_template_bytes()

    with ZipFile(BytesIO(template), "r") as archive:
        original_sheet = archive.read("xl/worksheets/sheet1.xml")
        original_custom = archive.read("docProps/custom.xml")

    generated = writer.populate_official_template(
        template,
        sheet_rows={"Vaccinations": [["Rabies", 1]]},
        start_row=5,
        visible_column_counts={"Vaccinations": 2},
        clear_through_row=20,
    )

    with ZipFile(BytesIO(generated), "r") as archive:
        assert archive.testzip() is None
        generated_sheet = archive.read("xl/worksheets/sheet1.xml")
        assert archive.read("docProps/custom.xml") == original_custom

    assert _outside_sheet_data(generated_sheet) == _outside_sheet_data(original_sheet)
    assert b'mc:Ignorable="x14ac"' in generated_sheet
    assert b'xmlns:x14ac="http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"' in generated_sheet
    assert b"Rabies" in generated_sheet
    assert b"old-2" not in generated_sheet
