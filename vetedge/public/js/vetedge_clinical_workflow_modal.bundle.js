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
const FINANCIAL_CANCEL_ACTIONS = new Set(["refund_required", "issue_customer_credit"]);
const RESOLUTION_ROLES = new Set(["System Manager", "VetEdge Administrator", "Branch Manager", "VetEdge Branch Manager", "Accounts/Cashier", "VetEdge Accounts/Cashier", "Accounts User", "Accounts Manager"]);
const RESCHEDULE_ROLES = new Set([...RESOLUTION_ROLES, "VetEdge Front Desk"]);
const EXTERNAL_REFERENCE_ROLES = new Set(["System Manager", "Accounts Manager"]);
const REFERENCE_TYPES = Object.freeze({
	refund_required: ["Payment Entry", "Journal Entry", "Sales Invoice"],
	issue_customer_credit: ["Sales Invoice", "Journal Entry", "Payment Entry"],
	admin_accounting_correction: ["Journal Entry", "Sales Invoice", "Payment Entry", "Stock Entry"],
});
let activeInstall = null;

function call(method, args = {}) { return frappe.call({ method, args }).then((response) => response.message || {}); }
function currentRoles() { return new Set(frappe.user_roles || frappe.boot?.user?.roles || []); }
function hasAnyRole(allowed) { const roles = currentRoles(); for (const role of allowed) if (roles.has(role)) return true; return false; }
function permissionState() { return { record: hasAnyRole(RESOLUTION_ROLES), approve: hasAnyRole(RESOLUTION_ROLES), retain: hasAnyRole(RESOLUTION_ROLES), reschedule: hasAnyRole(RESCHEDULE_ROLES), complete: hasAnyRole(RESOLUTION_ROLES), externalReference: hasAnyRole(EXTERNAL_REFERENCE_ROLES) }; }
function serverDatetime(value) { return value ? String(value).replace("T", " ") : value; }

function money(value) {
	const currency = frappe.boot?.sysdefaults?.currency || frappe.defaults?.get_default?.("currency") || "NGN";
	try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value || 0)); }
	catch (_error) { return `${currency} ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`; }
}

function humanAction(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase()); }
function optionRows(rows = []) {
	return rows.map((row) => {
		if (typeof row === "string") return { value: row, label: humanAction(row) };
		const value = row.value || row.action || row.key || row.name || "";
		return { value, label: row.label || row.title || humanAction(value) };
	}).filter((row) => row.value);
}
function recordAction(record = {}) { return String(record.resolution_action_key || "").trim(); }

function summaryMessage(preflight = {}) {
	const parts = [];
	const recommended = preflight.recommended_next_action;
	if (recommended) {
		const value = recommended.label || recommended.title || recommended.action || recommended;
		parts.push(`${__("Recommended")}: ${typeof value === "string" ? humanAction(value) : value}`);
	}
	for (const blocker of preflight.blockers || []) parts.push(`${__("Blocker")}: ${blocker.message || blocker.label || blocker.type || blocker}`);
	for (const warning of preflight.warnings || []) parts.push(`${__("Warning")}: ${warning.message || warning.label || warning.type || warning}`);
	if (!parts.length) parts.push(__("No blocking dependency was found. Submitted accounting and stock records will be preserved."));
	return parts.join("\n");
}

function rebuildForField(context, value, values, modalView, fieldname) {
	context.values = { ...values, [fieldname]: value };
	modalView.update({ fields: fieldsFor(context), actions: actionsFor(context), values: context.values, error: "" });
}

