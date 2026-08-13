const API = Object.freeze({
	preflight: "vetedge.services.consultation_cancellation.get_consultation_cancellation_preflight",
	options: "vetedge.services.consultation_cancellation.get_cancellation_resolution_options",
	directCancel: "vetedge.services.consultation_cancellation.cancel_consultation_safely",
	record: "vetedge.services.consultation_cancellation.record_consultation_cancellation_resolution",
	retain: "vetedge.services.consultation_cancellation.retain_payment_and_cancel_consultation",
	reschedule: "vetedge.services.consultation_cancellation.execute_consultation_reschedule_resolution",
	approve: "vetedge.services.consultation_cancellation.approve_consultation_cancellation_resolution",
	complete: "vetedge.services.consultation_cancellation.complete_consultation_cancellation_resolution_manually",
});

const MANUAL_ACTIONS = new Set(["refund_required", "issue_customer_credit", "admin_accounting_correction"]);
let activeInstall = null;

function call(method, args = {}) {
	return frappe.call({ method, args }).then((response) => response.message || {});
}

function money(value) {
	const currency = frappe.boot?.sysdefaults?.currency || frappe.defaults?.get_default?.("currency") || "NGN";
	try {
		return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value || 0));
	} catch (_error) {
		return `${currency} ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
	}
}

function optionRows(rows = []) {
	return rows.map((row) => {
		if (typeof row === "string") return { value: row, label: row.replaceAll("_", " ") };
		const value = row.value || row.action || row.key || row.name || "";
		return { value, label: row.label || row.title || value.replaceAll("_", " ") };
	}).filter((row) => row.value);
}

function summaryMessage(preflight = {}) {
	const parts = [];
	const recommended = preflight.recommended_next_action;
	if (recommended) parts.push(`${__("Recommended")}: ${recommended.label || recommended.title || recommended.action || recommended}`);
	for (const blocker of preflight.blockers || []) parts.push(`${__("Blocker")}: ${blocker.message || blocker.label || blocker.type || blocker}`);
	for (const warning of preflight.warnings || []) parts.push(`${__("Warning")}: ${warning.message || warning.label || warning.type || warning}`);
	if (!parts.length) parts.push(__("No blocking dependency was found. VetEdge will preserve submitted accounting and stock records."));
	return parts.join("\n");
}

function fieldsFor(context) {
	const record = context.record || {};
	const action = context.values.resolution_action || record.resolution_action || "";
	const fields = [
		{ fieldname: "reason", label: __("Reason / Resolution Note"), type: "textarea", rows: 3 },
	];
	if (!record.name && context.canRecord) {
		fields.push({
			fieldname: "resolution_action",
			label: __("Controlled Resolution"),
			type: "select",
			required: true,
			options: context.actionOptions,
			onChange(value, values, modalView) {
				context.values = { ...values, resolution_action: value };
				modalView.update({ fields: fieldsFor(context), actions: actionsFor(context), values: context.values });
			},
		});
	}
	if (action === "reschedule_consultation") {
		fields.push({ fieldname: "appointment_datetime", label: __("New Appointment Date/Time"), type: "datetime-local", required: true });
	}
	if (MANUAL_ACTIONS.has(action)) {
		fields.push(
			{
				fieldname: "accounting_reference_doctype",
				label: __("Accounting Reference Type"),
				type: "select",
				options: ["Payment Entry", "Journal Entry", "Sales Invoice", "Stock Entry"].map((value) => ({ value, label: value })),
			},
			{ fieldname: "accounting_reference_name", label: __("Accounting Reference"), type: "text" },
			{ fieldname: "resolution_amount", label: __("Resolution Amount"), type: "number", min: 0, step: "0.01" },
			{ fieldname: "resolution_date", label: __("Resolution Date"), type: "date" },
			{
				fieldname: "status_outcome",
				label: __("Consultation Status Outcome"),
				type: "select",
				options: [
					{ value: "no_status_change", label: __("No Status Change") },
					{ value: "cancel_consultation_after_financial_resolution", label: __("Cancel Consultation After Financial Resolution") },
				],
			},
			{ fieldname: "completion_note", label: __("Completion Evidence / Note"), type: "textarea", rows: 3 },
		);
	}
	return fields;
}

function actionsFor(context) {
	const record = context.record || {};
	const action = context.values.resolution_action || record.resolution_action || "";
	const actions = [];
	if (context.preflight.can_cancel) {
		actions.push({ label: __("Cancel Consultation Safely"), danger: true, onClick: () => executeDirectCancel(context) });
	}
	if (!record.name && context.canRecord && action) {
		actions.push({ label: __("Record Resolution"), primary: true, onClick: (values) => recordDecision(context, values) });
	}
	if (record.name && action === "retain_payment_clinical_cancel_only") {
		actions.push({ label: __("Retain Payment & Cancel"), primary: true, onClick: (values) => retainPayment(context, values) });
	}
	if (record.name && action === "reschedule_consultation") {
		actions.push({ label: __("Complete Reschedule"), primary: true, onClick: (values) => reschedule(context, values) });
	}
	if (record.name && MANUAL_ACTIONS.has(action)) {
		if (!["Approved", "Completed"].includes(record.resolution_status)) {
			actions.push({ label: __("Approve Resolution"), onClick: (values) => approve(context, values) });
		}
		if (record.resolution_status !== "Completed") {
			actions.push({ label: __("Complete Financial Resolution"), primary: true, onClick: (values) => completeManual(context, values) });
		}
	}
	return actions;
}

function modalSpec(context) {
	const preflight = context.preflight || {};
	const billing = preflight.billing_group_summary || {};
	const record = context.record || {};
	return {
		title: __("Reverse / Resolve Completed Consultation"),
		subtitle: context.consultation,
		size: "lg",
		metrics: [
			{ label: __("Consultation Status"), value: preflight.current_status || "—", tone: "neutral" },
			{ label: __("Linked Invoices"), value: Number(billing.invoice_count || (preflight.linked_invoices || []).length || 0), tone: "info" },
			{ label: __("Paid Amount"), value: money(billing.paid_amount), tone: "success" },
			{ label: __("Outstanding"), value: money(billing.outstanding_amount), tone: Number(billing.outstanding_amount || 0) > 0 ? "warning" : "success" },
		],
		badges: record.name ? [{ label: `${__("Resolution")}: ${record.resolution_status || __("Draft")}`, status: record.resolution_status || "Draft" }] : [],
		message: summaryMessage(preflight),
		fields: fieldsFor(context),
		values: context.values,
		actions: actionsFor(context),
	};
}

async function refreshContext(context) {
	const [preflight, options] = await Promise.all([
		call(API.preflight, { consultation_name: context.consultation }),
		call(API.options, { consultation_name: context.consultation }),
	]);
	context.preflight = preflight || {};
	context.options = options || {};
	context.record = options?.existing_resolution || preflight?.existing_resolution || {};
	context.canRecord = Boolean(options?.can_record_resolution);
	context.actionOptions = optionRows(options?.allowed_action_options || preflight?.allowed_action_options || []);
	if (!context.values.resolution_action) {
		context.values.resolution_action = context.record.resolution_action || context.actionOptions[0]?.value || "";
	}
	return context;
}

function updateModal(context, patch = {}) {
	context.modal?.update({ ...modalSpec(context), ...patch });
}

async function runAction(context, task, successMessage) {
	updateModal(context, { busy: true, error: "" });
	try {
		await task();
		frappe.show_alert({ message: successMessage, indicator: "green" });
		context.values = { ...context.values, reason: "" };
		await refreshContext(context);
		updateModal(context, { busy: false });
		await context.clinicalView?.loadDetail?.(context.consultation);
		context.syncButton?.();
	} catch (error) {
		updateModal(context, { busy: false, error: error?.message || __("Consultation resolution action failed."), errorTitle: __("Resolution action failed") });
	}
}

function executeDirectCancel(context) {
	return runAction(context, () => call(API.directCancel, { consultation_name: context.consultation, reason: context.values.reason || undefined }), __("Consultation cancelled safely."));
}

function recordDecision(context, values) {
	context.values = { ...context.values, ...values };
	return runAction(context, () => call(API.record, { consultation_name: context.consultation, resolution_action: context.values.resolution_action, reason: context.values.reason || undefined }), __("Resolution decision recorded."));
}

function retainPayment(context, values) {
	context.values = { ...context.values, ...values };
	return runAction(context, () => call(API.retain, { consultation_name: context.consultation, reason: context.values.reason || undefined }), __("Consultation cancelled with payment retained."));
}

function reschedule(context, values) {
	context.values = { ...context.values, ...values };
	return runAction(context, () => call(API.reschedule, { consultation_name: context.consultation, resolution_name: context.record?.name || undefined, appointment_datetime: context.values.appointment_datetime, reason: context.values.reason || undefined }), __("Consultation reschedule resolution completed."));
}

function approve(context, values) {
	context.values = { ...context.values, ...values };
	return runAction(context, () => call(API.approve, { resolution_name: context.record.name, note: context.values.reason || undefined }), __("Resolution approved."));
}

function completeManual(context, values) {
	context.values = { ...context.values, ...values };
	return runAction(context, () => call(API.complete, {
		resolution_name: context.record.name,
		completion_note: context.values.completion_note || undefined,
		accounting_reference_doctype: context.values.accounting_reference_doctype || undefined,
		accounting_reference_name: context.values.accounting_reference_name || undefined,
		resolution_amount: context.values.resolution_amount || undefined,
		resolution_date: context.values.resolution_date || undefined,
		status_outcome: context.values.status_outcome || "no_status_change",
	}), __("Financial resolution evidence completed."));
}

async function openWorkflow(clinicalView, syncButton) {
	const consultation = String(clinicalView?.detail?.name || "").trim();
	if (!consultation || !window.VetEdgeEdgeModalPresenter?.open) return;
	const context = {
		consultation,
		clinicalView,
		syncButton,
		preflight: {},
		options: {},
		record: {},
		canRecord: false,
		actionOptions: [],
		values: {
			reason: "",
			resolution_action: "",
			appointment_datetime: "",
			accounting_reference_doctype: "",
			accounting_reference_name: "",
			resolution_amount: "",
			resolution_date: frappe.datetime?.get_today?.() || "",
			status_outcome: "no_status_change",
			completion_note: "",
		},
	};
	context.modal = window.VetEdgeEdgeModalPresenter.open({
		title: __("Reverse / Resolve Completed Consultation"),
		subtitle: consultation,
		size: "lg",
		loading: true,
		loadingMessage: __("Checking consultation, billing and clinical dependencies..."),
	});
	try {
		await refreshContext(context);
		context.modal.update({ loading: false, ...modalSpec(context) });
	} catch (error) {
		context.modal.update({ loading: false, error: error?.message || __("Consultation resolution could not be loaded."), errorTitle: __("Resolution workflow unavailable"), onRetry: () => openWorkflow(clinicalView, syncButton) });
	}
}

export function installVetEdgeClinicalWorkflowModal(workspaceRoot, clinicalView) {
	if (!workspaceRoot || !clinicalView || !window.VetEdgeEdgeModalPresenter?.ready?.()) return { installed: false };
	activeInstall?.destroy?.();
	let button = null;
	const syncButton = () => {
		const completed = String(clinicalView?.detail?.status || "") === "Completed";
		const actions = workspaceRoot.querySelector(".clinical-statusbar .clinical-row-actions");
		if (!completed || !actions) {
			button?.remove();
			button = null;
			return;
		}
		if (button?.isConnected) return;
		button = document.createElement("button");
		button.type = "button";
		button.className = "edge-button edge-button--danger edge-button--compact vetedge-consultation-resolution-button";
		button.textContent = __("Reverse / Resolve Consultation");
		button.addEventListener("click", () => openWorkflow(clinicalView, syncButton));
		actions.prepend(button);
	};
	const observer = new MutationObserver(syncButton);
	observer.observe(workspaceRoot, { childList: true, subtree: true, characterData: true });
	syncButton();
	activeInstall = {
		installed: true,
		open: () => openWorkflow(clinicalView, syncButton),
		destroy() {
			observer.disconnect();
			button?.remove();
		},
	};
	return activeInstall;
}

if (typeof window !== "undefined") {
	window.installVetEdgeClinicalWorkflowModal = installVetEdgeClinicalWorkflowModal;
}
