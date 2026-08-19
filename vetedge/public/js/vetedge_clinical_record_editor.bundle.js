const API = Object.freeze({
	get: "vetedge.services.clinical_record_editor.get_clinical_record_editor",
	save: "vetedge.services.clinical_record_editor.save_clinical_record_editor",
	createSchema: "vetedge.services.clinical_record_editor.get_clinical_record_create_schema",
	create: "vetedge.services.clinical_record_editor.create_clinical_record",
	remove: "vetedge.services.clinical_record_editor.delete_clinical_record",
	labResult: "vetedge.services.clinical_record_editor.get_lab_result_editor",
	saveLabResult: "vetedge.services.clinical_record_editor.save_lab_result_editor",
	saveLabRate: "vetedge.services.clinical_record_editor.save_lab_test_rate",
	workflow: "vetedge.services.clinical_workflow_ui.get_clinical_workflow_actions",
});

const call = (method, args = {}) => frappe.call({ method, args }).then((response) => response.message || {});
const presenter = () => window.VetEdgeEdgeModalPresenter;

function normalizedOptions(field) {
	if (Array.isArray(field.options)) return field.options;
	return String(field.options || "")
		.split("\n")
		.map((value) => value.trim())
		.filter(Boolean)
		.map((value) => ({ value, label: value }));
}

async function searchLink(field, query, values = {}) {
	if (field?.link_search_method) {
		const contextField = field.link_search_context_field || "";
		const contextValue = contextField ? values?.[contextField] : "";
		if (contextField && !contextValue) return [];
		const args = {
			txt: String(query || ""),
			page_length: 20,
		};
		if (contextField) args[contextField] = contextValue;
		const response = await frappe.call(field.link_search_method, args);
		return response.message || [];
	}
	if (!field?.options || Array.isArray(field.options)) return [];
	const response = await frappe.call("frappe.desk.search.search_link", {
		doctype: field.options,
		txt: String(query || ""),
		page_length: 20,
		reference_doctype: field.reference_doctype || undefined,
		ignore_user_permissions: 0,
	});
	return response.message || [];
}

function fieldSpec(field, context = {}) {
	const typeMap = {
		Select: "select",
		Link: "link",
		Check: "checkbox",
		Date: "date",
		Datetime: "datetime-local",
		Time: "time",
		Int: "number",
		Float: "number",
		Currency: "number",
		Percent: "number",
		"Small Text": "textarea",
		Text: "textarea",
		"Long Text": "textarea",
		Email: "email",
		Phone: "tel",
		MultiSelect: "multiselect",
		Attach: "text",
	};
	const spec = {
		fieldname: field.fieldname,
		label: field.label,
		type: typeMap[field.fieldtype] || "text",
		description: field.description || "",
		required: Boolean(field.reqd),
		readOnly: Boolean(field.read_only || field.fieldtype === "Attach"),
		default: field.value ?? "",
		linkSearchContextField: field.link_search_context_field || "",
	};
	if (field.fieldtype === "Select" || field.fieldtype === "MultiSelect") spec.options = normalizedOptions(field);
	if (field.fieldtype === "Link") {
		spec.selectedLabel = field.selected_label || field.value || "";
		spec.searcher = (query) => searchLink(field, query, context.getValues?.() || {});
	}
	spec.onChange = (value, values, presenterView) => context.onChange?.(field, value, values, presenterView);
	if (["Int", "Float", "Currency", "Percent"].includes(field.fieldtype)) spec.step = field.fieldtype === "Int" ? "1" : "any";
	if (["Small Text", "Text", "Long Text"].includes(field.fieldtype)) spec.rows = field.fieldtype === "Long Text" ? 5 : 3;
	return spec;
}

function valuesFromFields(fields = []) {
	return Object.fromEntries(fields.map((field) => [field.fieldname, field.value ?? (field.fieldtype === "MultiSelect" ? [] : "")]));
}