function fieldsFor(context) {
	const record = context.record || {};
	const action = context.values.resolution_action || recordAction(record);
	const status = String(record.resolution_status || "");
	const fields = [];
	if (!record.name && context.canRecord) fields.push({ fieldname: "resolution_action", label: __("Controlled Resolution"), type: "select", required: true, options: context.actionOptions, onChange(value, values, modalView) { rebuildForField(context, value, values, modalView, "resolution_action"); } });
	fields.push({ fieldname: "reason", label: __("Reason / Resolution Note"), type: "textarea", rows: 3 });
	if (record.name && status === "Approved" && action === "reschedule_consultation") fields.push({ fieldname: "appointment_datetime", label: __("New Appointment Date/Time"), type: "datetime-local", required: true });
	if (record.name && status === "Approved" && MANUAL_ACTIONS.has(action)) {
		if (context.permissions.externalReference) fields.push({ fieldname: "external_reference", label: __("Use an external/manual accounting reference"), type: "checkbox", description: __("Only System Manager or Accounts Manager may use an external reference."), onChange(value, values, modalView) { rebuildForField(context, value, values, modalView, "external_reference"); } });
		if (!context.values.external_reference) fields.push({ fieldname: "accounting_reference_doctype", label: __("Accounting Reference Type"), type: "select", required: true, options: (REFERENCE_TYPES[action] || []).map((value) => ({ value, label: value })) });
		fields.push({ fieldname: "accounting_reference_name", label: context.values.external_reference ? __("External Reference") : __("Accounting Reference"), type: "text", required: true });
		fields.push({ fieldname: "resolution_amount", label: __("Resolution Amount"), type: "number", required: action === "refund_required" || action === "issue_customer_credit", min: 0, step: "0.01" });
		fields.push({ fieldname: "resolution_date", label: __("Resolution Date"), type: "date", required: true });
		fields.push({ fieldname: "status_outcome", label: __("Consultation Status Outcome"), type: "select", required: true, options: [{ value: "no_status_change", label: __("No Status Change") }, ...(FINANCIAL_CANCEL_ACTIONS.has(action) ? [{ value: "cancel_consultation_after_financial_resolution", label: __("Cancel Consultation After Financial Resolution") }] : [])] });
		fields.push({ fieldname: "completion_note", label: __("Completion Evidence / Note"), type: "textarea", rows: 3, required: true });
	}
	return fields;
}

function actionsFor(context) {
	const record = context.record || {};
	const action = context.values.resolution_action || recordAction(record);
	const status = String(record.resolution_status || "");
	const actions = [];
	if (context.preflight.can_cancel) actions.push({ label: __("Cancel Consultation Safely"), danger: true, onClick: () => executeDirectCancel(context), closeOnSuccess: false });
	if (!record.name && context.canRecord && action) actions.push({ label: __("Record Resolution"), primary: true, onClick: (values) => recordDecision(context, values), closeOnSuccess: false });
	if (record.name && context.permissions.approve && !["Approved", "Completed", "Rejected"].includes(status)) actions.push({ label: __("Approve Resolution"), onClick: (values) => approve(context, values), closeOnSuccess: false });
	if (record.name && status === "Approved" && action === "retain_payment_clinical_cancel_only" && context.permissions.retain) actions.push({ label: __("Retain Payment & Cancel"), primary: true, onClick: (values) => retainPayment(context, values), closeOnSuccess: false });
	if (record.name && status === "Approved" && action === "reschedule_consultation" && context.permissions.reschedule) actions.push({ label: __("Complete Reschedule"), primary: true, onClick: (values) => reschedule(context, values), closeOnSuccess: false });
	if (record.name && status === "Approved" && MANUAL_ACTIONS.has(action) && context.permissions.complete) actions.push({ label: __("Complete Financial Resolution"), primary: true, onClick: (values) => completeManual(context, values), closeOnSuccess: false });
	return actions;
}

function modalSpec(context) {
	const preflight = context.preflight || {};
	const billing = preflight.billing_group_summary || {};
	const record = context.record || {};
	return {
		title: __("Reverse / Resolve Completed Consultation"), subtitle: context.consultation, size: "lg",
		metrics: [
			{ label: __("Consultation Status"), value: preflight.current_status || "—", tone: "neutral" },
			{ label: __("Linked Invoices"), value: Number(billing.linked_invoice_count || (preflight.linked_invoices || []).length || 0), tone: "info" },
			{ label: __("Paid Amount"), value: money(billing.paid_amount), tone: "success" },
			{ label: __("Outstanding"), value: money(billing.outstanding_amount), tone: Number(billing.outstanding_amount || 0) > 0 ? "warning" : "success" },
		],
		badges: record.name ? [{ label: `${__("Resolution")}: ${record.resolution_status || __("Draft")}`, status: record.resolution_status || "Draft" }, { label: record.resolution_action || humanAction(recordAction(record)), status: record.resolution_action || recordAction(record) }] : [],
		message: summaryMessage(preflight), fields: fieldsFor(context), values: context.values, actions: actionsFor(context),
	};
}

