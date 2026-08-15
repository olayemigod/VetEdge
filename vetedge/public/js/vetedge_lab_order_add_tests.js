(function () {
	"use strict";

	if (window.__vetedgeLabOrderAddTestsInstalled) return;
	window.__vetedgeLabOrderAddTestsInstalled = true;

	const GET = "vetedge.services.lab_order_extensions.get_addable_lab_tests";
	const ADD = "vetedge.services.lab_order_extensions.add_lab_tests";
	const contexts = new Map();

	const presenter = () => window.VetEdgeEdgeModalPresenter;
	const call = (method, args = {}) => frappe.call({ method, args }).then((response) => response.message || {});

	function selectedSection(selected, remove) {
		return {
			title: __("Tests to Add"),
			message: selected.length
				? __("These tests will be added to the existing Lab Order and synchronized to any draft invoice.")
				: __("Choose one or more tests from the dropdown."),
			columns: [
				{ fieldname: "label", label: __("Lab Test") },
				{ fieldname: "result_format", label: __("Report Type") },
				{ fieldname: "rate", label: __("Default Rate"), fieldtype: "Currency" },
			],
			rows: selected.map((row) => ({ name: row.value, ...row })),
			rowKey: "name",
			rowActions: selected.map((row) => ({
				key: row.value,
				row,
				actions: [{ label: __("Remove"), danger: true, onClick: () => remove(row.value) }],
			})),
			emptyTitle: __("No additional tests selected"),
		};
	}

	async function openAddTests(context) {
		if (!presenter()?.ready?.()) throw new Error(__("The EdgeSuite modal runtime is unavailable."));
		const options = await call(GET, { lab_order: context.name });
		if (!options.length) {
			frappe.show_alert({ message: __("No additional active Lab Tests are available for this order."), indicator: "blue" });
			return;
		}
		let selected = [];
		let values = { lab_test_picker: "" };
		const modal = presenter().open({ title: __("Add Lab Tests"), subtitle: context.name, size: "lg" });
		const paint = () => {
			const remove = (value) => {
				selected = selected.filter((row) => row.value !== value);
				paint();
			};
			modal.update({
				message: __("Add tests only while the Lab Order and linked billing remain editable. Submitted invoices and deceased-patient service rules are enforced on the server."),
				fields: [{
					fieldname: "lab_test_picker",
					label: __("Lab Test"),
					type: "select",
					options: options.filter((row) => !selected.some((item) => item.value === row.value)),
					placeholder: __("Select a Lab Test"),
					onChange(value, nextValues) {
						const option = options.find((row) => row.value === value);
						if (option && !selected.some((row) => row.value === value)) selected.push(option);
						values = { ...nextValues, lab_test_picker: "" };
						paint();
					},
				}],
				values,
				sections: [selectedSection(selected, remove)],
				actions: [{
					label: __("Add Selected Tests"),
					primary: true,
					disabled: !selected.length,
					closeOnSuccess: false,
					async onClick() {
						if (!selected.length) return;
						modal.update({ busy: true, error: "" });
						try {
							await call(ADD, { lab_order: context.name, lab_tests: selected.map((row) => row.value) });
							frappe.show_alert({ message: __("Lab Tests added."), indicator: "green" });
							modal.update({ busy: false });
							modal.close();
							context.parent?.close?.();
							await context.onSaved?.();
							window.setTimeout(() => window.VetEdgeClinicalRecordEditor?.open?.({
								doctype: "Veterinary Lab Order",
								name: context.name,
								onSaved: context.onSaved,
							}), 0);
						} catch (error) {
							modal.update({ busy: false, error: error?.message || __("Lab Tests could not be added."), errorTitle: __("Add failed") });
						}
					},
				}],
			});
		};
		paint();
	}

	function injectButton(context) {
		const footers = [...document.querySelectorAll(".vetedge-edge-modal-actions")];
		const footer = footers.at(-1);
		if (!footer || footer.querySelector("[data-vetedge-add-lab-tests]")) return;
		const button = document.createElement("button");
		button.type = "button";
		button.className = "edge-button";
		button.dataset.vetedgeAddLabTests = "1";
		button.textContent = __("Add Lab Tests");
		button.addEventListener("click", () => openAddTests(context).catch((error) => frappe.msgprint(error?.message || __("Lab Tests could not be loaded."))));
		footer.prepend(button);
	}

	function install() {
		const editor = window.VetEdgeClinicalRecordEditor;
		if (!editor?.open || editor.__labAddTestsWrapped) return Boolean(editor?.__labAddTestsWrapped);
		const originalOpen = editor.open.bind(editor);
		editor.open = async function (options = {}) {
			const result = await originalOpen(options);
			if (options?.doctype === "Veterinary Lab Order" && options?.name) {
				const context = { name: options.name, onSaved: options.onSaved, parent: result };
				contexts.set(options.name, context);
				window.setTimeout(() => injectButton(context), 60);
				window.setTimeout(() => injectButton(context), 220);
			}
			return result;
		};
		editor.__labAddTestsWrapped = true;
		return true;
	}

	window.VetEdgeLabOrderAddTests = { install };
	install();
	window.setTimeout(install, 0);
	window.setTimeout(install, 250);
})();
