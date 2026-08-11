import VeterinaryMedicalHistory from './veterinary_medical_history/VeterinaryMedicalHistory.vue';

const SUMMARY_API = 'vetedge.services.medical_history_lazy.get_patient_medical_history_summary';
const SECTION_API = 'vetedge.services.medical_history_lazy.get_patient_medical_history_section';
const TREND_API = 'vetedge.services.medical_history.get_patient_vitals_trend';
const HISTORY_SECTIONS = ['consultations', 'vitals', 'diagnoses', 'symptoms', 'treatments', 'vaccinations', 'labs'];
const HISTORY_SECTION_LIMIT = 50;
const TREND_LIMIT = 100;

function lazyLoadError(message) {
	if (window.frappe?.show_alert) {
		window.frappe.show_alert({ message, indicator: 'red' }, 5);
	}
}

function requestedPatient() {
	const routePatient = window.frappe?.route_options?.patient;
	if (routePatient) return String(routePatient).trim();
	const params = new URLSearchParams(window.location.search || '');
	return String(params.get('patient') || '').trim();
}

function installLazyMedicalHistory() {
	if (VeterinaryMedicalHistory.__vetedgeLazyMedicalHistoryInstalled) return;

	const legacyData = VeterinaryMedicalHistory.data;
	const legacyMethods = VeterinaryMedicalHistory.methods || {};
	const legacyWatch = VeterinaryMedicalHistory.watch || {};

	VeterinaryMedicalHistory.data = function lazyMedicalHistoryData() {
		return {
			...(legacyData?.call(this) || {}),
			loadedHistorySections: {},
			loadedTrends: {},
			lazyRequestGeneration: 0,
			lastLazyLoadAt: 0,
		};
	};

	VeterinaryMedicalHistory.methods = {
		...legacyMethods,
		async load() {
			if (!this.filters.patient || this.loading) return;

			const generation = ++this.lazyRequestGeneration;
			this.loading = true;
			this.error = '';
			this.clearChart?.();
			this.data = { summary: {}, trends: {} };
			this.loadedHistorySections = {};
			this.loadedTrends = {};

			try {
				const response = await frappe.call(SUMMARY_API, {
					patient: this.filters.patient,
					from_date: this.filters.from_date || undefined,
					to_date: this.filters.to_date || undefined,
				});
				if (generation !== this.lazyRequestGeneration) return;

				const message = response.message || {};
				this.data = { ...message, trends: {} };
				const readableLabel = message?.summary?.patient_name || this.patientLabels[this.filters.patient] || this.filters.patient;
				this.patientLabel = readableLabel;
				this.patientLabels = { ...this.patientLabels, [this.filters.patient]: readableLabel };

				const url = new URL(window.location.href);
				url.pathname = '/app/veterinary-medical-history';
				url.search = new URLSearchParams({ patient: this.filters.patient }).toString();
				window.history.replaceState({}, '', url);

				await Promise.all([
					this.ensureHistorySection(this.activeHistory, { force: true, generation, throwOnError: true }),
					this.ensureTrend(this.activeTrend, { force: true, generation, throwOnError: true }),
				]);
				if (generation !== this.lazyRequestGeneration) return;

				this.lastLazyLoadAt = Date.now();
				await this.$nextTick();
				this.syncHistoryTabCounts();
				this.renderTrendChart();
			} catch (error) {
				if (generation !== this.lazyRequestGeneration) return;
				this.data = {};
				this.error = error?.message || error?._server_messages || __('Medical history could not be loaded.');
			} finally {
				if (generation === this.lazyRequestGeneration) {
					this.loading = false;
					await this.$nextTick();
					this.syncHistoryTabCounts();
				}
			}
		},
		async ensureHistorySection(section, options = {}) {
			if (!this.filters.patient || !HISTORY_SECTIONS.includes(section)) return false;
			if (!options.force && this.loadedHistorySections?.[section]) return false;

			const generation = options.generation ?? this.lazyRequestGeneration;
			try {
				const response = await frappe.call(SECTION_API, {
					patient: this.filters.patient,
					section,
					from_date: this.filters.from_date || undefined,
					to_date: this.filters.to_date || undefined,
					limit: HISTORY_SECTION_LIMIT,
				});
				if (generation !== this.lazyRequestGeneration) return false;

				const message = response.message || {};
				this.data = { ...this.data, [section]: message.rows || [] };
				this.loadedHistorySections = { ...this.loadedHistorySections, [section]: true };
				await this.$nextTick();
				this.syncHistoryTabCounts();
				return true;
			} catch (error) {
				if (options.throwOnError) throw error;
				lazyLoadError(error?.message || __('Medical history section could not be loaded.'));
				return false;
			}
		},
		async ensureTrend(fieldname, options = {}) {
			if (!this.filters.patient || !fieldname) return false;
			if (!options.force && this.loadedTrends?.[fieldname]) return false;

			const generation = options.generation ?? this.lazyRequestGeneration;
			try {
				const response = await frappe.call(TREND_API, {
					patient: this.filters.patient,
					fieldname,
					from_date: this.filters.from_date || undefined,
					to_date: this.filters.to_date || undefined,
					limit: TREND_LIMIT,
				});
				if (generation !== this.lazyRequestGeneration) return false;

				this.data = {
					...this.data,
					trends: { ...(this.data?.trends || {}), [fieldname]: response.message || [] },
				};
				this.loadedTrends = { ...this.loadedTrends, [fieldname]: true };
				return true;
			} catch (error) {
				if (options.throwOnError) throw error;
				lazyLoadError(error?.message || __('Vitals trend could not be loaded.'));
				return false;
			}
		},
		syncHistoryTabCounts() {
			const tabs = document.querySelectorAll('.history-tabs--records .history-tab');
			tabs.forEach((tab, index) => {
				const section = HISTORY_SECTIONS[index];
				const counter = tab.querySelector('small');
				if (!section || !counter) return;
				counter.textContent = this.loadedHistorySections?.[section]
					? String((this.data?.[section] || []).length)
					: '—';
			});
		},
	};

	VeterinaryMedicalHistory.watch = {
		...legacyWatch,
		async activeTrend(value) {
			await this.$nextTick();
			try {
				await this.ensureTrend(value);
				await this.$nextTick();
				this.renderTrendChart();
			} catch (_error) {
				// ensureTrend reports user-visible failures for lazy tab loads.
			}
		},
		async activeHistory(value) {
			await this.$nextTick();
			this.syncHistoryTabCounts();
			try {
				await this.ensureHistorySection(value);
			} finally {
				await this.$nextTick();
				this.syncHistoryTabCounts();
			}
		},
	};

	VeterinaryMedicalHistory.__vetedgeLazyMedicalHistoryInstalled = true;
}