async function refreshContext(context) {
	const [preflight, options] = await Promise.all([call(API.preflight, { consultation_name: context.consultation }), call(API.options, { consultation_name: context.consultation })]);
	context.preflight = preflight || {};
	context.options = options || {};
	context.record = options?.existing_resolution || preflight?.existing_resolution || {};
	context.permissions = permissionState();
	context.canRecord = Boolean(options?.can_record_resolution && context.permissions.record);
	context.actionOptions = optionRows(options?.allowed_action_options || preflight?.allowed_action_options || []);
	context.values = {
		...context.values,
		resolution_action: recordAction(context.record) || context.values.resolution_action || context.actionOptions[0]?.value || "",
		accounting_reference_doctype: context.record.accounting_reference_doctype || context.values.accounting_reference_doctype || "",
		accounting_reference_name: context.record.accounting_reference_name || context.values.accounting_reference_name || "",
		resolution_amount: context.record.resolution_amount || context.values.resolution_amount || "",
		resolution_date: context.record.resolution_date || context.values.resolution_date || frappe.datetime?.get_today?.() || "",
		status_outcome: context.record.status_outcome || context.values.status_outcome || "no_status_change",
		completion_note: context.record.completion_note || context.values.completion_note || "",
		external_reference: context.record.external_reference ? 1 : (context.values.external_reference || 0),
	};
	return context;
}

function updateModal(context, patch = {}) { context.modal?.update({ ...modalSpec(context), ...patch }); }
async function loadContextIntoModal(context) {
	context.modal?.update({ loading: true, busy: false, error: "" });
	try { await refreshContext(context); context.modal?.update({ loading: false, ...modalSpec(context) }); }
	catch (error) { context.modal?.update({ loading: false, busy: false, error: error?.message || __("Consultation resolution could not be loaded."), errorTitle: __("Resolution workflow unavailable"), onRetry: () => loadContextIntoModal(context) }); }
}

async function runAction(context, task, successMessage) {
	updateModal(context, { busy: true, error: "" });
	try {
		await task();
		frappe.show_alert({ message: successMessage, indicator: "green" });
		context.values = { ...context.values, reason: "" };
		await context.clinicalView?.loadDetail?.(context.consultation);
		if (String(context.clinicalView?.detail?.status || "") !== "Completed") {
			context.modal?.update({ busy: false }); context.modal?.close(); context.syncButton?.(); return;
		}
		await refreshContext(context); updateModal(context, { busy: false }); context.syncButton?.();
	} catch (error) { updateModal(context, { busy: false, error: error?.message || __("Consultation resolution action failed."), errorTitle: __("Resolution action failed") }); }
}

function executeDirectCancel(context) { return runAction(context, () => call(API.directCancel, { consultation_name: context.consultation, reason: context.values.reason || undefined }), __("Consultation cancelled safely.")); }
function recordDecision(context, values) {
	context.values = { ...context.values, ...values };
	if (!context.values.resolution_action) return updateModal(context, { error: __("Select a controlled resolution action."), errorTitle: __("Resolution required") });
	return runAction(context, () => call(API.record, { consultation_name: context.consultation, resolution_action: context.values.resolution_action, reason: context.values.reason || undefined }), __("Resolution decision recorded."));
}
function retainPayment(context, values) { context.values = { ...context.values, ...values }; return runAction(context, () => call(API.retain, { consultation_name: context.consultation, reason: context.values.reason || undefined }), __("Consultation cancelled with payment retained.")); }
function reschedule(context, values) {
	context.values = { ...context.values, ...values };
	if (!context.values.appointment_datetime) return updateModal(context, { error: __("New appointment date/time is required."), errorTitle: __("Appointment required") });
	return runAction(context, () => call(API.reschedule, { consultation_name: context.consultation, resolution_name: context.record?.name || undefined, appointment_datetime: serverDatetime(context.values.appointment_datetime), reason: context.values.reason || undefined }), __("Consultation reschedule resolution completed."));
}
function approve(context, values) { context.values = { ...context.values, ...values }; return runAction(context, () => call(API.approve, { resolution_name: context.record.name, note: context.values.reason || undefined }), __("Resolution approved.")); }

