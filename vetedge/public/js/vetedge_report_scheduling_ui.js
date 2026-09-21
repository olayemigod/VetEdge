(function installVetEdgeReportSchedulingUI(global) {
	"use strict";

	const COMPATIBILITY_API = "vetedge.services.report_scheduling_compatibility.get_scheduling_compatibility";
	const CREATE_NATIVE_API = "vetedge.services.report_scheduling.create_native_report_schedule";
	const CREATE_VETEDGE_API = "vetedge.services.report_scheduling.create_vetedge_report_schedule";
	const LIST_API = "vetedge.services.report_scheduling.get_my_report_schedules";
	const ENABLE_API = "vetedge.services.report_scheduling.set_report_schedule_enabled";
	const DELETE_API = "vetedge.services.report_scheduling.delete_report_schedule";
	const ACTION_CLASS = "vetedge-report-scheduling-actions";
	let dialogApp = null;
	let dialogRoot = null;
	let compatibility = null;

	function onReportCenter() {
		return global.location?.pathname === "/desk/vetedge-report-center" || global.frappe?.get_route?.()?.[0] === "vetedge-report-center";
	}

	function stateFromLocation() {
		const params = new URLSearchParams(global.location?.search || "");
		const filters = {};
		for (const [key, value] of params.entries()) {
			if (!["report", "source", "columns"].includes(key) && value !== "") filters[key] = value;
		}
		return {
			reportName: params.get("report") || global.frappe?.route_options?.report || "",
			filters,
			columns: String(params.get("columns") || "").split(",").map((item) => item.trim()).filter(Boolean),
		};
	}

	async function getCompatibility(reportName) {
		const response = await frappe.call(COMPATIBILITY_API, { report_name: reportName });
		return response.message || {};
	}

	function destroyScheduleDialog() {
		dialogApp?.unmount?.();
		dialogApp = null;
		dialogRoot?.remove?.();
		dialogRoot = null;
	}

	async function openScheduleDialog() {
		const state = stateFromLocation();
		if (!state.reportName) return;
		try {
			compatibility = await getCompatibility(state.reportName);
			if (!compatibility.can_configure) {
				frappe.msgprint({ title: __("Scheduled Delivery"), message: __("Scheduled report delivery is not available for this report or current Plan."), indicator: "orange" });
				return;
			}
			const runtime = global.EdgeSuiteUI || global.EdgeUI;
			const EdgeReportScheduleDialog = runtime?.components?.EdgeReportScheduleDialog;
			if (!runtime?.createEdgeApp || !runtime?.Vue?.h || !EdgeReportScheduleDialog) {
				throw new Error(__("The current EdgeSuite scheduled-delivery dialog is unavailable."));
			}
			destroyScheduleDialog();
			dialogRoot = document.createElement("div");
			dialogRoot.className = "vetedge-report-schedule-dialog-host";
			document.body.appendChild(dialogRoot);
			const h = runtime.Vue.h;
			const component = {
				data: () => ({ open: true, busy: false }),
				methods: {
					close() { this.open = false; global.setTimeout(destroyScheduleDialog, 0); },
					async schedule(options) {
						this.busy = true;
						try {
							const args = {
								report_name: state.reportName,
								email_to: options.email_to,
								frequency: options.frequency,
								file_format: options.format,
								filters: JSON.stringify(state.filters),
								day_of_week: options.day_of_week || "",
								send_if_data: options.send_if_data ? 1 : 0,
								no_of_rows: options.no_of_rows,
							};
							const optimized = compatibility.delivery_mode === "vetedge_export_adapter";
							if (optimized) args.selected_columns = JSON.stringify(options.columns || state.columns || []);
							await frappe.call(optimized ? CREATE_VETEDGE_API : CREATE_NATIVE_API, args);
							frappe.show_alert?.({ message: __("Scheduled report delivery created."), indicator: "green" });
							this.close();
						} catch (error) {
							frappe.msgprint({ title: __("Schedule Failed"), message: error?.message || __("The scheduled report could not be created."), indicator: "red" });
						} finally { this.busy = false; }
					},
				},
				render() {
					const columns = state.columns.map((fieldname) => ({ fieldname, label: fieldname.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) }));
					return h(EdgeReportScheduleDialog, {
						open: this.open,
						busy: this.busy,
						reportTitle: state.reportName,
						columns,
						initialOptions: { email_to: frappe.session?.user || "", frequency: "Daily", format: "XLSX", no_of_rows: 500, send_if_data: true, columns: state.columns },
						onClose: this.close,
						onSchedule: this.schedule,
					});
				},
			};
			dialogApp = runtime.createEdgeApp(component);
			dialogApp.mount(dialogRoot);
		} catch (error) {
			frappe.msgprint({ title: __("Scheduled Delivery"), message: error?.message || __("Scheduled delivery could not be opened."), indicator: "red" });
		}
	}

	function scheduleRowsHtml(items) {
		if (!items.length) return `<div class="text-muted p-3">${__("No scheduled VetEdge reports yet.")}</div>`;
		return `<div class="table-responsive"><table class="table table-bordered table-sm"><thead><tr><th>${__("Report")}</th><th>${__("Frequency")}</th><th>${__("Format")}</th><th>${__("Recipients")}</th><th>${__("Status")}</th><th>${__("Actions")}</th></tr></thead><tbody>${items.map((item) => `<tr><td>${frappe.utils.escape_html(item.report_name || "")}</td><td>${frappe.utils.escape_html(item.frequency || "")}${item.day_of_week ? ` · ${frappe.utils.escape_html(item.day_of_week)}` : ""}</td><td>${frappe.utils.escape_html(item.format || "")}</td><td>${frappe.utils.escape_html(item.email_to || "")}</td><td>${item.enabled ? __("Enabled") : __("Paused")}</td><td><button class="btn btn-xs btn-default" data-schedule-toggle="${frappe.utils.escape_html(item.name)}" data-enabled="${item.enabled ? 0 : 1}">${item.enabled ? __("Pause") : __("Enable")}</button> <button class="btn btn-xs btn-danger" data-schedule-delete="${frappe.utils.escape_html(item.name)}">${__("Delete")}</button></td></tr>`).join("")}</tbody></table></div>`;
	}

	async function openMySchedules() {
		try {
			const response = await frappe.call(LIST_API, {});
			const items = Array.isArray(response.message) ? response.message : [];
			const dialog = new frappe.ui.Dialog({ title: __("My Scheduled Reports"), size: "extra-large", fields: [{ fieldtype: "HTML", fieldname: "body" }] });
			dialog.fields_dict.body.$wrapper.html(scheduleRowsHtml(items));
			dialog.fields_dict.body.$wrapper.on("click", "[data-schedule-toggle]", async function () {
				await frappe.call(ENABLE_API, { name: this.dataset.scheduleToggle, enabled: Number(this.dataset.enabled || 0) });
				dialog.hide();
				frappe.show_alert?.({ message: __("Scheduled report updated."), indicator: "green" });
				openMySchedules();
			});
			dialog.fields_dict.body.$wrapper.on("click", "[data-schedule-delete]", function () {
				const name = this.dataset.scheduleDelete;
				frappe.confirm(__("Delete this scheduled report delivery?"), async () => {
					await frappe.call(DELETE_API, { name });
					dialog.hide();
					frappe.show_alert?.({ message: __("Scheduled report deleted."), indicator: "green" });
					openMySchedules();
				});
			});
			dialog.show();
		} catch (error) {
			frappe.msgprint({ title: __("Scheduled Reports"), message: error?.message || __("Scheduled reports could not be loaded."), indicator: "red" });
		}
	}

	function injectActions() {
		if (!onReportCenter()) return;
		const containers = [...document.querySelectorAll(".vetedge-report-center-actions")];
		const host = containers.at(-1);
		if (!host || host.querySelector(`.${ACTION_CLASS}`)) return;
		const wrapper = document.createElement("span");
		wrapper.className = ACTION_CLASS;
		const schedule = document.createElement("button");
		schedule.type = "button";
		schedule.className = "edge-button edge-button--secondary";
		schedule.textContent = __("Schedule · Advanced");
		schedule.addEventListener("click", openScheduleDialog);
		const manage = document.createElement("button");
		manage.type = "button";
		manage.className = "edge-button edge-button--secondary";
		manage.textContent = __("My Schedules");
		manage.addEventListener("click", openMySchedules);
		wrapper.append(schedule, manage);
		host.prepend(wrapper);
	}

	const observer = new MutationObserver(injectActions);
	observer.observe(document.documentElement, { childList: true, subtree: true });
	global.addEventListener("popstate", injectActions);
	global.addEventListener("hashchange", injectActions);
	if (frappe.router?.on) frappe.router.on("change", injectActions);
	injectActions();
})(window);
