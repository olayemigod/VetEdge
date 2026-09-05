frappe.render_pdf = function (html, opts = {}) {
	const formData = new FormData();
	formData.append("html", html);
	formData.append("orientation", opts.orientation || "Landscape");
	formData.append("report_name", opts.report_name || "report");
	formData.append("blob", new Blob([], { type: "text/xml" }));

	const xhr = new XMLHttpRequest();
	xhr.open("POST", "/api/method/vetedge.services.report_pdf.download_report_pdf");
	xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
	xhr.responseType = "arraybuffer";

	const showError = (message) => {
		frappe.msgprint(message || __("Report PDF download failed."));
	};
	const parseError = (response) => {
		try {
			const decoded = new TextDecoder("utf-8").decode(response || new ArrayBuffer(0));
			const parsed = JSON.parse(decoded);
			return parsed?._server_messages || parsed?.message || parsed?.exc || "";
		} catch (_error) {
			return "";
		}
	};
	const fallbackValidatePdf = (bytes, mime) => {
		if (!bytes.length) throw new Error(__("The generated PDF is empty."));
		const header = Array.from(bytes.slice(0, 5));
		if (header.join(",") !== "37,80,68,70,45") {
			const preview = new TextDecoder("utf-8").decode(bytes.slice(0, Math.min(bytes.length, 256))).trim().toLowerCase();
			if (preview.startsWith("<html") || preview.startsWith("<!doctype html") || preview.includes("<body")) {
				throw new Error(__("The server returned an error page instead of a PDF file."));
			}
			throw new Error(__("The generated PDF is invalid or incomplete."));
		}
		if (mime && !String(mime).toLowerCase().includes("application/pdf")) {
			throw new Error(__("The server returned an unexpected file type instead of PDF."));
		}
	};
	const saveVerifiedPdf = (response) => {
		const bytes = new Uint8Array(response || new ArrayBuffer(0));
		const mime = xhr.getResponseHeader("Content-Type") || "application/pdf";
		const shared = window.EdgeSuiteReportExport || window.EdgeSuiteUI?.reportExport || window.EdgeUI?.reportExport;
		if (shared?.downloadVerified) {
			shared.downloadVerified({ bytes, format: "pdf", mime, filename: `${opts.report_name || "report"}.pdf` });
			return;
		}
		fallbackValidatePdf(bytes, mime);
		const blob = new Blob([bytes], { type: "application/pdf" });
		const objectUrl = URL.createObjectURL(blob);
		const hiddenATag = document.createElement("a");
		document.body.appendChild(hiddenATag);
		hiddenATag.style = "display: none";
		hiddenATag.href = objectUrl;
		hiddenATag.download = `${opts.report_name || "report"}.pdf`;
		hiddenATag.click();
		hiddenATag.remove();
		window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 0);
	};

	xhr.onload = function (event) {
		if (this.status >= 200 && this.status < 300) {
			try {
				saveVerifiedPdf(event.currentTarget.response);
			} catch (error) {
				showError(error?.message || __("Report PDF download failed validation."));
			}
			return;
		}
		showError(parseError(this.response) || __("Report PDF download failed."));
	};

	xhr.onerror = function () {
		showError(__("Report PDF download failed. Please try again."));
	};

	xhr.send(formData);
};


// Navigation hardening is operational shell infrastructure, not reporting
// functionality. Load it independently before any optional frappe.require()
// calls so a failure in another late-loaded VetEdge helper cannot prevent the
// direct Veterinary Home/sidebar repair from installing.
(function loadVetEdgePostQaNavigationHardening() {
	if (window.__vetedgePostQaNavigationHardeningInstalled) return;
	if (document.querySelector('script[data-vetedge-postqa-navigation="1"]')) return;

	const script = document.createElement("script");
	script.src = "/assets/vetedge/js/vetedge_postqa_navigation_hardening.js?v=20260905-1";
	script.async = false;
	script.dataset.vetedgePostqaNavigation = "1";
	script.onload = function () {
		window.VetEdgePostQaNavigation?.reconcile?.();
	};
	script.onerror = function () {
		console.error("VetEdge navigation hardening asset failed to load:", script.src);
	};
	(document.head || document.documentElement).appendChild(script);
})();

function vetedgeSafeRequire(path) {
	try {
		const pending = frappe.require(path);
		if (pending && typeof pending.catch === "function") {
			pending.catch((error) => console.error(`VetEdge optional asset failed to load: ${path}`, error));
		}
	} catch (error) {
		console.error(`VetEdge optional asset failed to load: ${path}`, error);
	}
}

vetedgeSafeRequire("/assets/vetedge/js/vetedge_product_menu_native_guard.js?v=20260831-1");
vetedgeSafeRequire("/assets/vetedge/js/vetedge_report_scheduling_ui.js");
vetedgeSafeRequire("/assets/vetedge/js/vetedge_report_scheduling_management_ui.js");
