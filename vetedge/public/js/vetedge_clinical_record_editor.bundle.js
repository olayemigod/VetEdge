const API = Object.freeze({
	get: "vetedge.services.clinical_record_editor.get_clinical_record_editor",
	save: "vetedge.services.clinical_record_editor.save_clinical_record_editor",
});

const call = (method, args = {}) => frappe.call({ method, args }).then((response) => response.message || {});
const presenter = () => window.VetEdgeEdgeModalPresenter;

function normalizedOptions(field) {
	return String(field.options || "")
		.split("\n")
		.map((value) => value.trim())
		.filter(Boolean)
		.map((value) => ({ value, label: value }));
}

async function searchLink(field, query) {
	if (!field?.options) return [];
	const response = await frappe.call("frappe.desk.search.search_link", {
		doctype: field.options,
		txt: String(query || ""),
		page_length: 20,
		ignore_user_permissions: 0,
	});
	return response.message || [];
}

function fieldValue(field) {
	const value = field.value ?? "";
	if (field.fieldtype === "Datetime" && value) return String(value).replace(" ", "T").slice(0, 16);
	return value;
}

function fieldSpec(field) {
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
	};
	const isReadOnly = Boolean(field.read_only);
	const spec = {
		fieldname: field.fieldname,
		label: field.label,
		type: typeMap[field.fieldtype] || "text",
		description: field.description || "",
		required: Boolean(field.reqd),
		readOnly: isReadOnly,
		disabled: isReadOnly && ["Select", "Link", "Check"].includes(field.fieldtype),
		default: fieldValue(field),
	};
	if (field.fieldtype === "Select") spec.options = normalizedOptions(field);
	if (field.fieldtype === "Link") {
		spec.selectedLabel = field.value || "";
		spec.searcher = (query) => searchLink(field, query);
	}
	if (["Int", "Float", "Currency", "Percent"].includes(field.fieldtype)) spec.step = field.fieldtype === "Int" ? "1" : "any";
	if (["Small Text", "Text", "Long Text"].includes(field.fieldtype)) spec.rows = field.fieldtype === "Long Text" ? 5 : 3;
	return spec;
}

function sectionSpec(section) {
	return {
		title: section.title || "Details",
		message: section.message || "",
		columns: section.columns || [],
		rows: section.rows || [],
		rowKey: section.row_key || "name",
		emptyTitle: "No rows",
	};
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

function serializedValues(schema, values) {
	const fieldMap = Object.fromEntries((schema.fields || []).map((field) => [field.fieldname, field]));
	const payload = {};
	for (const [fieldname, raw] of Object.entries(values || {})) {
		const field = fieldMap[fieldname];
		if (!field || field.read_only) continue;
		let value = raw;
		if (field.fieldtype === "Datetime" && value) {
			value = String(value).replace("T", " ");
			if (value.length === 16) value = `${value}:00`;
		}
		if (field.fieldtype === "Check") value = value ? 1 : 0;
		payload[fieldname] = value ?? "";
	}
	return payload;
}

export async function openVetEdgeClinicalRecordEditor({ doctype, name, onSaved } = {}) {
	if (!doctype || !name || !presenter()?.ready?.()) {
		throw new Error("The EdgeSuite clinical record editor is unavailable.");
	}
	const modal = presenter().open({
		title: __("Clinical Record"),
		subtitle: name,
		size: "xl",
		loading: true,
		loadingMessage: __("Loading clinical record..."),
	});
	let schema = {};

	const load = async () => {
		modal.update({ loading: true, busy: false, error: "" });
		try {
			schema = await call(API.get, { doctype, name });
			const values = Object.fromEntries((schema.fields || []).map((field) => [field.fieldname, fieldValue(field)]));
			const actions = [];
			if (schema.can_save) {
				actions.push({
					label: __("Save Changes"),
					primary: true,
					closeOnSuccess: false,
					async onClick(nextValues) {
						modal.update({ busy: true, error: "" });
						try {
							schema = await call(API.save, { doctype, name, values: serializedValues(schema, nextValues) });
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
			if (doctype !== "Veterinary Vital Signs") {
				actions.push({
					label: __("Open Native Form"),
					closeOnSuccess: false,
					onClick: () => openNative(doctype, name),
				});
			}
			modal.update({
				loading: false,
				busy: false,
				title: schema.title || doctype,
				subtitle: `${doctype} · ${name}`,
				badges: [{ label: schema.status || __("Draft"), status: schema.status || "Draft" }],
				message: schema.can_save
					? __("Edit the safe clinical fields below without leaving EdgeSuite. Workflow-controlled fields remain protected.")
					: __("This record is read-only for your current permissions or document state."),
				fields: (schema.fields || []).map(fieldSpec),
				values,
				sections: (schema.sections || []).map(sectionSpec),
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

	await load();
	return modal;
}

export function installVetEdgeClinicalRecordEditor() {
	if (typeof window !== "undefined") {
		window.VetEdgeClinicalRecordEditor = {
			open: openVetEdgeClinicalRecordEditor,
			ready: () => Boolean(presenter()?.ready?.()),
		};
	}
	return true;
}

installVetEdgeClinicalRecordEditor();
export default openVetEdgeClinicalRecordEditor;