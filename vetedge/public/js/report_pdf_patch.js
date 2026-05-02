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

	xhr.onload = function (event) {
		if (this.status === 200) {
			const blob = new Blob([event.currentTarget.response], { type: "application/pdf" });
			const objectUrl = URL.createObjectURL(blob);
			const hiddenATag = document.createElement("a");
			document.body.appendChild(hiddenATag);
			hiddenATag.style = "display: none";
			hiddenATag.href = objectUrl;
			hiddenATag.download = `${opts.report_name || "report"}.pdf`;
			hiddenATag.click();
			window.URL.revokeObjectURL(objectUrl);
			hiddenATag.remove();
			return;
		}

		let errorMessage = __("Report PDF download failed.");
		try {
			const decoded = new TextDecoder("utf-8").decode(this.response);
			const parsed = JSON.parse(decoded);
			errorMessage =
				parsed?._server_messages ||
				parsed?.message ||
				parsed?.exc ||
				errorMessage;
		} catch (e) {
			// Keep the generic message when the error body is not JSON.
		}
		showError(errorMessage);
	};

	xhr.onerror = function () {
		showError(__("Report PDF download failed. Please try again."));
	};

	xhr.send(formData);
};
