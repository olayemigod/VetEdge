<template>
  <div v-if="!edgeUIValid" class="p-6 text-center hospitalisation-runtime-error">
    <strong>EdgeSuite Hospitalisation Operations failed to load</strong>
    <div v-if="missingComponents.length" class="hospitalisation-runtime-error__detail">
      Missing components: {{ missingComponents.join(', ') }}
    </div>
    <button class="edge-button edge-button--primary" type="button" @click="retryRuntime">Retry</button>
  </div>

  <EdgeAppShell
    v-else
    product="vetedge"
    activeRoute="/app/vetedge-hospitalisation-operations"
    title="Veterinary"
    :tenantName="tenantName"
    :branchName="branchName"
    :userName="userName"
    data-edge-product="vetedge"
  >
    <EdgeReportShell
      title="Hospitalisation Operations"
      eyebrow="Hospital & Services"
      subtitle="Monitor active admissions, care activity, stock actions, charges and discharge readiness signals."
      :columns="displayColumns"
      :rows="rows"
      :summary="summary"
      :pagination="pagination"
      :loading="loading"
      :error="error"
      :rowKey="rowKey"
      :formatter="formatCell"
      :exportEnabled="false"
      :printEnabled="false"
      emptyTitle="No active hospitalisations"
      emptyDescription="No admitted, under-care or ready-for-discharge records match the current filters."
      loadingMessage="Loading Hospitalisation Operations…"
      @retry="refreshOperationalView"
      @page-change="goToPage"
      @page-size-change="setPageSize"
      @cell-click="openCell"
    >
      <template #filters>
        <div class="hospitalisation-filter-grid">
          <EdgeLinkField
            v-model="filters.branch"
            label="Branch"
            placeholder="All visible Branches"
            :searcher="searchBranch"
            :disabled="loading"
            @select="onBranchChanged"
            @clear="onBranchChanged"
          />
          <EdgeLinkField
            v-model="filters.patient"
            label="Patient"
            placeholder="All Patients"
            :searcher="searchPatient"
            :disabled="loading"
            @select="onPatientChanged"
            @clear="onPatientChanged"
          />
          <EdgeLinkField
            v-model="filters.customer"
            label="Pet Owner"
            placeholder="All Owners"
            :searcher="searchCustomer"
            :disabled="loading"
            @select="onCustomerChanged"
            @clear="onCustomerChanged"
          />
          <EdgeLinkField
            v-model="filters.practitioner"
            label="Attending Veterinarian"
            placeholder="All Veterinarians"
            :searcher="searchPractitioner"
            :disabled="loading"
            @select="applyFilters"
            @clear="applyFilters"
          />
          <EdgeLinkField
            v-model="filters.care_location"
            label="Care Location"
            placeholder="All Care Locations"
            :searcher="searchCareLocation"
            :disabled="loading"
            @select="applyFilters"
            @clear="applyFilters"
          />
          <EdgeDropdown
            v-model="filters.status"
            label="Status"
            :options="statusOptions"
            :disabled="loading"
            @change="applyFilters"
          />
          <EdgeDropdown
            v-model="filters.care_level"
            label="Care Level"
            :options="careLevelOptions"
            :disabled="loading"
            @change="applyFilters"
          />
          <EdgeInput
            v-model="filters.from_date"
            type="date"
            label="Admitted From"
            :disabled="loading"
            @change="applyFilters"
          />
          <EdgeInput
            v-model="filters.to_date"
            type="date"
            label="Admitted To"
            :disabled="loading"
            @change="applyFilters"
          />
        </div>
      </template>
      <template #filterActions>
        <button class="edge-button edge-button--primary" type="button" :disabled="loading" @click="applyFilters">
          Apply / Refresh
        </button>
        <button class="edge-button" type="button" :disabled="loading" @click="clearFilters">
          Clear Filters
        </button>
      </template>
      <template v-if="exceptionPanelSupported && advancedExceptionsEntitled" #chart>
        <EdgeReportExceptionPanel
          :title="exceptionPayload?.title || 'Hospitalisation Exceptions'"
          :description="exceptionPayload?.description || 'Operational exceptions requiring attention within the current Hospitalisation scope.'"
          :items="exceptionPayload?.items || []"
          :loading="exceptionLoading"
          emptyMessage="No pending Hospitalisation stock actions match the current filters."
          @open="openException"
        />
      </template>
      <template #resultMeta>
        <span>Active admissions only · activity and charge signals are enriched for the current page.</span>
      </template>
    </EdgeReportShell>
  </EdgeAppShell>
</template>

