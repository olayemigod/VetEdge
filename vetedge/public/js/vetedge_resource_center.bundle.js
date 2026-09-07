import VetEdgeAppointmentFlow from './vetedge_resource_center/VetEdgeAppointmentFlow.vue';
import VetEdgeResourceCenter from './vetedge_resource_center/VetEdgeResourceCenter.vue';
import VetEdgeResourceQuickEditor from './vetedge_resource_center/VetEdgeResourceQuickEditor.vue';

const RESOURCE_ROUTE_KEYS = Object.freeze([
	'resource',
	'search',
	'name',
	'new',
	'appointment_type',
	'branch',
	'status',
	'registration_status',
	'species',
	'patient',
	'owner',
	'practitioner',
	'consultation_type',
	'service_branch',
	'date_preset',
	'from_date',
	'to_date',
	'vaccine',
	'lab_test',
	'sort_by',
	'sort_order',
]);

const CLINICAL_RESOURCES = new Set(['lab-orders', 'vaccinations']);
const LEGACY_GROOMING_RESOURCE = 'grooming';
const DEFAULT_APPOINTMENT_SORT = Object.freeze({ by: 'appointment_datetime', order: 'asc' });
const DEFAULT_APPOINTMENT_DATE_PRESET = 'upcoming';
const APPOINTMENT_FUZZY_DATE_OPTIONS = Object.freeze([
	{ value: 'upcoming', label: __('Upcoming') },
	{ value: 'today', label: __('Today') },
	{ value: 'tomorrow', label: __('Tomorrow') },
	{ value: 'next_7_days', label: __('Next 7 Days') },
	{ value: 'this_week', label: __('This Week') },
	{ value: 'next_week', label: __('Next Week') },
	{ value: 'this_month', label: __('This Month') },
	{ value: 'next_30_days', label: __('Next 30 Days') },
	{ value: 'past', label: __('Past') },
	{ value: 'full_history', label: __('Full History') },
	{ value: 'custom', label: __('Custom Range') },
]);
const APPOINTMENT_FUZZY_DATE_VALUES = new Set(APPOINTMENT_FUZZY_DATE_OPTIONS.map((option) => option.value));