function validateManualEvidence(context) {
	const action = recordAction(context.record);
	const values = context.values;
	if (!values.completion_note?.trim()) throw new Error(__("Completion evidence / note is required."));
	if (!values.resolution_date) throw new Error(__("Resolution date is required."));
	if (!values.accounting_reference_name?.trim()) throw new Error(__("Accounting reference is required."));
	if (!values.external_reference && !values.accounting_reference_doctype) throw new Error(__("Accounting reference type is required."));
	if ((action === "refund_required" || action === "issue_customer_credit") && Number(values.resolution_amount || 0) <= 0) throw new Error(__("Resolution amount must be greater than zero for refund or customer credit resolutions."));
	if (values.status_outcome === "cancel_consultation_after_financial_resolution" && !FINANCIAL_CANCEL_ACTIONS.has(action)) throw new Error(__("Only refund or customer credit resolutions can cancel the consultation after financial resolution."));
}

function completeManual(context, values) {
	context.values = { ...context.values, ...values };
	try { validateManualEvidence(context); } catch (error) { return updateModal(context, { error: error.message, errorTitle: __("Completion evidence required") }); }
	return runAction(context, () => call(API.complete, {
		resolution_name: context.record.name, completion_note: context.values.completion_note,
		accounting_reference_doctype: context.values.external_reference ? undefined : context.values.accounting_reference_doctype,
		accounting_reference_name: context.values.accounting_reference_name, resolution_amount: context.values.resolution_amount || undefined,
		resolution_date: context.values.resolution_date, external_reference: context.values.external_reference ? 1 : 0,
		status_outcome: context.values.status_outcome || "no_status_change",
	}), __("Financial resolution evidence completed."));
}

async function openWorkflow(clinicalView, syncButton) {
	const consultation = String(clinicalView?.detail?.name || "").trim();
	if (!consultation || !window.VetEdgeEdgeModalPresenter?.open) return;
	const context = {
		consultation, clinicalView, syncButton, preflight: {}, options: {}, record: {}, canRecord: false, permissions: permissionState(), actionOptions: [],
		values: { reason: "", resolution_action: "", appointment_datetime: "", accounting_reference_doctype: "", accounting_reference_name: "", resolution_amount: "", resolution_date: frappe.datetime?.get_today?.() || "", status_outcome: "no_status_change", completion_note: "", external_reference: 0 },
	};
	context.modal = window.VetEdgeEdgeModalPresenter.open({ title: __("Reverse / Resolve Completed Consultation"), subtitle: consultation, size: "lg", loading: true, loadingMessage: __("Checking consultation, billing and clinical dependencies...") });
	await loadContextIntoModal(context);
}

export function installVetEdgeClinicalWorkflowModal(workspaceRoot, clinicalView) {
	if (!workspaceRoot || !clinicalView || !window.VetEdgeEdgeModalPresenter?.ready?.()) return { installed: false };
	activeInstall?.destroy?.();
	let button = null;
	const syncButton = () => {
		const completed = String(clinicalView?.detail?.status || "") === "Completed";
		const actions = workspaceRoot.querySelector(".clinical-statusbar .clinical-row-actions");
		if (!completed || !actions) { button?.remove(); button = null; return; }
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
	activeInstall = { installed: true, open: () => openWorkflow(clinicalView, syncButton), destroy() { observer.disconnect(); button?.remove(); } };
	return activeInstall;
}

if (typeof window !== "undefined") window.installVetEdgeClinicalWorkflowModal = installVetEdgeClinicalWorkflowModal;
