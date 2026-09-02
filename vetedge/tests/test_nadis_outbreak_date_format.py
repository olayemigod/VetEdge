from __future__ import annotations

import base64
import importlib.util
import re
from datetime import date
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
WRITER_PATH = ROOT / "services/nadis_xlsx_template_writer.py"
NADIS_TEMPLATE_DIR = ROOT / "templates" / "nadis"
OUTBREAK_TEMPLATE_B64 = NADIS_TEMPLATE_DIR / "NadisTemplate Disease Outbreak Report.xlsx.b64"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _load_writer_module():
    spec = importlib.util.spec_from_file_location("nadis_xlsx_template_writer_date_test", WRITER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _packaged_outbreak_template_bytes() -> bytes:
    return base64.b64decode(OUTBREAK_TEMPLATE_B64.read_text(encoding="ascii").strip(), validate=True)


def _outside_sheet_data(xml: bytes) -> tuple[bytes, bytes]:
    match = re.search(rb"<(?P<prefix>[A-Za-z_][\w.-]*:)?sheetData\b[^>]*>", xml)
    assert match is not None
    prefix = match.group("prefix") or b""
    closing = b"</" + prefix + b"sheetData>"
    closing_start = xml.index(closing, match.end())
    return xml[: match.start()], xml[closing_start + len(closing) :]


def _cell(row: ET.Element, ref: str) -> ET.Element:
    for cell in row.findall(f"{{{MAIN_NS}}}c"):
        if cell.attrib.get("r") == ref:
            return cell
    raise AssertionError(f"Missing generated cell {ref}")


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
    row = next(
        item for item in sheet_root.find(f"{{{MAIN_NS}}}sheetData").findall(f"{{{MAIN_NS}}}row")
        if item.attrib.get("r") == "5"
    )
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