export function mountVeterinaryMedicalHistory(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	installLazyMedicalHistory();
	VeterinaryMedicalHistory.components = runtime.components;
	const app = runtime.createEdgeApp(VeterinaryMedicalHistory);
	const view = app.mount(target);
	return {
		view,
		async refresh(options = {}) {
			if (!view) return false;
			const maxAgeMs = Math.max(Number(options.maxAgeMs || 0), 0);
			const force = options.force === true;
			const routePatient = requestedPatient();
			const patientChanged = Boolean(routePatient && routePatient !== view.filters?.patient);
			const isFresh = maxAgeMs > 0 && Date.now() - Number(view.lastLazyLoadAt || 0) < maxAgeMs;

			if (patientChanged) {
				view.filters.patient = routePatient;
				view.patientLabel = '';
				if (window.frappe?.route_options) window.frappe.route_options = null;
				await view.resolvePatientLabel?.(routePatient);
				await view.load?.();
				return true;
			}

			if (!view.filters?.patient || (!force && isFresh)) return false;
			await view.load?.();
			return true;
		},
		unmount: () => app.unmount(),
	};
}

if (typeof window !== 'undefined') {
	installLazyMedicalHistory();
	window.VeterinaryMedicalHistory = VeterinaryMedicalHistory;
	window.mountVeterinaryMedicalHistory = mountVeterinaryMedicalHistory;
}

export { installLazyMedicalHistory };
export default VeterinaryMedicalHistory;