function buildFieldSpecs(fields = []) {
	const state = {
		values: valuesFromFields(fields),
		specs: [],
	};
	const context = {
		getValues: () => state.values,
		onChange: (field, _value, values, presenterView) => {
			state.values = { ...(values || {}) };
			for (const dependent of state.specs) {
				if (dependent.linkSearchContextField !== field.fieldname) continue;
				if (!state.values[dependent.fieldname]) continue;
				dependent.selectedLabel = "";
				presenterView?.setField?.(dependent, "");
			}
		},
	};
	state.specs = fields.map((field) => fieldSpec(field, context));
	return { fields: state.specs, values: state.values };
}

function sectionSpec(section, context = {}) {
	const spec = {
		title: section.title || "Details",
		message: section.message || "",
		columns: section.columns || [],
		rows: section.rows || [],
		rowKey: section.row_key || "name",
		emptyTitle: "No rows",
	};
	if (section.kind === "lab_results") {
		spec.rowActions = (section.rows || []).map((row) => {
			const actions = [];
			if (row.can_edit_result || row.result) {
				actions.push({
					label: row.result ? __("View / Edit Result") : __("Enter Result"),
					primary: !row.result,
					onClick: () => context.openLabResult?.(row),
				});
			}
			if (row.can_edit_result && ["Document Upload", "Mixed"].includes(row.result_format)) {
				actions.push({ label: __("Upload Result"), onClick: () => context.uploadLabResult?.(row) });
			}
			if (row.result_attachment) {
				actions.push({ label: __("Open Upload"), onClick: () => window.open(row.result_attachment, "_blank", "noopener,noreferrer") });
			}
			if (row.can_edit_rate) {
				actions.push({ label: __("Change Price"), onClick: () => context.editLabRate?.(row) });
			}
			return { key: row.name, row, actions };
		});
	}
	return spec;
}

function billingFrame(doctype, name, reload) {
	return {
		doc: { doctype, name },
		is_new: () => false,
		is_dirty: () => false,
		reload_doc: reload,
	};
}

function openNative(doctype, name) {
	if (!doctype || !name) return;
	frappe.set_route("Form", doctype, name);
}

async function uploadFile(file, doctype, docname) {
	if (!file) throw new Error(__("Select a file to upload."));
	const form = new FormData();
	form.append("file", file, file.name);
	form.append("is_private", "1");
	form.append("doctype", doctype);
	form.append("docname", docname);
	const csrf = frappe.csrf_token || frappe.boot?.csrf_token || "";
	const response = await fetch("/api/method/upload_file", {
		method: "POST",
		credentials: "same-origin",
		headers: csrf ? { "X-Frappe-CSRF-Token": csrf } : {},
		body: form,
	});
	const payload = await response.json();
	if (!response.ok || !payload?.message?.file_url) {
		throw new Error(payload?.exception || payload?.message || __("The laboratory report could not be uploaded."));
	}
	return payload.message.file_url;
}

function chooseFile() {
	return new Promise((resolve) => {
		const input = document.createElement("input");
		input.type = "file";
		input.accept = ".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.xls,.xlsx,.csv,.txt";
		input.style.position = "fixed";
		input.style.left = "-9999px";
		document.body.appendChild(input);
		input.addEventListener("change", () => {
			const file = input.files?.[0] || null;
			input.remove();
			resolve(file);
		}, { once: true });
		input.click();
	});
}

