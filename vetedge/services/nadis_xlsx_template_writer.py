from __future__ import annotations

import re
from copy import deepcopy
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import quoteattr
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DEFAULT_DATE_FORMAT = "dd/mm/yyyy"
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


def _excel_date_serial(value: date | datetime) -> float | int:
    day = value.date() if isinstance(value, datetime) else value
    serial = (day - date(1899, 12, 31)).days
    if day >= date(1900, 3, 1):
        serial += 1
    if not isinstance(value, datetime):
        return serial
    seconds = value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1_000_000
    return serial + seconds / 86400


def _write_excel_date(cell: ET.Element, value: date | datetime) -> None:
    _clear_value(cell)
    serial = _excel_date_serial(value)
    text = str(serial) if isinstance(serial, int) else format(serial, ".15g")
    ET.SubElement(cell, _q("v")).text = text


def _style_templates(sheet_data: ET.Element, template_row: int) -> dict[int, ET.Element]:
    row = _find_row(sheet_data, template_row)
    if row is None:
        return {}
    return {_column_number(cell.attrib["r"]): deepcopy(cell) for cell in row.findall(_q("c"))}


def _tag_opening(xml: bytes, local_name: str) -> re.Match[bytes] | None:
    return re.search(
        rb"<(?P<prefix>[A-Za-z_][\w.-]*:)?" + re.escape(local_name.encode()) + rb"\b[^>]*>",
        xml,
    )


def _with_count(opening: bytes, count: int) -> bytes:
    count_bytes = f'count="{count}"'.encode()
    if re.search(rb"\bcount=\"[^\"]*\"", opening):
        return re.sub(rb"\bcount=\"[^\"]*\"", count_bytes, opening, count=1)
    suffix = b"/>" if opening.rstrip().endswith(b"/>") else b">"
    body = opening[: -len(suffix)].rstrip()
    return body + b" " + count_bytes + suffix


def _append_xml_child(xml: bytes, container_name: str, child: bytes, count: int) -> bytes:
    opening = _tag_opening(xml, container_name)
    if opening is None:
        raise ValueError(f"Official NADIS styles.xml has no {container_name} element.")
    prefix = opening.group("prefix") or b""
    opening_bytes = opening.group(0)
    updated_opening = _with_count(opening_bytes, count)
    if opening_bytes.rstrip().endswith(b"/>"):
        expanded_opening = updated_opening.rstrip()
        expanded_opening = expanded_opening[:-2].rstrip() + b">"
        closing = b"</" + prefix + container_name.encode() + b">"
        return xml[: opening.start()] + expanded_opening + child + closing + xml[opening.end() :]

    closing = b"</" + prefix + container_name.encode() + b">"
    closing_start = xml.find(closing, opening.end())
    if closing_start < 0:
        raise ValueError(f"Official NADIS styles.xml has an unclosed {container_name} element.")
    return (
        xml[: opening.start()]
        + updated_opening
        + xml[opening.end() : closing_start]
        + child
        + xml[closing_start:]
    )


def _insert_num_format(xml: bytes, num_fmt_id: int, format_code: str, existing_count: int) -> bytes:
    num_fmt_opening = _tag_opening(xml, "numFmts")
    if num_fmt_opening is not None:
        prefix = num_fmt_opening.group("prefix") or b""
        child = (
            b"<"
            + prefix
            + b'numFmt numFmtId="'
            + str(num_fmt_id).encode()
            + b'" formatCode='
            + quoteattr(format_code).encode()
            + b"/>"
        )
        return _append_xml_child(xml, "numFmts", child, existing_count + 1)

    fonts = _tag_opening(xml, "fonts")
    if fonts is None:
        raise ValueError("Official NADIS styles.xml has no fonts element before cell styles.")
    prefix = fonts.group("prefix") or b""
    block = (
        b"<"
        + prefix
        + b'numFmts count="1"><'
        + prefix
        + b'numFmt numFmtId="'
        + str(num_fmt_id).encode()
        + b'" formatCode='
        + quoteattr(format_code).encode()
        + b"/></"
        + prefix
        + b"numFmts>"
    )
    return xml[: fonts.start()] + block + xml[fonts.start() :]