<script>
const requiredEdgeUIComponents = [
  'EdgeAppShell',
  'EdgeReportShell',
  'EdgeLinkField',
  'EdgeDropdown',
  'EdgeInput'
];
const optionalEdgeUIComponents = ['EdgeReportExceptionPanel'];

const runtimeComponents = () => {
  const runtime = typeof window !== 'undefined' ? (window.EdgeSuiteUI || window.EdgeUI || {}) : {};
  return runtime.components || runtime;
};

const OPERATIONS_API = 'vetedge.services.hospitalisation_operations.get_hospitalisation_operations';
const FILTER_API = 'vetedge.services.hospitalisation_filter_search.search_hospitalisation_filter_options';
const VISIBILITY_API = 'vetedge.services.report_visibility.get_visibility_context';
const CAPABILITIES_API = 'vetedge.services.reporting_capabilities.get_shell_capabilities';
const EXCEPTIONS_API = 'vetedge.services.report_exceptions.get_report_exceptions';
const EXCEPTION_SCOPE = 'Pending Hospitalisation Actions';
const EXCEPTION_KEY = 'hospitalisation_pending_stock';

export default {
  name: 'VetEdgeHospitalisationOperations',
  components: Object.fromEntries(
    [...requiredEdgeUIComponents, ...optionalEdgeUIComponents]
      .map((name) => [name, runtimeComponents()[name]])
      .filter(([, component]) => Boolean(component))
  ),
  data() {
    return {
      edgeUIValid: true,
      missingComponents: [],
      loading: true,
      error: '',
      rows: [],
      columns: [],
      summary: [],
      totalCount: 0,
      currentPage: 1,
      pageLength: 50,
      tenantName: '',
      branchName: 'All Branches',
      userName: '',
      visibilityDefaultBranch: '',
      exceptionLoading: false,
      exceptionPayload: null,
      exceptionRequestGeneration: 0,
      exceptionCapabilities: { advanced_features_entitled: false },
      filters: {
        branch: '',
        patient: '',
        customer: '',
        practitioner: '',
        care_location: '',
        status: '',
        care_level: '',
        from_date: '',
        to_date: '',
        active_only: 1
      },
      statusOptions: [
        { value: '', label: 'All Active Admissions' },
        { value: 'Admitted', label: 'Admitted' },
        { value: 'Under Care', label: 'Under Care' },
        { value: 'Ready for Discharge', label: 'Ready for Discharge' }
      ],
      careLevelOptions: [
        { value: '', label: 'All Care Levels' },
        { value: 'Standard', label: 'Standard' },
        { value: 'Observation', label: 'Observation' },
        { value: 'Intensive Care', label: 'Intensive Care' },
        { value: 'ICU', label: 'ICU' },
        { value: 'Isolation', label: 'Isolation' },
        { value: 'Recovery', label: 'Recovery' }
      ]
    };
  },
  computed: {
    displayColumns() {
      const clickable = new Set(['hospitalisation', 'patient_name', 'owner', 'care_location', 'attending_veterinarian']);
      return (this.columns || []).map((column) => ({ ...column, clickable: clickable.has(column.fieldname) }));
    },
    pagination() {
      const pageSize = Number(this.pageLength || 50);
      return {
        page: this.currentPage,
        page_size: pageSize,
        total_rows: Number(this.totalCount || 0),
        total_pages: Math.max(1, Math.ceil(Number(this.totalCount || 0) / Math.max(1, pageSize))),
        has_previous: this.currentPage > 1,
        has_next: this.currentPage * pageSize < Number(this.totalCount || 0)
      };
    },
    exceptionPanelSupported() {
      return Boolean(runtimeComponents().EdgeReportExceptionPanel);
    },
    advancedExceptionsEntitled() {
      return Boolean(this.exceptionCapabilities?.advanced_features_entitled);
    }
  },
  created() {
    const components = runtimeComponents();
    this.missingComponents = requiredEdgeUIComponents.filter((name) => !components[name]);
    this.edgeUIValid = this.missingComponents.length === 0;
  },
  mounted() {
    window.VetedgeProductMenu?.mount?.();
    this.syncShellContext();
    if (window.jQuery) {
      window.jQuery(document).on('branch-change.vetedge_hospitalisation_ops session-defaults-changed.vetedge_hospitalisation_ops', this.handleContextChange);
    }
    this.initialize();
  },
  beforeUnmount() {
    this.invalidateExceptionRequest();
    if (window.jQuery) window.jQuery(document).off('.vetedge_hospitalisation_ops');
  },
  methods: {
    retryRuntime() { window.location.reload(); },
    rowKey(row, index) { return row?.hospitalisation || `hospitalisation-${index}`; },
    syncShellContext() {
      const boot = window.frappe?.boot || {};
      const user = window.frappe?.session?.user || '';
      this.userName = boot.user_info?.[user]?.fullname || user || 'Veterinary User';
      this.tenantName = boot.sysdefaults?.company || 'Veterinary';
      this.branchName = boot.session_defaults?.branch || boot.edgesuite_product_menu?.branch || boot.user_info?.[user]?.branch || 'All Branches';
    },
    async initialize() {
      await this.loadVisibilityContext();
      await this.loadExceptionCapabilities();
      await this.refreshOperationalView();
    },
    async handleContextChange() {
      this.syncShellContext();
      this.currentPage = 1;
      this.filters.branch = '';
      this.invalidateExceptionRequest();
      await this.loadVisibilityContext();
      await this.loadExceptionCapabilities();
      await this.refreshOperationalView();
    },
    callFrappe(method, args = {}) {
      return new Promise((resolve, reject) => {
        if (!window.frappe?.call) return reject(new Error('Frappe Desk is not ready.'));
        frappe.call({ method, args, callback: (response) => resolve(response?.message || {}), error: reject });
      });
    },
    async loadVisibilityContext() {
      try {
        const context = await this.callFrappe(VISIBILITY_API, {
          scope_name: 'Active Hospitalisations',
          scope_type: 'report'
        });
        this.visibilityDefaultBranch = context?.default_branch || '';
        if (!this.filters.branch && this.visibilityDefaultBranch) this.filters.branch = this.visibilityDefaultBranch;
        if (this.filters.branch) this.branchName = this.filters.branch;
      } catch (error) {
        this.error = error?.message || 'Hospitalisation Branch visibility could not be resolved.';
      }
    },
    async loadExceptionCapabilities() {
      if (!this.exceptionPanelSupported) return;
      try {
        this.exceptionCapabilities = await this.callFrappe(CAPABILITIES_API, {
          scope_name: EXCEPTION_SCOPE,
          scope_type: 'report'
        });
      } catch (_error) {
        this.exceptionCapabilities = { advanced_features_entitled: false };
      }
      if (!this.advancedExceptionsEntitled) {
        this.invalidateExceptionRequest();
        this.exceptionPayload = null;
      }
    },
    requestFilters() {
      return Object.fromEntries(
        Object.entries(this.filters).filter(([, value]) => value !== undefined && value !== null && String(value) !== '')
      );
    },
    exceptionRequestSignature() {
      const filters = Object.entries(this.requestFilters())
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, value]) => [key, value]);
      return JSON.stringify({ exception_key: EXCEPTION_KEY, filters });
    },
    invalidateExceptionRequest() {
      this.exceptionRequestGeneration += 1;
      this.exceptionLoading = false;
    },
    async searchFilter(field, term) {
      const result = await this.callFrappe(FILTER_API, {
        field,
        txt: term || '',
        start: 0,
        page_length: 20,
        filters: JSON.stringify(this.requestFilters())
      });
      return Array.isArray(result) ? result : [];
    },
    searchBranch(term) { return this.searchFilter('branch', term); },
    searchPatient(term) { return this.searchFilter('patient', term); },
    searchCustomer(term) { return this.searchFilter('customer', term); },
    searchPractitioner(term) { return this.searchFilter('practitioner', term); },
    searchCareLocation(term) { return this.searchFilter('care_location', term); },
    onBranchChanged() {
      this.filters.patient = '';
      this.filters.customer = '';
      this.filters.practitioner = '';
      this.filters.care_location = '';
      this.branchName = this.filters.branch || this.visibilityDefaultBranch || 'All Branches';
      this.applyFilters();
    },
    onPatientChanged() {
      if (this.filters.patient) this.filters.customer = '';
      this.applyFilters();
    },
    onCustomerChanged() {
      if (this.filters.customer) this.filters.patient = '';
      this.applyFilters();
    },
    clearFilters() {
      this.filters = {
        branch: this.visibilityDefaultBranch || '', patient: '', customer: '', practitioner: '', care_location: '', status: '',
        care_level: '', from_date: '', to_date: '', active_only: 1
      };
      this.branchName = this.filters.branch || 'All Branches';
      this.currentPage = 1;
      this.refreshOperationalView();
    },
    applyFilters() {
      this.currentPage = 1;
      this.refreshOperationalView();
    },
    async refreshOperationalView() {
      this.invalidateExceptionRequest();
      this.exceptionPayload = null;
      const requests = [this.fetchData()];
      if (this.exceptionPanelSupported && this.advancedExceptionsEntitled) requests.push(this.fetchExceptions());
      await Promise.all(requests);
    },
    async fetchData() {
      this.loading = true;
      this.error = '';
      try {
        const payload = await this.callFrappe(OPERATIONS_API, {
          filters: JSON.stringify(this.requestFilters()),
          start: (this.currentPage - 1) * Number(this.pageLength || 50),
          page_length: Number(this.pageLength || 50)
        });
        this.rows = payload.rows || [];
        this.columns = payload.columns || [];
        this.summary = payload.summary || [];
        this.totalCount = Number(payload.total || 0);
      } catch (error) {
        this.error = error?.message || 'Hospitalisation Operations could not be loaded.';
      } finally {
        this.loading = false;
      }
    },
    async fetchExceptions() {
      if (!this.exceptionPanelSupported || !this.advancedExceptionsEntitled) return;
      const generation = ++this.exceptionRequestGeneration;
      const signature = this.exceptionRequestSignature();
      this.exceptionLoading = true;
      try {
        const payload = await this.callFrappe(EXCEPTIONS_API, {
          exception_key: EXCEPTION_KEY,
          filters: JSON.stringify(this.requestFilters())
        });
        if (generation !== this.exceptionRequestGeneration || signature !== this.exceptionRequestSignature()) return;
        this.exceptionPayload = payload || null;
      } catch (error) {
        if (generation !== this.exceptionRequestGeneration || signature !== this.exceptionRequestSignature()) return;
        this.exceptionPayload = null;
        console.warn('Hospitalisation exception feed could not be loaded', error);
      } finally {
        if (generation !== this.exceptionRequestGeneration || signature !== this.exceptionRequestSignature()) return;
        this.exceptionLoading = false;
      }
    },
    goToPage(page) {
      this.currentPage = Math.max(1, Number(page || 1));
      this.fetchData();
    },
    setPageSize(size) {
      this.pageLength = Math.min(100, Math.max(1, Number(size || 50)));
      this.currentPage = 1;
      this.fetchData();
    },
    formatCell(value, column) {
      if (value === null || value === undefined || value === '') return '—';
      if (column?.fieldtype === 'Currency') {
        const currency = window.frappe?.boot?.sysdefaults?.currency || 'NGN';
        try { return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(value || 0)); }
        catch (_error) { return `${currency} ${Number(value || 0).toLocaleString()}`; }
      }
      if (column?.fieldtype === 'Int') return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
      if (column?.fieldtype === 'Datetime' || column?.fieldtype === 'Date') {
        return window.frappe?.datetime?.str_to_user?.(value) || value;
      }
      return String(value);
    },
    openCell({ row, column, value }) {
      if (!window.frappe?.set_route || !column?.fieldname) return;
      const field = column.fieldname;
      if (field === 'hospitalisation' && row?.hospitalisation) frappe.set_route('Form', 'Veterinary Hospitalisation', row.hospitalisation);
      else if (field === 'patient_name' && row?.patient) frappe.set_route('Form', 'Veterinary Patient', row.patient);
      else if (field === 'owner' && row?.owner) frappe.set_route('Form', 'Customer', row.owner);
      else if (field === 'care_location' && row?.care_location) frappe.set_route('Form', 'Veterinary Care Location', row.care_location);
      else if (field === 'attending_veterinarian' && value) frappe.set_route('Form', 'User', value);
    },
    openException(item) {
      if (!window.frappe?.set_route || !item?.reference_doctype || !item?.reference_name) return;
      frappe.set_route('Form', item.reference_doctype, item.reference_name);
    }
  }
};
</script>