function getRequestedRouteParams() {
	const params = new URLSearchParams(window.location.search || '');
	const routeOptions = window.frappe?.route_options || {};
	const consumed = [];

	for (const key of RESOURCE_ROUTE_KEYS) {
		const value = routeOptions[key];
		if (value === undefined || value === null || String(value) === '') continue;
		if (!params.has(key)) params.set(key, String(value));
		consumed.push(key);
	}

	if (consumed.length && window.location.pathname === '/desk/vetedge-resource-center') {
		const query = params.toString();
		const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`;
		window.history.replaceState(window.history.state, '', nextUrl);
		for (const key of consumed) delete routeOptions[key];
	}

	return params;
}

function valueFrom(params, key, fallback = '') {
	return String(params.get(key) ?? fallback ?? '').trim();
}

function installEdgeFuzzyDate() {
	frappe.EdgeSuite = frappe.EdgeSuite || {};
	const existing = frappe.EdgeSuite.FuzzyDate;
	if (existing?.getOptions && existing?.getRange) return existing;

	const sharedDateRanges = frappe.EdgeSuite.DateRanges || null;
	const formatRange = (start, end) => ({
		start: start ? start.format('YYYY-MM-DD') : '',
		end: end ? end.format('YYYY-MM-DD') : '',
	});
	const fuzzyDate = {
		getDefaultPreset() {
			return DEFAULT_APPOINTMENT_DATE_PRESET;
		},
		getOptions() {
			return APPOINTMENT_FUZZY_DATE_OPTIONS.map((option) => ({ ...option }));
		},
		getRange(preset) {
			const selected = String(preset || '').trim();
			if (['upcoming', 'past', 'full_history'].includes(selected)) return { start: '', end: '' };
			if (selected === 'custom') return null;

			const today = moment();
			if (selected === 'tomorrow') {
				const target = today.clone().add(1, 'day');
				return formatRange(target, target);
			}
			if (selected === 'next_7_days') return formatRange(today, today.clone().add(6, 'days'));
			if (selected === 'next_week') {
				const start = today.clone().add(1, 'week').startOf('week');
				return formatRange(start, start.clone().endOf('week'));
			}
			if (selected === 'next_30_days') return formatRange(today, today.clone().add(29, 'days'));

			return sharedDateRanges?.getRange?.(selected) || null;
		},
	};
	frappe.EdgeSuite.FuzzyDate = fuzzyDate;
	return fuzzyDate;
}

const EDGE_FUZZY_DATE = installEdgeFuzzyDate();

function appointmentDateStateFromParams(params) {
	let preset = valueFrom(params, 'date_preset');
	let fromDate = valueFrom(params, 'from_date');
	let toDate = valueFrom(params, 'to_date');
	if (!preset) preset = fromDate || toDate ? 'custom' : DEFAULT_APPOINTMENT_DATE_PRESET;

	if (!APPOINTMENT_FUZZY_DATE_VALUES.has(preset)) {
		const legacyRange = EDGE_FUZZY_DATE.getRange(preset);
		if (!fromDate && !toDate && legacyRange) {
			fromDate = legacyRange.start || '';
			toDate = legacyRange.end || '';
		}
		preset = 'custom';
	}

	if (preset !== 'custom') {
		const range = EDGE_FUZZY_DATE.getRange(preset);
		if (range) {
			fromDate = range.start || '';
			toDate = range.end || '';
		}
	}
	return { preset, fromDate, toDate };
}

function vaccinationAwareAppointmentFlow() {
	const originalMethods = VetEdgeAppointmentFlow.methods || {};
	const originalSearchPractitioner = originalMethods.searchPractitioner;
	const originalSubmitAppointment = originalMethods.submitAppointment;
	return {
		...VetEdgeAppointmentFlow,
		methods: {
			...originalMethods,
			searchPractitioner(query) {
				if (!this.isVaccination) return originalSearchPractitioner?.call(this, query) || [];
				return frappe.call('vetedge.services.appointment_vaccination_bridge.search_vaccination_practitioners', {
					txt: query,
					branch: this.form.branch,
					start: 0,
					page_length: 20,
				}).then((response) => response.message || []);
			},
			async submitAppointment() {
				if (!this.isVaccination) return originalSubmitAppointment?.call(this);
				this.error = '';
				if (!this.bootstrap.can_create_appointment) {
					this.error = __('You do not have permission to create Veterinary Appointments.');
					return;
				}
				if (!this.form.patient || !this.form.branch || !this.form.appointment_datetime) {
					this.error = __('Patient, Service Branch and Appointment Date/Time are required.');
					return;
				}
				if (!this.form.vaccine) {
					this.error = __('Planned Vaccine is required for Vaccination appointments.');
					return;
				}
				if (!this.form.practitioner) {
					this.error = __('Veterinary Practitioner is required for this appointment type.');
					return;
				}
				this.saving = true;
				try {
					const response = await frappe.call('vetedge.services.appointment_vaccination_bridge.create_edgeui_vaccination_appointment', {
						values: this.appointmentPayload(),
					});
					const created = response.message || {};
					frappe.show_alert({ message: __('Veterinary Appointment created'), indicator: 'green' });
					this.$emit('created', created);
					this.openState = false;
				} catch (error) {
					this.error = error?.message || __('The Veterinary Appointment could not be created.');
				} finally {
					this.saving = false;
				}
			},
		},
	};
}

export function mountVetEdgeResourceCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	if (!runtime.components?.EdgeLinkField || !runtime.components?.EdgeModal || !runtime.components?.EdgeDropdown) {
		throw new Error('VetEdge Resource Center requires the EdgeSuite UI 0.6.2 form runtime.');
	}

	const requestedRoute = getRequestedRouteParams();
	const requestedName = valueFrom(requestedRoute, 'name');
	const requestedNew = requestedRoute.get('new') === '1';
	const requestedAppointmentType = valueFrom(requestedRoute, 'appointment_type');

	const flowHost = document.createElement('div');
	flowHost.className = 'vetedge-appointment-flow-host';
	document.body.appendChild(flowHost);

	const quickEditorHost = document.createElement('div');
	quickEditorHost.className = 'vetedge-resource-quick-editor-host';
	document.body.appendChild(quickEditorHost);

	let resourceView = null;
	let lastRefreshAt = Date.now();

	const flowApp = runtime.createEdgeApp(vaccinationAwareAppointmentFlow(), {
		onCreated: async () => {
			await resourceView?.loadPage?.();
			lastRefreshAt = Date.now();
		},
	});
	const flowView = flowApp.mount(flowHost);

	const quickEditorApp = runtime.createEdgeApp(VetEdgeResourceQuickEditor, {
		onSaved: async () => {
			await resourceView?.loadPage?.();
			lastRefreshAt = Date.now();
		},
	});
	const quickEditorView = quickEditorApp.mount(quickEditorHost);
	const originalData = VetEdgeResourceCenter.data;
	const originalMethods = VetEdgeResourceCenter.methods || {};
	const originalLoadPage = originalMethods.loadPage;
	const originalChangeResource = originalMethods.changeResource;
	const originalResetSearch = originalMethods.resetSearch;

	const ResourceCenterRoot = {
		...VetEdgeResourceCenter,
		components: { ...runtime.components, ...(VetEdgeResourceCenter.components || {}) },
		data() {
			const state = typeof originalData === 'function' ? originalData.call(this) : {};
			state.resourceOptions = (state.resourceOptions || []).filter((option) => option.value !== LEGACY_GROOMING_RESOURCE);
			if (state.resource === LEGACY_GROOMING_RESOURCE) state.resource = 'appointments';
			if (state.resource === 'appointments' && state.appointmentFilters) {
				const dateState = appointmentDateStateFromParams(getRequestedRouteParams());
				state.appointmentFilters.date_preset = dateState.preset;
				state.appointmentFilters.from_date = dateState.fromDate;
				state.appointmentFilters.to_date = dateState.toDate;
			}
			return state;
		},
		computed: {
			...(VetEdgeResourceCenter.computed || {}),
			primaryActionLabel() {
				if (!this.page?.can_create) return '';
				if (this.resource === 'appointments') return 'New Appointment';
				if (this.resource === 'lab-orders') return 'New Lab Order';
				if (this.resource === 'vaccinations') return 'New Vaccination';
				return 'Add Record';
			},
			appointmentDatePresetOptions() {
				return EDGE_FUZZY_DATE.getOptions();
			},
		},
		methods: {
			...originalMethods,
			async loadPage() {
				if (this.resource !== 'appointments') return originalLoadPage?.call(this);
				this.loading = true;
				this.error = '';
				try {
					const response = await frappe.call('vetedge.services.appointment_resource_center.get_appointment_page', {
						search: this.search,
						start: this.start,
						page_length: this.pageLength,
						branch: this.appointmentFilters.branch,
						patient: this.appointmentFilters.patient,
						owner: this.appointmentFilters.owner,
						practitioner: this.appointmentFilters.practitioner,
						status: this.appointmentFilters.status,
						appointment_type: this.appointmentFilters.appointment_type,
						consultation_type: this.appointmentFilters.consultation_type,
						date_preset: this.appointmentFilters.date_preset || DEFAULT_APPOINTMENT_DATE_PRESET,
						from_date: this.appointmentFilters.from_date,
						to_date: this.appointmentFilters.to_date,
						sort_by: this.appointmentSort.by,
						sort_order: this.appointmentSort.order,
					});
					this.page = response.message || this.page;
					if (this.page.context_branch && !this.appointmentFilters.branch) {
						this.appointmentFilters.branch = this.page.context_branch;
						this.appointmentFilterLabels.branch = this.page.context_branch;
					}
					this.appointmentFilters.date_preset = this.page.date_preset || this.appointmentFilters.date_preset || DEFAULT_APPOINTMENT_DATE_PRESET;
					this.appointmentSort.by = this.page.sort_by || this.appointmentSort.by || DEFAULT_APPOINTMENT_SORT.by;
					this.appointmentSort.order = this.page.sort_order || this.appointmentSort.order || DEFAULT_APPOINTMENT_SORT.order;
					this.updateLocation();
				} catch (error) {
					this.error = error?.message || __('The Veterinary resource could not be loaded.');
				} finally {
					this.loading = false;
				}
			},
			onAppointmentDatePresetChange() {
				const preset = this.appointmentFilters.date_preset || DEFAULT_APPOINTMENT_DATE_PRESET;
				if (preset === 'custom') return;
				const range = EDGE_FUZZY_DATE.getRange(preset);
				if (!range) return;
				this.appointmentFilters.from_date = range.start || '';
				this.appointmentFilters.to_date = range.end || '';
				this.start = 0;
				this.loadPage();
			},
			onAppointmentManualDateChange() {
				this.appointmentFilters.date_preset = 'custom';
			},
			changeResource() {
				if (this.resource !== 'appointments') return originalChangeResource?.call(this);
				this.start = 0;
				this.search = '';
				this.appointmentFilters = {
					branch: '',
					patient: '',
					owner: '',
					practitioner: '',
					status: '',
					appointment_type: '',
					consultation_type: '',
					date_preset: DEFAULT_APPOINTMENT_DATE_PRESET,
					from_date: '',
					to_date: '',
				};
				this.appointmentFilterLabels = { branch: '', patient: '', owner: '', practitioner: '', consultation_type: '' };
				this.appointmentSort = { ...DEFAULT_APPOINTMENT_SORT };
				this.loadPage();
			},
			resetSearch() {
				if (this.resource !== 'appointments') return originalResetSearch?.call(this);
				this.search = '';
				this.appointmentFilters = {
					branch: '',
					patient: '',
					owner: '',
					practitioner: '',
					status: '',
					appointment_type: '',
					consultation_type: '',
					date_preset: DEFAULT_APPOINTMENT_DATE_PRESET,
					from_date: '',
					to_date: '',
				};
				this.appointmentFilterLabels = { branch: '', patient: '', owner: '', practitioner: '', consultation_type: '' };
				this.appointmentSort = { ...DEFAULT_APPOINTMENT_SORT };
				this.start = 0;
				this.loadPage();
			},
			openEditor(name = null) {
				if (this.resource === 'appointments' && !name) {
					flowView?.open?.();
					return;
				}
				quickEditorView?.open?.({ resource: this.resource, name });
			},
			async openClinicalCreate() {
				try {
					const editor = await this.ensureClinicalEditor();
					const defaults = Object.fromEntries(Object.entries({
						patient: this.clinicalFilters?.patient || '',
						service_branch: this.clinicalFilters?.service_branch || '',
						vaccine: this.resource === 'vaccinations' ? (this.clinicalFilters?.vaccine || '') : '',
					}).filter(([, value]) => Boolean(value)));
					await editor.create(this.clinicalDoctype, () => this.loadPage(), defaults);
				} catch (error) {
					frappe.msgprint(error?.message || __('The clinical record creator is unavailable.'));
				}
			},
		},
	};

	const app = runtime.createEdgeApp(ResourceCenterRoot);
	resourceView = app.mount(target);

	const isAppointments = () => resourceView?.resource === 'appointments';
	const isClinicalResource = () => CLINICAL_RESOURCES.has(resourceView?.resource);

	const getRequestedState = () => {
		const params = getRequestedRouteParams();
		const requestedResource = valueFrom(params, 'resource', 'patients') || 'patients';
		const requestedSortOrder = valueFrom(params, 'sort_order', DEFAULT_APPOINTMENT_SORT.order).toLowerCase();
		const dateState = appointmentDateStateFromParams(params);
		return {
			resource: requestedResource === LEGACY_GROOMING_RESOURCE ? 'appointments' : requestedResource,
			search: valueFrom(params, 'search'),
			name: valueFrom(params, 'name'),
			isNew: params.get('new') === '1',
			appointmentType: valueFrom(params, 'appointment_type'),
			branch: valueFrom(params, 'branch'),
			status: valueFrom(params, 'status'),
			registrationStatus: valueFrom(params, 'registration_status'),
			species: valueFrom(params, 'species'),
			patient: valueFrom(params, 'patient'),
			owner: valueFrom(params, 'owner'),
			practitioner: valueFrom(params, 'practitioner'),
			consultationType: valueFrom(params, 'consultation_type'),
			serviceBranch: valueFrom(params, 'service_branch') || valueFrom(params, 'branch'),
			datePreset: dateState.preset,
			fromDate: dateState.fromDate,
			toDate: dateState.toDate,
			vaccine: valueFrom(params, 'vaccine'),
			labTest: valueFrom(params, 'lab_test'),
			sortBy: valueFrom(params, 'sort_by', DEFAULT_APPOINTMENT_SORT.by),
			sortOrder: ['asc', 'desc'].includes(requestedSortOrder) ? requestedSortOrder : DEFAULT_APPOINTMENT_SORT.order,
		};
	};

	const setField = (targetState, fieldname, value) => {
		if (!targetState || String(targetState[fieldname] || '') === String(value || '')) return false;
		targetState[fieldname] = value || '';
		return true;
	};

	const setLinkField = (values, labels, fieldname, value) => {
		const changed = setField(values, fieldname, value);
		if (labels && (changed || String(labels[fieldname] || '') !== String(value || ''))) {
			labels[fieldname] = value || '';
		}
		return changed;
	};

	const applyRequestedState = () => {
		if (!resourceView) return { routeChanged: false, state: getRequestedState() };
		const state = getRequestedState();
		let routeChanged = false;
		const allowedResources = resourceView.resourceOptions || [];
		const resourceIsValid = allowedResources.some((option) => option.value === state.resource);
		if (resourceIsValid && resourceView.resource !== state.resource) {
			resourceView.resource = state.resource;
			resourceView.start = 0;
			routeChanged = true;
		}
		if (resourceView.search !== state.search) {
			resourceView.search = state.search;
			resourceView.start = 0;
			routeChanged = true;
		}

		if (state.resource === 'patients') {
			routeChanged = setLinkField(resourceView.patientFilters, resourceView.patientFilterLabels, 'default_branch', state.branch) || routeChanged;
			routeChanged = setField(resourceView.patientFilters, 'status', state.status) || routeChanged;
			routeChanged = setField(resourceView.patientFilters, 'registration_status', state.registrationStatus) || routeChanged;
			routeChanged = setLinkField(resourceView.patientFilters, resourceView.patientFilterLabels, 'species', state.species) || routeChanged;
		} else if (state.resource === 'appointments') {
			routeChanged = setLinkField(resourceView.appointmentFilters, resourceView.appointmentFilterLabels, 'branch', state.branch) || routeChanged;
			routeChanged = setLinkField(resourceView.appointmentFilters, resourceView.appointmentFilterLabels, 'patient', state.patient) || routeChanged;
			routeChanged = setLinkField(resourceView.appointmentFilters, resourceView.appointmentFilterLabels, 'owner', state.owner) || routeChanged;
			routeChanged = setLinkField(resourceView.appointmentFilters, resourceView.appointmentFilterLabels, 'practitioner', state.practitioner) || routeChanged;
			routeChanged = setField(resourceView.appointmentFilters, 'status', state.status) || routeChanged;
			routeChanged = setField(resourceView.appointmentFilters, 'appointment_type', state.appointmentType) || routeChanged;
			routeChanged = setLinkField(resourceView.appointmentFilters, resourceView.appointmentFilterLabels, 'consultation_type', state.consultationType) || routeChanged;
			routeChanged = setField(resourceView.appointmentFilters, 'date_preset', state.datePreset) || routeChanged;
			routeChanged = setField(resourceView.appointmentFilters, 'from_date', state.fromDate) || routeChanged;
			routeChanged = setField(resourceView.appointmentFilters, 'to_date', state.toDate) || routeChanged;
			routeChanged = setField(resourceView.appointmentSort, 'by', state.sortBy) || routeChanged;
			routeChanged = setField(resourceView.appointmentSort, 'order', state.sortOrder) || routeChanged;
		} else if (CLINICAL_RESOURCES.has(state.resource)) {
			routeChanged = setLinkField(resourceView.clinicalFilters, resourceView.clinicalFilterLabels, 'patient', state.patient) || routeChanged;
			routeChanged = setLinkField(resourceView.clinicalFilters, resourceView.clinicalFilterLabels, 'service_branch', state.serviceBranch) || routeChanged;
			routeChanged = setField(resourceView.clinicalFilters, 'status', state.status) || routeChanged;
			routeChanged = setField(resourceView.clinicalFilters, 'from_date', state.fromDate) || routeChanged;
			routeChanged = setField(resourceView.clinicalFilters, 'to_date', state.toDate) || routeChanged;
			routeChanged = setLinkField(resourceView.clinicalFilters, resourceView.clinicalFilterLabels, 'vaccine', state.vaccine) || routeChanged;
			routeChanged = setLinkField(resourceView.clinicalFilters, resourceView.clinicalFilterLabels, 'lab_test', state.labTest) || routeChanged;
		}

		if (routeChanged) resourceView.start = 0;
		return { routeChanged, state };
	};

	const openRequestedEditor = (state) => {
		if (!state?.name && !state?.isNew) return;
		if (state.isNew && isAppointments()) {
			flowView?.open?.({ appointment_type: state.appointmentType || '' });
			return;
		}
		if (isClinicalResource()) {
			if (state.isNew) {
				resourceView.openClinicalCreate?.();
				return;
			}
			if (state.name) {
				resourceView.openClinicalRecord?.({ name: state.name });
				return;
			}
		}
		quickEditorView?.open?.({
			resource: resourceView.resource,
			name: state.name || null,
		});
	};

	// `interceptAppointmentAction` is intentionally retired: the Vue component's
	// primaryActionLabel/runPrimaryAction path now owns New Appointment directly.

	// Route alignment captures `name` / `new` before the Resource Center normalizes
	// its list URL so bookmarks, sidebar links and notification deep links can open
	// the canonical EdgeSuite editor rather than falling back to a native Frappe form.
	if (requestedName || requestedNew) {
		window.setTimeout(() => {
			if (!resourceView) return;
			openRequestedEditor({
				name: requestedName,
				isNew: requestedNew,
				appointmentType: requestedAppointmentType,
			});
		}, 0);
	}

	return {
		async refresh(options = {}) {
			if (!resourceView) return false;
			const maxAgeMs = Math.max(Number(options.maxAgeMs || 0), 0);
			const force = options.force === true;
			const { routeChanged, state } = applyRequestedState();
			const hasDeepLink = Boolean(state.name || state.isNew);
			const isFresh = maxAgeMs > 0 && Date.now() - lastRefreshAt < maxAgeMs;

			if (!force && !routeChanged && !hasDeepLink && isFresh) {
				return false;
			}

			await resourceView.loadPage?.();
			lastRefreshAt = Date.now();
			if (hasDeepLink) {
				window.setTimeout(() => openRequestedEditor(state), 0);
			}
			return true;
		},
		unmount() {
			app.unmount();
			flowApp.unmount();
			quickEditorApp.unmount();
			flowHost.remove();
			quickEditorHost.remove();
		},
	};
}

if (typeof window !== 'undefined') {
	window.VetEdgeResourceCenter = VetEdgeResourceCenter;
	window.VetEdgeAppointmentFlow = VetEdgeAppointmentFlow;
	window.VetEdgeResourceQuickEditor = VetEdgeResourceQuickEditor;
	window.mountVetEdgeResourceCenter = mountVetEdgeResourceCenter;
}
