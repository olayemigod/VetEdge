(function installVetEdgeReportSchedulingManagementUI(global) {
	"use strict";

	const LIST_API = "vetedge.services.report_scheduling_management.get_my_report_schedules";
	const ENABLE_API = "vetedge.services.report_scheduling_management.set_report_schedule_enabled";
	const DELETE_API = "vetedge.services.report_scheduling_management.delete_report_schedule";
	const REPLACEMENT_CLASS = "vetedge-report-scheduling-management-replacement";

	function escape(value) {
		return frappe.utils?.escape_html ? frappe.utils.escape_html(String(value || "")) : String(value || "");
	}

	function rowsHtml(items) {
		if (!items.length) return `<div class="text-muted p-3">${__("No scheduled VetEdge reports yet.")}</div>`;
		return `<div class="table-responsive"><table class="table table-bordered table-sm"><thead><tr><th>${__("Report")}</th><th>${__("Delivery")}</th><th>${__("Frequency")}</th><th>${__("Format")}</th><th>${__("Recipients")}</th><th>${__("Status")}</th><th>${__("Actions")}</th></tr></thead><tbody>${items.map((item) => `<tr><td>${escape(item.report_name)}</td><td>${item.delivery_mode === "vetedge_export_adapter" ? __("Optimized") : __("Native")}</td><td>${escape(item.frequency)}${item.day_of_week ? ` · ${escape(item.day_of_week)}` : ""}</td><td>${escape(item.format)}</td><td>${escape(item.email_to)}</td><td>${item.enabled ? __("Enabled") : __("Paused")}</td><td><button class="btn btn-xs btn-default" data-vetedge-schedule-toggle="${escape(item.name)}" data-enabled="${item.enabled ? 0 : 1}">${item.enabled ? __("Pause") : __("Enable")}</button> <button class="btn btn-xs btn-danger" data-vetedge-schedule-delete="${escape(item.name)}">${__("Delete")}</button></td></tr>`).join("")}</tbody></table></div>`;
	}

	async function openManager() {
		try {
			const response = await frappe.call(LIST_API, {});
			const items = Array.isArray(response.message) ? response.message : [];
			const dialog = new frappe.ui.Dialog({ title: __("My Scheduled Reports"), size: "extra-large", fields: [{ fieldtype: "HTML", fieldname: "body" }] });
			dialog.fields_dict.body.$wrapper.html(rowsHtml(items));
			dialog.fields_dict.body.$wrapper.on("click", "[data-vetedge-schedule-toggle]", async function () {
				await frappe.call(ENABLE_API, { name: this.dataset.vetedgeScheduleToggle, enabled: Number(this.dataset.enabled || 0) });
				dialog.hide();
				frappe.show_alert?.({ message: __("Scheduled report updated."), indicator: "green" });
				openManager();
			});
			dialog.fields_dict.body.$wrapper.on("click", "[data-vetedge-schedule-delete]", function () {
				const name = this.dataset.vetedgeScheduleDelete;
				frappe.confirm(__("Delete this scheduled report delivery?"), async () => {
					await frappe.call(DELETE_API, { name });
					dialog.hide();
					frappe.show_alert?.({ message: __("Scheduled report deleted."), indicator: "green" });
					openManager();
				});
			});
			dialog.show();
		} catch (error) {
			frappe.msgprint({ title: __("Scheduled Reports"), message: error?.message || __("Scheduled reports could not be loaded."), indicator: "red" });
		}
	}

	function replaceManagerButton() {
		const wrapper = document.querySelector(".vetedge-report-scheduling-actions");
		if (!wrapper || wrapper.querySelector(`.${REPLACEMENT_CLASS}`)) return;
		const buttons = wrapper.querySelectorAll("button");
		if (buttons.length < 2) return;
		buttons[1].style.display = "none";
		const replacement = document.createElement("button");
		replacement.type = "button";
		replacement.className = `edge-button edge-button--secondary ${REPLACEMENT_CLASS}`;
		replacement.textContent = __("My Schedules");
		replacement.addEventListener("click", openManager);
		wrapper.appendChild(replacement);
	}

	const observer = new MutationObserver(replaceManagerButton);
	observer.observe(document.documentElement, { childList: true, subtree: true });
	replaceManagerButton();
})(window);