async function openCreateModal({ doctype, onSaved } = {}) {
	if (!doctype || !presenter()?.ready?.()) throw new Error(__("The EdgeSuite clinical record creator is unavailable."));
	const modal = presenter().open({
		title: __("Create Clinical Record"),
		subtitle: doctype,
		size: "xl",
		loading: true,
		loadingMessage: __("Preparing clinical record..."),
	});
	try {
		const schema = await call(API.createSchema, { doctype });
		const form = buildFieldSpecs(schema.fields || []);
		modal.update({
			loading: false,
			title: schema.title || __("Create Clinical Record"),
			subtitle: doctype,
			message: doctype === "Veterinary Lab Order"
				? __("Select the patient and required tests. Each test keeps its configured result format, upload rules, payment workflow and default price.")
				: __("Create the record inside EdgeSuite. Server-side clinical, branch and role rules remain authoritative."),
			fields: form.fields,
			values: form.values,
			actions: [{
				label: __("Create"),
				primary: true,
				closeOnSuccess: false,
				async onClick(values) {
					modal.update({ busy: true, error: "" });
					try {
						const created = await call(API.create, { doctype, values });
						frappe.show_alert({ message: __("Clinical record created."), indicator: "green" });
						modal.update({ busy: false });
						modal.close();
						await onSaved?.(created);
						window.setTimeout(() => openVetEdgeClinicalRecordEditor({ doctype, name: created.name, onSaved }), 0);
					} catch (error) {
						modal.update({ busy: false, error: error?.message || __("Clinical record could not be created."), errorTitle: __("Create failed") });
					}
				},
			}],
		});
	} catch (error) {
		modal.update({ loading: false, error: error?.message || __("Create form could not load."), errorTitle: __("Create unavailable") });
	}
	return modal;
}

