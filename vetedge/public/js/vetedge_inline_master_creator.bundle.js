const API = "vetedge.services.inline_master.create_inline_master";

function ensurePresenter() {
	return new Promise((resolve, reject) => {
		if (window.VetEdgeEdgeModalPresenter?.ready?.()) {
			resolve(window.VetEdgeEdgeModalPresenter);
			return;
		}
		frappe.require("vetedge_edge_modal_presenter.bundle.js", () => {
			if (window.VetEdgeEdgeModalPresenter?.ready?.()) resolve(window.VetEdgeEdgeModalPresenter);
			else reject(new Error(__("The EdgeSuite modal runtime is unavailable.")));
		});
	});
}

function specFor(doctype, term, context = {}) {
	if (doctype === "Customer") {
		return {
			title: __("Create Pet Owner"),
			subtitle: __("Create the owner without leaving the Patient form."),
			fields: [
				{ fieldname: "owner_name", label: __("Owner Name"), type: "text", required: true, default: term || "" },
				{ fieldname: "mobile_no", label: __("Mobile Number"), type: "tel", default: "" },
				{ fieldname: "email_id", label: __("Email"), type: "email", default: "" },
			],
			validate(values) {
				if (!String(values.owner_name || "").trim()) return __("Owner Name is required.");
				if (!String(values.mobile_no || "").trim() && !String(values.email_id || "").trim()) {
					return __("Enter a mobile number or email address for the Pet Owner.");
				}
				return "";
			},
		};
	}
	if (doctype === "Veterinary Species") {
		return {
			title: __("Create Species"),
			subtitle: __("Add a reusable Veterinary Species master."),
			fields: [
				{ fieldname: "species_name", label: __("Species Name"), type: "text", required: true, default: term || "" },
				{ fieldname: "description", label: __("Description"), type: "textarea", rows: 3, default: "" },
			],
		};
	}
	if (doctype === "Veterinary Breed") {
		if (!context.species) throw new Error(__("Select Species before creating a Breed."));
		return {
			title: __("Create Breed"),
			subtitle: __("The new Breed will belong to {0}.", [context.species_label || context.species]),
			fields: [
				{ fieldname: "breed_name", label: __("Breed Name"), type: "text", required: true, default: term || "" },
				{ fieldname: "species", label: __("Species"), type: "text", readOnly: true, default: context.species },
				{ fieldname: "description", label: __("Description"), type: "textarea", rows: 3, default: "" },
			],
		};
	}
	throw new Error(__("This linked master is not approved for inline creation."));
}

export async function createVetEdgeInlineMaster({ doctype, term = "", context = {} } = {}) {
	const presenter = await ensurePresenter();
	const spec = specFor(doctype, String(term || "").trim(), context || {});
	return new Promise((resolve, reject) => {
		let settled = false;
		const finish = (value, error = null) => {
			if (settled) return;
			settled = true;
			if (error) reject(error);
			else resolve(value || null);
		};
		const modal = presenter.open({
			title: spec.title,
			subtitle: spec.subtitle,
			size: "md",
			fields: spec.fields,
			values: Object.fromEntries(spec.fields.map((field) => [field.fieldname, field.default ?? ""])),
			onClose: () => finish(null),
			actions: [{
				label: __("Create"),
				primary: true,
				closeOnSuccess: false,
				async onClick(values) {
					const validation = spec.validate?.(values) || "";
					if (validation) {
						modal.update({ error: validation, errorTitle: __("Complete the required details") });
						return;
					}
					modal.update({ busy: true, error: "" });
					try {
						const response = await frappe.call(API, {
							doctype,
							label: term,
							context,
							values,
						});
						const created = response.message || null;
						modal.update({ busy: false });
						finish(created);
						modal.close();
					} catch (error) {
						modal.update({ busy: false, error: error?.message || __("The linked master could not be created."), errorTitle: __("Create failed") });
					}
				},
			}],
		});
	});
}

if (typeof window !== "undefined") {
	window.VetEdgeInlineMasterCreator = { create: createVetEdgeInlineMaster };
}