<style scoped>
.hospitalisation-filter-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(12rem, 1fr));
  gap: var(--edge-space-md, 16px);
  width: 100%;
}
.hospitalisation-runtime-error {
  margin: 20px;
  border: 1px solid var(--edge-danger, #ff4d4f);
  border-radius: 8px;
  background: var(--edge-surface, #fff);
  color: var(--edge-text, #172033);
}
.hospitalisation-runtime-error__detail { margin: 10px 0 16px; color: var(--edge-text-muted, #667085); }
@media (max-width: 900px) { .hospitalisation-filter-grid { grid-template-columns: repeat(2, minmax(10rem, 1fr)); } }
@media (max-width: 576px) { .hospitalisation-filter-grid { grid-template-columns: minmax(0, 1fr); } }
</style>

<style>
.vetedge-hospitalisation-operations-root .edge-sidebar,
.vetedge-hospitalisation-operations-root .edge-shell-sidebar { display: none !important; }
.vetedge-hospitalisation-operations-root .edge-shell-body,
.vetedge-hospitalisation-operations-root .edge-shell-main,
.vetedge-hospitalisation-operations-root .edge-page-layout,
.vetedge-hospitalisation-operations-root .edge-page-layout-body { width: 100%; max-width: none; min-width: 0; }
</style>
