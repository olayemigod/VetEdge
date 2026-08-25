(function installVetEdgeReportFilterUI(global) {
	"use strict";

	const optionList = (values, allLabel) => [
		{ value: "", label: allLabel },
		...values.map((value) => ({ value, label: value })),
	];

	const consultationStatuses = optionList(
		["Draft", "In Progress", "Awaiting Payment", "Pending Dispensary", "Ready for Treatment", "Completed", "Cancelled"],
		"All Statuses",
	);
	const paymentStatuses = optionList(
		["Not Billed", "Unpaid", "Partly Paid", "Paid", "Cancelled"],
		"All Payment Statuses",
	);
	const labStatuses = optionList(
		["Draft", "Ordered", "Sample Collected", "Sent to Lab", "In Progress", "Result Pending", "Result Entered", "Awaiting Review", "Reviewed", "Completed", "Cancelled"],
		"All Lab Statuses",
	);
	const vaccinationStatuses = optionList(
		["Draft", "Awaiting Payment", "Pending Administration", "Administered", "Cancelled"],
		"All Vaccination Statuses",
	);
	const dueStatuses = optionList(["Due Soon", "Overdue"], "All Due States");
	const patientStatuses = optionList(["Active", "Inactive", "Deceased"], "All Patient Statuses");
	const outstandingOptions = [
		{ value: "", label: "All Owners" },
		{ value: "1", label: "Outstanding Only" },
	];
	const serviceCategories = optionList(
		["Consultation Service", "Treatment", "Registration", "Vaccination", "Lab", "Grooming", "Boarding", "Hospitalisation", "Dispensary / Pharmacy", "General / Other"],
		"All Service Categories",
	);

	const DEFINITIONS = Object.freeze({
		"Consultation Register": [
			{ field: "patient", type: "link", label: "Patient" },
			{ field: "customer", type: "link", label: "Owner" },
			{ field: "practitioner", type: "link", label: "Practitioner" },
			{ field: "consultation_type", type: "link", label: "Consultation Type" },
			{ field: "status", type: "select", label: "Status", options: consultationStatuses },
			{ field: "payment_status", type: "select", label: "Payment Status", options: paymentStatuses },
		],
		"Planned Treatment": [
			{ field: "patient", type: "link", label: "Patient" },
			{ field: "customer", type: "link", label: "Owner" },
			{ field: "practitioner", type: "link", label: "Practitioner" },
			{ field: "consultation_type", type: "link", label: "Consultation Type" },
			{ field: "item", type: "link", label: "Treatment Item" },
			{ field: "status", type: "select", label: "Consultation Status", options: consultationStatuses },
		],
		"Lab Order Report": [
			{ field: "patient", type: "link", label: "Patient" },
			{ field: "customer", type: "link", label: "Owner" },
			{ field: "practitioner", type: "link", label: "Requested By" },
			{ field: "status", type: "select", label: "Lab Status", options: labStatuses },
		],
		"Laboratory Report": [
			{ field: "patient", type: "link", label: "Patient", serverReport: "Lab Order Report" },
			{ field: "customer", type: "link", label: "Owner", serverReport: "Lab Order Report" },
			{ field: "practitioner", type: "link", label: "Requested By", serverReport: "Lab Order Report" },
			{ field: "status", type: "select", label: "Lab Status", options: labStatuses },
		],
		"Vaccination Report": [
			{ field: "patient", type: "link", label: "Patient" },
			{ field: "customer", type: "link", label: "Owner" },
			{ field: "practitioner", type: "link", label: "Administered By" },
			{ field: "vaccine", type: "link", label: "Vaccine" },
			{ field: "status", type: "select", label: "Status", options: vaccinationStatuses },
			{ field: "due_status", type: "select", label: "Due Status", options: dueStatuses },
		],
		"Patient Register": [
			{ field: "customer", type: "link", label: "Owner" },
			{ field: "species", type: "link", label: "Species" },
			{ field: "breed", type: "link", label: "Breed" },
			{ field: "status", type: "select", label: "Patient Status", options: patientStatuses },
		],
		"Owner Register": [
			{ field: "customer", type: "link", label: "Owner" },
			{ field: "outstanding_only", type: "select", label: "Receivables", options: outstandingOptions },
		],
		"Service Revenue Breakdown": [
			{ field: "service_category", type: "select", label: "Service Category", options: serviceCategories },
			{ field: "practitioner", type: "link", label: "Practitioner" },
			{ field: "item", type: "link", label: "Item" },
		],
	});

	function linkNode({ h, EdgeLinkField, reportName, filters, searcher, definition, onChange }) {
		const field = definition.field;
		return h(EdgeLinkField, {
			modelValue: filters[field] || "",
			selectedLabel: filters[field] || "",
			label: __(definition.label),
			placeholder: __(`All ${definition.label}s`),
			searcher: (term) => searcher(definition.serverReport || reportName, field, term || ""),
			allowClear: true,
			"onUpdate:modelValue": (value) => onChange(field, value || ""),
		});
	}

	function selectNode({ h, EdgeDropdown, filters, definition, onChange }) {
		const field = definition.field;
		return h(EdgeDropdown, {
			modelValue: filters[field] || "",
			label: __(definition.label),
			options: definition.options || [],
			"onUpdate:modelValue": (value) => onChange(field, value || ""),
		});
	}

	function extraNodes(context) {
		const definitions = DEFINITIONS[context.reportName] || [];
		return definitions.map((definition) =>
			definition.type === "link"
				? linkNode({ ...context, definition })
				: selectNode({ ...context, definition }),
		);
	}

	function hasSmartDefinition(reportName) {
		return Boolean(DEFINITIONS[reportName]);
	}

	global.VetEdgeReportFilterUI = Object.freeze({
		extraNodes,
		hasSmartDefinition,
		definitions: DEFINITIONS,
	});
})(window);