export async function openVetEdgeClinicalRecordEditor({ doctype, name = null, onSaved } = {}) {
	if (!doctype || !presenter()?.ready?.()) {
		throw new Error("The EdgeSuite clinical record editor is unavailable.");
	}
	if (!name) return openCreateModal({ doctype, onSaved });

	const modal = presenter().open({
		title: __("Clinical Record"),
		subtitle: name,
		size: "xl",
		loading: true,
		loadingMessage: __("Loading clinical record..."),
	});
	let schema = {};
	let workflow = { actions: [], message: "" };

	const load = async () => {
		modal.update({ loading: true, busy: false, error: "" });
		try {
			const [recordSchema, workflowSchema] = await Promise.all([
				call(API.get, { doctype, name }),
				call(API.workflow, { doctype, name }),
			]);
			schema = recordSchema || {};
			workflow = workflowSchema || { actions: [], message: "" };
			const form = buildFieldSpecs(schema.fields || []);
			const context = {
				openLabResult: (row) => openLabResult(row),
				uploadLabResult: (row) => uploadLabResult(row),
				editLabRate: (row) => editLabRate(row),
			};
			const actions = [];
			if (schema.can_save) {
				actions.push({
					label: __("Save Changes"),
					primary: true,
					closeOnSuccess: false,
					async onClick(nextValues) {
						modal.update({ busy: true, error: "" });
						try {
							schema = await call(API.save, { doctype, name, values: nextValues });
							frappe.show_alert({ message: __("Clinical record updated."), indicator: "green" });
							await onSaved?.(schema);
							await load();
						} catch (error) {
							modal.update({ busy: false, error: error?.message || __("Clinical record could not be saved."), errorTitle: __("Save failed") });
						}
					},
				});
			}
			if (schema.can_bill && window.vetedgeBillingModal?.open) {
				actions.push({
					label: __("Billing & Payment"),
					closeOnSuccess: false,
					onClick: () => window.vetedgeBillingModal.open(billingFrame(doctype, name, load)),
				});
			}
			for (const workflowAction of workflow.actions || []) {
				actions.push({
					label: workflowAction.label,
					primary: Boolean(workflowAction.primary),
					danger: Boolean(workflowAction.danger),
					closeOnSuccess: false,
					onClick: () => runWorkflowAction(workflowAction),
				});
			}
			if (schema.can_delete) {
				actions.push({ label: __("Delete"), danger: true, closeOnSuccess: false, onClick: () => confirmDelete() });
			}
			if (doctype !== "Veterinary Vital Signs") {
				actions.push({ label: __("Open Native Form"), closeOnSuccess: false, onClick: () => openNative(doctype, name) });
			}
			const billingMessage = schema.billing_state?.message || "";
			modal.update({
				loading: false,
				busy: false,
				title: schema.title || doctype,
				subtitle: `${schema.patient_name || doctype} · ${name}`,
				badges: [
					{ label: schema.status || __("Draft"), status: schema.status || "Draft" },
					...(schema.billing_state?.has_submitted_invoice ? [{ label: schema.billing_state.is_paid ? __("Paid") : __("Invoice Submitted"), status: schema.billing_state.is_paid ? "Paid" : "Submitted" }] : []),
				],
				message: [
					billingMessage,
					workflow.message,
					schema.can_save
						? __("Edit the permitted fields below. Workflow, submitted billing and stock protections remain server-enforced.")
						: __("This record is read-only for its current permission, workflow or billing state."),
				].filter(Boolean).join("\n"),
				fields: form.fields,
				values: form.values,
				sections: (schema.sections || []).map((section) => sectionSpec(section, context)),
				actions,
			});
		} catch (error) {
			modal.update({
				loading: false,
				busy: false,
				error: error?.message || __("Clinical record could not be loaded."),
				errorTitle: __("Clinical record unavailable"),
				onRetry: load,
			});
		}
	};

	const executeWorkflowAction = async (action, confirmationModal = null) => {
		modal.update({ busy: true, error: "" });
		confirmationModal?.update?.({ busy: true, error: "" });
		try {
			const result = await call(action.method, action.args || {});
			confirmationModal?.update?.({ busy: false });
			confirmationModal?.close?.();
			frappe.show_alert({ message: __("Workflow updated to {0}.", [result.status || action.target_status || action.label]), indicator: "green" });
			await onSaved?.(result);
			await load();
		} catch (error) {
			modal.update({ busy: false });
			const payload = {
				busy: false,
				error: error?.message || __("The workflow action could not be completed."),
				errorTitle: __("Workflow action blocked"),
			};
			if (confirmationModal) confirmationModal.update(payload);
			else modal.update(payload);
		}
	};

	const runWorkflowAction = async (action) => {
		if (!action?.method) return;
		if (!action.confirm) {
			await executeWorkflowAction(action);
			return;
		}
		const confirmModal = presenter().open({
			title: action.label,
			subtitle: name,
			size: "sm",
			message: action.confirm,
			actions: [{
				label: action.label,
				primary: !action.danger,
				danger: Boolean(action.danger),
				closeOnSuccess: false,
				onClick: () => executeWorkflowAction(action, confirmModal),
			}],
		});
	};

	const openLabResult = async (row) => {
		const resultModal = presenter().open({ title: __("Laboratory Result"), subtitle: row.lab_test || "", size: "lg", loading: true });
		const refreshResult = async () => {
			try {
				const result = await call(API.labResult, { lab_order: name, row_name: row.name });
				const actions = [];
				if (result.can_save) {
					actions.push({
						label: __("Save Result"), primary: true, closeOnSuccess: false,
						async onClick(values) {
							resultModal.update({ busy: true, error: "" });
							try {
								await call(API.saveLabResult, { lab_order: name, row_name: row.name, values });
								frappe.show_alert({ message: __("Laboratory result saved."), indicator: "green" });
								await load();
								await refreshResult();
							} catch (error) {
								resultModal.update({ busy: false, error: error?.message || __("Laboratory result could not be saved."), errorTitle: __("Save failed") });
							}
						},
					});
				}
				if (result.can_upload) actions.push({ label: __("Upload Report"), closeOnSuccess: false, onClick: () => uploadLabResult({ ...row, result_attachment: result.result_attachment }, refreshResult) });
				if (result.result_attachment) actions.push({ label: __("Open Uploaded Report"), closeOnSuccess: false, onClick: () => window.open(result.result_attachment, "_blank", "noopener,noreferrer") });
				resultModal.update({
					loading: false,
					busy: false,
					title: result.title || row.lab_test,
					subtitle: `${result.result_format} · ${result.result_status || result.status || "Pending"}`,
					message: __("The configured report type controls which result fields are available. Payment and review gates remain authoritative."),
					fields: (result.fields || []).map(fieldSpec),
					values: valuesFromFields(result.fields || []),
					actions,
				});
			} catch (error) {
				resultModal.update({ loading: false, busy: false, error: error?.message || __("Laboratory result could not load."), errorTitle: __("Result unavailable") });
			}
		};
		await refreshResult();
	};

	const uploadLabResult = async (row, nestedRefresh = null) => {
		const file = await chooseFile();
		if (!file) return;
		modal.update({ busy: true, error: "" });
		try {
			const fileUrl = await uploadFile(file, "Veterinary Lab Order", name);
			await call(API.saveLabResult, { lab_order: name, row_name: row.name, values: { result_attachment: fileUrl } });
			frappe.show_alert({ message: __("Laboratory report uploaded."), indicator: "green" });
			await load();
			await nestedRefresh?.();
		} catch (error) {
			modal.update({ busy: false, error: error?.message || __("Laboratory report could not be uploaded."), errorTitle: __("Upload failed") });
		}
	};

	const editLabRate = async (row) => {
		const priceModal = presenter().open({
			title: __("Change Lab Price"),
			subtitle: row.lab_test || "",
			size: "sm",
			message: __("Price changes are allowed only before invoice submission. If a draft invoice exists, it is synchronized automatically."),
			fields: [{ fieldname: "rate", label: __("Rate"), type: "number", step: "any", required: true, default: row.rate || 0 }],
			values: { rate: row.rate || 0 },
			actions: [{
				label: __("Update Price"), primary: true, closeOnSuccess: false,
				async onClick(values) {
					priceModal.update({ busy: true, error: "" });
					try {
						await call(API.saveLabRate, { lab_order: name, row_name: row.name, rate: values.rate });
						frappe.show_alert({ message: __("Lab price updated and draft billing synchronized."), indicator: "green" });
						priceModal.update({ busy: false });
						priceModal.close();
						await load();
						await onSaved?.(schema);
					} catch (error) {
						priceModal.update({ busy: false, error: error?.message || __("Lab price could not be updated."), errorTitle: __("Price update failed") });
					}
				},
			}],
		});
	};

	const confirmDelete = () => {
		const confirmModal = presenter().open({
			title: __("Delete Clinical Record"),
			subtitle: name,
			size: "sm",
			message: __("Delete this record permanently? Billing, submitted, administered, stock-posted and result-bearing records are protected from deletion."),
			actions: [{
				label: __("Delete Permanently"), danger: true, closeOnSuccess: false,
				async onClick() {
					confirmModal.update({ busy: true, error: "" });
					try {
						await call(API.remove, { doctype, name });
						confirmModal.update({ busy: false });
						confirmModal.close();
						modal.update({ busy: false });
						modal.close();
						frappe.show_alert({ message: __("Clinical record deleted."), indicator: "green" });
						await onSaved?.({ deleted: true, doctype, name });
					} catch (error) {
						confirmModal.update({ busy: false, error: error?.message || __("Clinical record could not be deleted."), errorTitle: __("Delete blocked") });
					}
				},
			}],
		});
	};

	await load();
	return modal;
}

export function installVetEdgeClinicalRecordEditor() {
	if (typeof window !== "undefined") {
		window.VetEdgeClinicalRecordEditor = {
			open: openVetEdgeClinicalRecordEditor,
			create: (doctype, onSaved) => openCreateModal({ doctype, onSaved }),
			ready: () => Boolean(presenter()?.ready?.()),
		};
	}
	return true;
}

installVetEdgeClinicalRecordEditor();
export default openVetEdgeClinicalRecordEditor;