def _number_format_map(root: ET.Element) -> dict[int, str]:
    num_fmts = root.find(_q("numFmts"))
    if num_fmts is None:
        return {}
    return {
        int(item.attrib["numFmtId"]): item.attrib.get("formatCode", "")
        for item in num_fmts.findall(_q("numFmt"))
        if item.attrib.get("numFmtId")
    }


def _ensure_number_format_style(styles_xml: bytes, base_style_index: int, format_code: str) -> tuple[bytes, int]:
    root = ET.fromstring(styles_xml)
    cell_xfs = root.find(_q("cellXfs"))
    if cell_xfs is None:
        raise ValueError("Official NADIS styles.xml has no cellXfs element.")
    xfs = cell_xfs.findall(_q("xf"))
    if base_style_index < 0 or base_style_index >= len(xfs):
        raise ValueError(f"Official NADIS cell style index {base_style_index} is outside cellXfs.")

    format_map = _number_format_map(root)
    base_xf = xfs[base_style_index]
    base_num_fmt_id = int(base_xf.attrib.get("numFmtId", "0") or 0)
    if format_map.get(base_num_fmt_id) == format_code:
        return styles_xml, base_style_index

    matching_num_fmt_id = next((fmt_id for fmt_id, code in format_map.items() if code == format_code), None)
    if matching_num_fmt_id is None:
        matching_num_fmt_id = max([163, *format_map.keys()]) + 1
        styles_xml = _insert_num_format(styles_xml, matching_num_fmt_id, format_code, len(format_map))

    cloned_xf = deepcopy(base_xf)
    cloned_xf.attrib["numFmtId"] = str(matching_num_fmt_id)
    cloned_xf.attrib["applyNumberFormat"] = "1"
    xf_bytes = ET.tostring(cloned_xf, encoding="utf-8", short_empty_elements=True)
    style_index = len(xfs)
    styles_xml = _append_xml_child(styles_xml, "cellXfs", xf_bytes, style_index + 1)
    return styles_xml, style_index


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
    workbook rather than being reconstructed by VetEdge. Python date values are
    stored as native Excel serials with the NADIS ``dd/mm/yyyy`` display format.
    """
    source_buffer = BytesIO(template_bytes)
    output_buffer = BytesIO()
    with ZipFile(source_buffer, "r") as source:
        paths = _sheet_paths(source)
        replacements: dict[str, bytes] = {}
        styles_xml: bytes | None = None
        date_style_cache: dict[int, int] = {}
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
                    if isinstance(value, (date, datetime)):
                        if styles_xml is None:
                            try:
                                styles_xml = source.read("xl/styles.xml")
                            except KeyError as exc:
                                raise ValueError("Official NADIS template has no xl/styles.xml for date formatting.") from exc
                        base_style_index = int(cell.attrib.get("s", "0") or 0)
                        date_style_index = date_style_cache.get(base_style_index)
                        if date_style_index is None:
                            styles_xml, date_style_index = _ensure_number_format_style(
                                styles_xml,
                                base_style_index,
                                _DEFAULT_DATE_FORMAT,
                            )
                            date_style_cache[base_style_index] = date_style_index
                        cell.attrib["s"] = str(date_style_index)
                        _write_excel_date(cell, value)
                    else:
                        _write_value(cell, value)
            replacements[path] = _replace_sheet_data_xml(sheet_xml, sheet_data)

        if styles_xml is not None:
            replacements["xl/styles.xml"] = styles_xml

        with ZipFile(output_buffer, "w", ZIP_DEFLATED) as output:
            for info in source.infolist():
                payload = replacements.get(info.filename, source.read(info.filename))
                output.writestr(info, payload)
    return output_buffer.getvalue()
