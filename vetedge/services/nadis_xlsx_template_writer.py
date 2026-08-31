from __future__ import annotations

import re
from copy import deepcopy
from datetime import date, datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_SHEET_DATA_OPEN_RE = re.compile(rb"<(?P<prefix>[A-Za-z_][\w.-]*:)?sheetData\b[^>]*>")
ET.register_namespace("", _MAIN_NS)
ET.register_namespace("r", _REL_NS)


def _q(local: str) -> str:
    return f"{{{_MAIN_NS}}}{local}"


def _column_number(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - 64)
    return value


def _column_letters(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_paths(source: ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(source.read("xl/workbook.xml"))
    relationships = ET.fromstring(source.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in relationships.findall(f"{{{_PKG_REL_NS}}}Relationship")
    }
    result: dict[str, str] = {}
    sheets = workbook.find(_q("sheets"))
    if sheets is None:
        return result
    for sheet in sheets:
        rel_id = sheet.attrib[f"{{{_REL_NS}}}id"]
        target = rel_map[rel_id].lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        result[sheet.attrib["name"]] = target
    return result


def _find_row(sheet_data: ET.Element, row_number: int) -> ET.Element | None:
    for row in sheet_data.findall(_q("row")):
        if int(row.attrib.get("r", "0")) == row_number:
            return row
    return None


def _ensure_row(sheet_data: ET.Element, row_number: int) -> ET.Element:
    existing = _find_row(sheet_data, row_number)
    if existing is not None:
        return existing
    row = ET.Element(_q("row"), {"r": str(row_number)})
    inserted = False
    for index, current in enumerate(sheet_data.findall(_q("row"))):
        if int(current.attrib.get("r", "0")) > row_number:
            sheet_data.insert(index, row)
            inserted = True
            break
    if not inserted:
        sheet_data.append(row)
    return row


def _find_cell(row: ET.Element, cell_ref: str) -> ET.Element | None:
    for cell in row.findall(_q("c")):
        if cell.attrib.get("r") == cell_ref:
            return cell
    return None


def _ensure_cell(row: ET.Element, cell_ref: str, style_source: ET.Element | None = None) -> ET.Element:
    existing = _find_cell(row, cell_ref)
    if existing is not None:
        return existing
    attrs = {"r": cell_ref}
    if style_source is not None and style_source.attrib.get("s") is not None:
        attrs["s"] = style_source.attrib["s"]
    cell = ET.Element(_q("c"), attrs)
    target_col = _column_number(cell_ref)
    inserted = False
    for index, current in enumerate(row.findall(_q("c"))):
        if _column_number(current.attrib.get("r", "A1")) > target_col:
            row.insert(index, cell)
            inserted = True
            break
    if not inserted:
        row.append(cell)
    return cell


def _clear_value(cell: ET.Element) -> None:
    for child in list(cell):
        if child.tag in {_q("v"), _q("is"), _q("f")}:
            cell.remove(child)
    cell.attrib.pop("t", None)


def _write_value(cell: ET.Element, value) -> None:
    _clear_value(cell)
    if value is None or value == "":
        return
    if isinstance(value, bool):
        cell.attrib["t"] = "b"
        ET.SubElement(cell, _q("v")).text = "1" if value else "0"
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        ET.SubElement(cell, _q("v")).text = str(value)
        return
    if isinstance(value, (date, datetime)):
        cell.attrib["t"] = "d"
        ET.SubElement(cell, _q("v")).text = value.isoformat()
        return
    cell.attrib["t"] = "inlineStr"
    inline = ET.SubElement(cell, _q("is"))
    text = ET.SubElement(inline, _q("t"))
    string_value = str(value)
    if string_value[:1].isspace() or string_value[-1:].isspace():
        text.attrib["{http://www.w3.org/XML/1998/namespace}space"] = "preserve"
    text.text = string_value


def _style_templates(sheet_data: ET.Element, template_row: int) -> dict[int, ET.Element]:
    row = _find_row(sheet_data, template_row)
    if row is None:
        return {}
    return {_column_number(cell.attrib["r"]): deepcopy(cell) for cell in row.findall(_q("c"))}


def _replace_sheet_data_xml(original_xml: bytes, sheet_data: ET.Element) -> bytes:
    """Replace only sheetData while preserving Excel-specific worksheet XML verbatim.

    Official Excel worksheets carry namespace declarations and extension metadata
    whose prefixes can be referenced by string-valued attributes such as
    ``mc:Ignorable``. Re-serializing the complete worksheet with ElementTree can
    rename or remove those prefixes even when the XML remains well-formed, which
    makes desktop Excel repair the generated workbook. Keep the official worksheet
    envelope byte-for-byte and serialize only the report rows VetEdge owns.
    """
    opening = _SHEET_DATA_OPEN_RE.search(original_xml)
    if opening is None:
        raise ValueError("Official NADIS worksheet XML has no sheetData element.")

    prefix = opening.group("prefix") or b""
    opening_bytes = opening.group(0)
    if opening_bytes.rstrip().endswith(b"/>"):
        end = opening.end()
    else:
        closing = b"</" + prefix + b"sheetData>"
        closing_start = original_xml.find(closing, opening.end())
        if closing_start < 0:
            raise ValueError("Official NADIS worksheet XML has an unclosed sheetData element.")
        end = closing_start + len(closing)

    fragment = deepcopy(sheet_data)
    fragment.tail = None
    replacement = ET.tostring(fragment, encoding="utf-8", short_empty_elements=True)
    return original_xml[: opening.start()] + replacement + original_xml[end:]


def populate_official_template(
    template_bytes: bytes,
    *,
    sheet_rows: dict[str, list[list]],
    start_row: int,
    visible_column_counts: dict[str, int],
    clear_through_row: int,
) -> bytes:
    """Populate report cells while retaining all untouched official XLSX package parts.

    Only the visible report-cell values inside the requested worksheets are
    changed. Hidden lookup columns, named ranges, validations, comments,
    drawings and other package parts remain sourced from the verified official
    workbook rather than being reconstructed by VetEdge.
    """
    source_buffer = BytesIO(template_bytes)
    output_buffer = BytesIO()
    with ZipFile(source_buffer, "r") as source:
        paths = _sheet_paths(source)
        replacements: dict[str, bytes] = {}
        for sheet_name, rows in sheet_rows.items():
            path = paths.get(sheet_name)
            if not path:
                raise ValueError(f"Official NADIS template is missing sheet {sheet_name!r}.")
            sheet_xml = source.read(path)
            root = ET.fromstring(sheet_xml)
            sheet_data = root.find(_q("sheetData"))
            if sheet_data is None:
                raise ValueError(f"Official NADIS sheet {sheet_name!r} has no sheetData element.")
            max_col = visible_column_counts[sheet_name]
            styles = _style_templates(sheet_data, start_row)
            for row_number in range(start_row, clear_through_row + 1):
                row_node = _find_row(sheet_data, row_number)
                if row_node is None:
                    continue
                for cell in list(row_node.findall(_q("c"))):
                    if _column_number(cell.attrib.get("r", "A1")) <= max_col:
                        _clear_value(cell)
            for offset, values in enumerate(rows):
                row_number = start_row + offset
                row_node = _ensure_row(sheet_data, row_number)
                for column_number, value in enumerate(values, start=1):
                    if column_number > max_col:
                        break
                    cell_ref = f"{_column_letters(column_number)}{row_number}"
                    cell = _ensure_cell(row_node, cell_ref, styles.get(column_number))
                    _write_value(cell, value)
            replacements[path] = _replace_sheet_data_xml(sheet_xml, sheet_data)

        with ZipFile(output_buffer, "w", ZIP_DEFLATED) as output:
            for info in source.infolist():
                payload = replacements.get(info.filename, source.read(info.filename))
                output.writestr(info, payload)
    return output_buffer.getvalue()
