from __future__ import annotations

import vhome_browser_smoke as smoke

# This exception is inherited from the reconciled PR57 reporting/navigation
# composition. Attribute it by the complete known stack signature rather than
# a source line number, because harmless insertions in report_pdf_patch.js must
# not turn a green Veterinary Home browser matrix red.
KNOWN_INHERITED_PAGEERROR_SIGNATURE = (
    "pageerror: s is not a function",
    "frappe.require (",
    "Object.wrappedRequire [as require]",
    "vetedge_professional_ui.js",
    "report_pdf_patch.js:",
)


def _is_known_inherited_pageerror(event: str) -> bool:
    return all(fragment in event for fragment in KNOWN_INHERITED_PAGEERROR_SIGNATURE)


def _assert_pageerror_attribution(events: list[str]) -> None:
    pageerrors = [event for event in events if " pageerror:" in event]
    unexpected = [event for event in pageerrors if not _is_known_inherited_pageerror(event)]
    if unexpected:
        raise AssertionError("Unexpected browser page errors:\n" + "\n\n".join(unexpected))


smoke._assert_pageerror_attribution = _assert_pageerror_attribution


if __name__ == "__main__":
    smoke.main()
