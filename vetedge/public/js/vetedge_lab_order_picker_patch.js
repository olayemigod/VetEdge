(function () {
	"use strict";

	if (window.__vetedgeLabOrderPickerPatchInstalled) return;
	window.__vetedgeLabOrderPickerPatchInstalled = true;

	const DOCTYPE = "Veterinary Lab Order";
	const CREATE_SCHEMA = "vetedge.services.clinical_record_editor.get_clinical_record_create_schema";
	const CREATE_RECORD = "vetedge.services.clinical_record_editor.create_clinical_record";

	const presenter = () => window.VetEdgeEdgeModalPresenter;
	const call = (method, args = {}) => frappe.call({ method, args }).then((response) => response.message || {});

	async function searchLink(doctype, query) {
		const response = await frappe.call("frappe.desk.search.search_link", {
			doctype,
			txt: String(query || ""),
			page_length: 20,
			ignore_user_permissions: 0,
		});
		return response.message || [];
	}

	function linkField(field, initialValues = {}) {
		const initialValue = initialValues[field.fieldname] || "";
		return {
			fieldname: field.fieldname,
			label: field.label,
			type: "link",
			required: Boolean(field.reqd),
			description: field.description || "",
			selectedLabel: initialValues[`${field.fieldname}_label`] || initialValue || field.selected_label || "",
			searcher: (query) => searchLink(field.options, query),
			placeholder: __("Search {0}", [field.label || field.options || __("records")]),
		};
	}

	function textField(field) {
		return {
			fieldname: field.fieldname,
			label: field.label,
			type: ["Small Text", "Text", "Long Text"].includes(field.fieldtype) ? "textarea" : "text",
			required: Boolean(field.reqd),
			description: field.description || "",
			rows: 3,
		};
	}

	function selectedSection(selected, remove) {
		return {
			title: __("Selected Lab Tests"),
			message: selected.length
				? __("Each test keeps its configured result type, upload/review rules and default billing rate.")
				: __("Choose a Lab Test from the dropdown above. You can add more than one test to the same order."),
			columns: [
				{ fieldname: "label", label: __("Lab Test") },
				{ fieldname: "result_format", label: __("Report Type") },
				{ fieldname: "price", label: __("Default Price") },
			],
			rows: selected.map((row) => ({
				name: row.value,
				label: row.label,
				result_format: row.result_format,
				price: row.price,
			})),
			rowKey: "name",
			rowActions: selected.map((row) => ({
				key: row.value,
				row,
				actions: [{ label: __("Remove"), danger: true, onClick: () => remove(row.value) }],
			})),
			emptyTitle: __("No Lab Tests Selected"),
		};
	}

	function normalizeTestOption(option) {
		const description = String(option.description || "");
		const parts = description.split(" · ");
		return {
			value: String(option.value || option.name || ""),
			label: String(option.label || option.value || option.name || ""),
			result_format: parts[0] || __("Value Driven"),
			price: parts.slice(1).join(" · ") || "—",
			description,
		};
	}

	async function openLabOrderCreate(onSaved, initialValues = {}) {
		if (!presenter()?.ready?.()) throw new Error(__("The EdgeSuite clinical record creator is unavailable."));

		const modal = presenter().open({
			title: __("Create Lab Order"),
			subtitle: __("Laboratory"),
			size: "xl",
			loading: true,
			loadingMessage: __("Preparing Lab Tests..."),
		});
		let selected = [];
		let baseFields = [];
		let testOptions = [];
		let values = {
			patient: initialValues.patient || "",
			service_branch: initialValues.service_branch || "",
			sample_notes: "",
			lab_test_picker: "",
		};

		const paint = () => {
			const remove = (value) => {
				selected = selected.filter((row) => row.value !== value);
				paint();
			};
			const picker = {
				fieldname: "lab_test_picker",
				label: __("Lab Test"),
				type: "select",
				options: testOptions.map((row) => ({ value: row.value, label: row.label, description: row.description })),
				placeholder: __("Select a Lab Test"),
				description: __("Select one test at a time. The selected tests are listed below."),
				onChange(value, nextValues) {
					if (!value) return;
					const option = testOptions.find((row) => row.value === value);
					if (option && !selected.some((row) => row.value === value)) selected.push(option);
					values = { ...nextValues, lab_test_picker: "" };
					paint();
				},
			};
			modal.update({
				loading: false,
				busy: false,
				title: __("Create Lab Order"),
				subtitle: initialValues.patient
					? __("New standalone Laboratory Order for {0}", [initialValues.patient_label || initialValues.patient])
					: __("Standalone Laboratory Service"),
				message: __("Choose the Patient, then add one or more Lab Tests from the dropdown. A patient may have multiple Lab Orders over time; creating this order never replaces an earlier one. Result format, permissions and billing remain server-controlled."),
				fields: [...baseFields, picker],
				values,
				sections: [selectedSection(selected, remove)],
				actions: [{
					label: __("Create Lab Order"),
					primary: true,
					closeOnSuccess: false,
					async onClick(nextValues) {
						if (!selected.length) {
							modal.update({ error: __("Select at least one Lab Test before creating the order."), errorTitle: __("Lab Test Required") });
							return;
						}
						modal.update({ busy: true, error: "" });
						try {
							const created = await call(CREATE_RECORD, {
								doctype: DOCTYPE,
								values: {
									patient: nextValues.patient,
									service_branch: nextValues.service_branch,
									sample_notes: nextValues.sample_notes,
									lab_tests: selected.map((row) => row.value),
								},
							});
							frappe.show_alert({ message: __("Lab Order created."), indicator: "green" });
							modal.update({ busy: false });
							modal.close();
							await onSaved?.(created);
							window.setTimeout(() => window.VetEdgeClinicalRecordEditor?.open?.({ doctype: DOCTYPE, name: created.name, onSaved }), 0);
						} catch (error) {
							modal.update({ busy: false, error: error?.message || __("Lab Order could not be created."), errorTitle: __("Create Failed") });
						}
					},
				}],
			});
		};

		try {
			const schema = await call(CREATE_SCHEMA, { doctype: DOCTYPE });
			const testField = (schema.fields || []).find((field) => field.fieldname === "lab_tests");
			testOptions = (testField?.options || []).map(normalizeTestOption).filter((row) => row.value);
			baseFields = (schema.fields || [])
				.filter((field) => field.fieldname !== "lab_tests")
				.map((field) => field.fieldtype === "Link" ? linkField(field, initialValues) : textField(field));
			values = Object.fromEntries(baseFields.map((field) => [field.fieldname, initialValues[field.fieldname] || ""]));
			values.lab_test_picker = "";
			paint();
		} catch (error) {
			modal.update({ loading: false, error: error?.message || __("Lab Test options could not be loaded."), errorTitle: __("Lab Order Unavailable") });
		}
		return modal;
	}

	function install() {
		const editor = window.VetEdgeClinicalRecordEditor;
		if (!editor?.create || editor.__labDropdownPatched) return Boolean(editor?.__labDropdownPatched);
		const originalCreate = editor.create.bind(editor);
		editor.create = (doctype, onSaved) => doctype === DOCTYPE ? openLabOrderCreate(onSaved) : originalCreate(doctype, onSaved);
		editor.__labDropdownPatched = true;
		return true;
	}

	window.VetEdgeLabOrderPickerPatch = {
		install,
		open({ onSaved = null, patient = "", patientLabel = "", serviceBranch = "" } = {}) {
			return openLabOrderCreate(onSaved, {
				patient,
				patient_label: patientLabel || patient,
				service_branch: serviceBranch,
				service_branch_label: serviceBranch,
			});
		},
	};
	install();
})();
