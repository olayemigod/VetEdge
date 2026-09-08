from __future__ import annotations

import ast
import base64
import importlib.util
import re
from datetime import date
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
WRITER_PATH = ROOT / "services/nadis_xlsx_template_writer.py"
NADIS_TEMPLATE_DIR = ROOT / "templates" / "nadis"
VACCINATION_TEMPLATE_PART_PATTERN = "Nadis Template Vaccination Report 1.xlsx.b64.part*"
OUTBREAK_TEMPLATE_B64 = NADIS_TEMPLATE_DIR / "NadisTemplate Disease Outbreak Report.xlsx.b64"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


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


def _packaged_vaccination_template_bytes() -> bytes:
    parts = sorted(NADIS_TEMPLATE_DIR.glob(VACCINATION_TEMPLATE_PART_PATTERN))
    assert parts, "Packaged official NADIS vaccination template chunks are required"
    payload = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    return base64.b64decode(payload)


def _packaged_outbreak_template_bytes() -> bytes:
    return base64.b64decode(OUTBREAK_TEMPLATE_B64.read_text(encoding="ascii").strip(), validate=True)


def _outside_sheet_data(xml: bytes) -> tuple[bytes, bytes]:
    start = xml.index(b"<sheetData")
    closing = b"</sheetData>"
    end = xml.index(closing, start) + len(closing)
    return xml[:start], xml[end:]


def _cell(row: ET.Element, ref: str) -> ET.Element:
    for cell in row.findall(f"{{{MAIN_NS}}}c"):
        if cell.attrib.get("r") == ref:
            return cell
    raise AssertionError(f"Missing generated cell {ref}")


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


def test_packaged_vaccination_template_keeps_official_worksheet_envelope_after_population():
    writer = _load_writer_module()
    template = _packaged_vaccination_template_bytes()

    with ZipFile(BytesIO(template), "r") as archive:
        sheet_path = writer._sheet_paths(archive)["Vaccinations"]
        original_sheet = archive.read(sheet_path)
        original_parts = {info.filename: archive.read(info.filename) for info in archive.infolist() if info.filename != sheet_path}

    generated = writer.populate_official_template(
        template,
        sheet_rows={
            "Vaccinations": [[
                None,
                1,
                "Nigeria",
                "Lagos, Nigeria",
                "Ikeja, Nigeria",
                2026,
                "August",
                "Preventive/Routine vaccination",
                "Dog",
                "Rabies",
                1,
                "Rabies",
                "Inactivated vaccines",
                "QA source",
                "QA-BATCH-1",
                "No",
            ]]
        },
        start_row=5,
        visible_column_counts={"Vaccinations": 16},
        clear_through_row=239,
    )

    with ZipFile(BytesIO(generated), "r") as archive:
        assert archive.testzip() is None
        generated_sheet = archive.read(sheet_path)
        for filename, payload in original_parts.items():
            assert archive.read(filename) == payload, f"Unexpected package rewrite: {filename}"

    assert _outside_sheet_data(generated_sheet) == _outside_sheet_data(original_sheet)
    assert b"Lagos, Nigeria" in generated_sheet
    assert b"Preventive/Routine vaccination" in generated_sheet
    assert b"Rabies" in generated_sheet


def test_packaged_outbreak_dates_are_native_excel_dates_with_dd_mm_yyyy_format():
    writer = _load_writer_module()
    template = _packaged_outbreak_template_bytes()
    report_date = date(2026, 9, 1)

    with ZipFile(BytesIO(template), "r") as archive:
        sheet_path = writer._sheet_paths(archive)["Outbreaks"]
        original_sheet = archive.read(sheet_path)
        original_parts = {
            info.filename: archive.read(info.filename)
            for info in archive.infolist()
            if info.filename not in {sheet_path, "xl/styles.xml"}
        }

    generated = writer.populate_official_template(
        template,
        sheet_rows={
            "Outbreaks": [[
                None,
                "VDO-QA-DATE-001",
                "Nigeria",
                "Lagos, Nigeria",
                2026,
                "September",
                "Rabies",
                None,
                "New outbreak",
                1,
                1,
                report_date,
                report_date,
                report_date,
                report_date,
                "Airborne spread",
                "Continuing",
            ]]
        },
        start_row=5,
        visible_column_counts={"Outbreaks": 17},
        clear_through_row=252,
    )

    with ZipFile(BytesIO(generated), "r") as archive:
        assert archive.testzip() is None
        generated_sheet = archive.read(sheet_path)
        styles_xml = archive.read("xl/styles.xml")
        for filename, payload in original_parts.items():
            assert archive.read(filename) == payload, f"Unexpected package rewrite: {filename}"

    assert _outside_sheet_data(generated_sheet) == _outside_sheet_data(original_sheet)

    sheet_root = ET.fromstring(generated_sheet)
    sheet_data = sheet_root.find(f"{{{MAIN_NS}}}sheetData")
    assert sheet_data is not None
    row = next(item for item in sheet_data.findall(f"{{{MAIN_NS}}}row") if item.attrib.get("r") == "5")
    styles_root = ET.fromstring(styles_xml)
    num_fmts_node = styles_root.find(f"{{{MAIN_NS}}}numFmts")
    custom_formats = {
        int(item.attrib["numFmtId"]): item.attrib.get("formatCode")
        for item in (num_fmts_node.findall(f"{{{MAIN_NS}}}numFmt") if num_fmts_node is not None else [])
    }
    cell_xfs = styles_root.find(f"{{{MAIN_NS}}}cellXfs")
    assert cell_xfs is not None
    xfs = cell_xfs.findall(f"{{{MAIN_NS}}}xf")

    assert writer._excel_date_serial(report_date) == 46266
    for ref in ("L5", "M5", "N5", "O5"):
        cell = _cell(row, ref)
        value = cell.find(f"{{{MAIN_NS}}}v")
        assert value is not None and value.text == "46266"
        assert cell.attrib.get("t") is None
        style_index = int(cell.attrib["s"])
        num_fmt_id = int(xfs[style_index].attrib.get("numFmtId", "0"))
        assert custom_formats.get(num_fmt_id) == "dd/mm/yyyy"
