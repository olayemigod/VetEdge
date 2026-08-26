(function installVetEdgeReportFilterUI(global) {
	"use strict";

	const optionList = (values, allLabel) => [
		{ value: "", label: allLabel },
		...values.map((value) => ({ value, label: value })),
	];
	const booleanOptions = [
		{ value: "", label: "All" },
		{ value: "1", label: "Yes" },
		{ value: "0", label: "No" },
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
	const revenueCategories = optionList(
		["Consultation", "Lab", "Vaccination", "Boarding", "Grooming", "Dispensary", "Registration", "General"],
		"All Service Categories",
	);
	const revenueStatuses = optionList(["Draft", "Paid", "Unpaid", "Overdue", "Cancelled"], "All Invoice States");
	const ageRanges = optionList(["0-30", "31-60", "61-90", "90+"], "All Age Ranges");
	const boardingStatuses = optionList(["Draft", "Reserved", "Checked In", "Checked Out", "Cancelled"], "All Boarding States");
	const kennelStatuses = optionList(["Available", "Reserved", "Occupied", "Full", "Out of Service / Inactive"], "All Kennel States");
	const groomingStatuses = optionList(["Draft", "Awaiting Payment", "Pending Grooming", "In Progress", "Completed", "Cancelled"], "All Grooming States");
	const careLevels = optionList(["Standard", "Observation", "Intensive Care", "ICU", "Isolation", "Recovery"], "All Care Levels");
	const hospitalStatuses = optionList(["Draft", "Admitted", "Under Care", "Ready for Discharge", "Discharged", "Cancelled"], "All Hospitalisation States");
	const activeHospitalStatuses = optionList(["Admitted", "Under Care", "Ready for Discharge", "Discharged", "Cancelled"], "All Hospitalisation States");
	const activeCareStatuses = optionList(["Admitted", "Under Care", "Ready for Discharge"], "All Active States");
	const invoiceStatuses = optionList(["Not Invoiced", "Draft", "Unpaid", "Partly Paid", "Paid", "Overdue", "Cancelled"], "All Invoice States");
	const careLocationTypes = optionList(["Ward", "Kennel", "Cage", "ICU", "Isolation", "Recovery", "General"], "All Location Types");
	const careLocationStatuses = optionList(["Available", "Occupied", "Cleaning", "Maintenance", "Inactive"], "All Location States");
	const dischargeIssueTypes = optionList(["Missing Price Charges", "Pending Charge Sync", "Pending Stock Posting", "Care Location Still Assigned", "Pending Discharge Summary"], "All Pending Issues");
	const hospitalActionTypes = optionList(["Missing Price Charges", "Pending Charge Sync", "Pending Stock Posting", "Care Location Still Assigned", "No Recent Activity", "Pending Discharge Summary", "Pending Daily Charges"], "All Action Types");

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
		"Practitioner Performance Report": [
			{ field: "practitioner", type: "link", label: "Practitioner" },
		],
		"Branch Performance Report": [],
		"Revenue Summary": [
			{ field: "cost_center", type: "link", label: "Cost Center" },
			{ field: "customer", type: "link", label: "Customer" },
			{ field: "service_category", type: "select", label: "Service Category", options: revenueCategories },
			{ field: "status", type: "select", label: "Invoice Status", options: revenueStatuses },
		],
		"Unpaid Invoice Report": [
			{ field: "customer", type: "link", label: "Customer" },
			{ field: "age_range", type: "select", label: "Age Range", options: ageRanges },
		],
		"Boarding Report": [
			{ field: "kennel", type: "link", label: "Kennel" },
			{ field: "status", type: "select", label: "Status", options: boardingStatuses },
			{ field: "patient", type: "link", label: "Patient" },
			{ field: "owner", type: "link", label: "Owner" },
		],
		"Kennel Availability Report": [
			{ field: "kennel", type: "link", label: "Kennel" },
			{ field: "status", type: "select", label: "Status", options: kennelStatuses },
		],
		"Grooming Report": [
			{ field: "assigned_staff", type: "link", label: "Assigned Staff" },
			{ field: "status", type: "select", label: "Status", options: groomingStatuses },
			{ field: "patient", type: "link", label: "Patient" },
			{ field: "owner", type: "link", label: "Owner" },
		],
		"Active Hospitalisations": [
			{ field: "care_level", type: "select", label: "Care Level", options: careLevels },
			{ field: "care_location", type: "link", label: "Care Location" },
			{ field: "attending_veterinarian", type: "link", label: "Attending Veterinarian" },
			{ field: "status", type: "select", label: "Status", options: activeHospitalStatuses },
			{ field: "admission_date_from", type: "input", inputType: "date", label: "Admission Date From" },
			{ field: "admission_date_to", type: "input", inputType: "date", label: "Admission Date To" },
			{ field: "owner", type: "link", label: "Pet Owner" },
			{ field: "patient", type: "link", label: "Patient" },
		],
		"Hospitalisation Charge Summary": [
			{ field: "care_level", type: "select", label: "Care Level", options: careLevels },
			{ field: "status", type: "select", label: "Status", options: hospitalStatuses },
			{ field: "patient", type: "link", label: "Patient" },
			{ field: "owner", type: "link", label: "Pet Owner" },
			{ field: "invoice_status", type: "select", label: "Invoice Status", options: invoiceStatuses },
			{ field: "missing_price_only", type: "select", label: "Missing Price Only", options: booleanOptions },
			{ field: "pending_only", type: "select", label: "Pending Only", options: booleanOptions },
		],
		"Care Location Occupancy": [
			{ field: "location_type", type: "select", label: "Location Type", options: careLocationTypes },
			{ field: "status", type: "select", label: "Status", options: careLocationStatuses },
			{ field: "include_inactive", type: "select", label: "Include Inactive", options: booleanOptions },
			{ field: "occupied_only", type: "select", label: "Occupied Only", options: booleanOptions },
		],
		"Hospitalisation Discharge Watch": [
			{ field: "care_level", type: "select", label: "Care Level", options: careLevels },
			{ field: "attending_veterinarian", type: "link", label: "Attending Veterinarian" },
			{ field: "minimum_days_admitted", type: "input", inputType: "number", min: 0, label: "Minimum Days Admitted" },
			{ field: "status", type: "select", label: "Status", options: activeCareStatuses },
			{ field: "discharge_ready_only", type: "select", label: "Discharge Ready Only", options: booleanOptions },
			{ field: "pending_issue_type", type: "select", label: "Pending Issue Type", options: dischargeIssueTypes },
		],
		"Pending Hospitalisation Actions": [
			{ field: "action_type", type: "select", label: "Action Type", options: hospitalActionTypes },
			{ field: "status", type: "select", label: "Status", options: activeCareStatuses },
			{ field: "attending_veterinarian", type: "link", label: "Assigned To / Attending Veterinarian" },
		],
		"Dispensary Activity Report": [
			{ field: "item", type: "link", label: "Item" },
			{ field: "warehouse", type: "link", label: "Warehouse" },
		],
		"Stock Usage Summary": [
			{ field: "item", type: "link", label: "Item" },
			{ field: "warehouse", type: "link", label: "Warehouse" },
		],
		"Stock Expiry Status": [
			{ field: "company", type: "link", label: "Company" },
			{ field: "warehouse", type: "link", label: "Warehouse" },
			{ field: "item_group", type: "link", label: "Item Group" },
			{ field: "expiry_buckets", type: "input", inputType: "text", label: "Expiry Buckets", placeholder: "30,60,90" },
			{ field: "include_zero_qty", type: "select", label: "Include Zero Qty", options: booleanOptions },
		],
		"Service Revenue Breakdown": [
			{ field: "service_category", type: "select", label: "Service Category", options: serviceCategories },
			{ field: "practitioner", type: "link", label: "Practitioner" },
			{ field: "item", type: "link", label: "Item" },
		],
	});

	const EXTRA_FILTER_KEYS = [...new Set(Object.values(DEFINITIONS).flatMap((definitions) => definitions.map((definition) => definition.field).filter(Boolean)))];
	// The Report Center declares its base filter-key array before this asset is lazy-loaded.
	// Mutating that array here keeps URL sharing and saved-view apply/save parity for every
	// migrated report without duplicating a second report-state store.
	try {
		if (typeof REPORT_FILTER_KEYS !== "undefined" && Array.isArray(REPORT_FILTER_KEYS)) {
			for (const key of EXTRA_FILTER_KEYS) if (!REPORT_FILTER_KEYS.includes(key)) REPORT_FILTER_KEYS.push(key);
		}
	} catch (_error) {
		// The filter UI remains usable in isolated tests or pages without Report Center state.
	}

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
			modelValue: filters[field] ?? "",
			label: __(definition.label),
			options: definition.options || [],
			"onUpdate:modelValue": (value) => onChange(field, value ?? ""),
		});
	}

	function inputNode({ h, EdgeInput, filters, definition, onChange }) {
		const field = definition.field;
		const Input = EdgeInput || global.EdgeSuiteUI?.components?.EdgeInput || global.EdgeUI?.components?.EdgeInput;
		if (!Input) return null;
		return h(Input, {
			modelValue: filters[field] ?? "",
			label: __(definition.label),
			type: definition.inputType || "text",
			min: definition.min,
			placeholder: definition.placeholder ? __(definition.placeholder) : "",
			"onUpdate:modelValue": (value) => onChange(field, value ?? ""),
		});
	}

	function extraNodes(context) {
		const definitions = DEFINITIONS[context.reportName] || [];
		return definitions.map((definition) => {
			if (definition.type === "link") return linkNode({ ...context, definition });
			if (definition.type === "input") return inputNode({ ...context, definition });
			return selectNode({ ...context, definition });
		}).filter(Boolean);
	}

	function filterKeys(reportName) {
		return [...new Set((DEFINITIONS[reportName] || []).map((definition) => definition.field).filter(Boolean))];
	}

	function hasSmartDefinition(reportName) {
		return Boolean(DEFINITIONS[reportName]);
	}

	global.VetEdgeReportFilterUI = Object.freeze({
		extraNodes,
		filterKeys,
		extraFilterKeys: EXTRA_FILTER_KEYS,
		hasSmartDefinition,
		definitions: DEFINITIONS,
	});
})(window);