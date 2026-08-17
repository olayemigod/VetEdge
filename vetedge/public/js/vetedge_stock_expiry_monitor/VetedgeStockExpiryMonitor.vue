<template>
  <div v-if="!edgeUIValid" class="p-6 text-center stock-expiry-runtime-error">
    <strong>EdgeSuite reporting shell failed to load</strong>
    <div v-if="missingComponents.length" class="stock-expiry-runtime-error__detail">
      Missing components: {{ missingComponents.join(', ') }}
    </div>
    <button class="edge-button edge-button--primary" type="button" @click="retryRuntime">Retry</button>
  </div>

  <EdgeAppShell
    v-else
    product="vetedge"
    activeRoute="/app/stock-expiry-monitor"
    title="Veterinary"
    :tenantName="tenantName"
    :branchName="branchName"
    :userName="userName"
    data-edge-product="vetedge"
  >
    <template #notifications>
      <EdgeNotificationBell
        :unreadCount="notificationUnreadCount"
        title="Notifications"
        @toggle="toggleNotificationDrawer"
      />
      <EdgeNotificationDrawer
        product="vetedge"
        title="Notifications"
        :open="notificationDrawerOpen"
        :notifications="filteredNotifications"
        :unreadCount="notificationUnreadCount"
        :filter="notificationFilter"
        :loading="notificationLoading"
        :error="notificationError"
        @close="notificationDrawerOpen = false"
        @update:filter="setNotificationFilter"
        @retry="fetchNotifications"
        @refresh="fetchNotifications"
        @mark-all-read="markAllNotificationsRead"
        @action="runNotificationAction"
        @open="openNotificationRoute"
      />
    </template>

    <EdgeReportShell
      title="Stock Expiry Monitor"
      eyebrow="Inventory"
      subtitle="Track expired and soon-to-expire batch stock with server-paginated results."
      :columns="columns"
      :rows="rows"
      :summary="summaryCards"
      :pagination="pagination"
      :loading="loading"
      :error="error"
      :rowKey="rowKey"
      :formatter="formatCell"
      :exportEnabled="capabilities.can_export"
      :printEnabled="capabilities.can_print"
      :exportBusy="exportBusy"
      :printBusy="printBusy"
      :exportInitialOptions="exportInitialOptions"
      emptyTitle="No expiry records"
      emptyDescription="No batch stock matches the current expiry filters."
      loadingMessage="Fetching batch inventory data…"
      @retry="fetchData"
      @page-change="goToPage"
      @page-size-change="setPageSize"
      @cell-click="openCell"
      @export="runExport"
      @print="runPrint"
    >
      <template #filters>
        <div class="stock-expiry-filter-grid">
          <EdgeLinkField
            v-model="filters.warehouse"
            label="Warehouse"
            placeholder="All Warehouses"
            :searcher="searchWarehouse"
            :disabled="loading"
            @select="applyFilters"
            @clear="applyFilters"
          />
          <EdgeLinkField
            v-model="filters.item_group"
            label="Item Group"
            placeholder="All Item Groups"
            :searcher="searchItemGroup"
            :disabled="loading"
            @select="applyFilters"
            @clear="applyFilters"
          />
          <EdgeLinkField
            v-model="filters.item"
            label="Item"
            placeholder="All Items"
            :searcher="searchItem"
            :disabled="loading"
            @select="applyFilters"
            @clear="applyFilters"
          />
          <EdgeDropdown
            v-model="filters.expiry_window"
            label="Expiry Window"
            :options="expiryWindowOptions"
            :disabled="loading"
            @change="applyFilters"
          />
          <EdgeDropdown
            v-model="filters.days_threshold"
            label="Days Threshold"
            :options="thresholdOptions"
            :disabled="loading"
            @change="applyFilters"
          />
        </div>
      </template>
      <template #filterActions>
        <button class="edge-button edge-button--primary" type="button" :disabled="loading" @click="applyFilters">
          Apply / Refresh
        </button>
      </template>
      <template #resultMeta>
        <span v-if="summary.last_updated">Last recalculated {{ formatTime(summary.last_updated) }}</span>
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
  'EdgeNotificationBell',
  'EdgeNotificationDrawer'
];

const notificationApi = {
  feed: 'vetedge.services.notification_api.get_my_edgesuite_notifications',
  markRead: 'vetedge.services.notification_api.mark_my_edgesuite_notification_read',
  markAllRead: 'vetedge.services.notification_api.mark_all_my_notifications_read',
  acknowledge: 'vetedge.services.notification_api.acknowledge_my_notification',
  done: 'vetedge.services.notification_api.mark_my_notification_done',
  dismiss: 'vetedge.services.notification_api.dismiss_my_notification'
};

const runtimeComponents = () => {
  const runtime = typeof window !== 'undefined' ? (window.EdgeSuiteUI || window.EdgeUI || {}) : {};
  return runtime.components || runtime;
};

export default {
  name: 'VetedgeStockExpiryMonitor',
  components: Object.fromEntries(requiredEdgeUIComponents.map((name) => [name, runtimeComponents()[name]])),
  data() {
    return {
      edgeUIValid: true,
      missingComponents: [],
      loading: true,
      error: '',
      summary: {},
      rows: [],
      totalCount: 0,
      currentPage: 1,
      tenantName: '',
      branchName: 'All Branches',
      userName: '',
      exportBusy: false,
      printBusy: false,
      capabilities: { can_view: true, can_print: false, can_export: false },
      notificationDrawerOpen: false,
      notificationLoading: false,
      notificationError: '',
      notificationFilter: 'all',
      notificationItems: [],
      notificationUnreadCount: 0,
      filters: {
        warehouse: '',
        item_group: '',
        expiry_window: 'all',
        days_threshold: 60,
        item: '',
        limit: 50,
        offset: 0
      },
      expiryWindowOptions: [
        { value: 'all', label: 'All Inventory' },
        { value: 'expired', label: 'Expired Batches' },
        { value: 'expiring soon', label: 'Expiring Soon' }
      ],
      thresholdOptions: [30, 60, 90, 180].map((value) => ({ value, label: `${value} Days` })),
      columns: [
        { fieldname: 'item_code', label: 'Item Code', fieldtype: 'Link', options: 'Item', clickable: true },
        { fieldname: 'item_name', label: 'Item Name', fieldtype: 'Data' },
        { fieldname: 'batch_no', label: 'Batch No', fieldtype: 'Link', options: 'Batch', clickable: true },
        { fieldname: 'warehouse', label: 'Warehouse', fieldtype: 'Link', options: 'Warehouse', clickable: true },
        { fieldname: 'qty', label: 'Quantity', fieldtype: 'Float' },
        { fieldname: 'stock_uom', label: 'UOM', fieldtype: 'Data' },
        { fieldname: 'expiry_date', label: 'Expiry Date', fieldtype: 'Date' },
        { fieldname: 'days_to_expiry', label: 'Days Left', fieldtype: 'Int' },
        { fieldname: 'expiry_status', label: 'Risk Status', fieldtype: 'Data' },
        { fieldname: 'branch', label: 'Branch', fieldtype: 'Link', options: 'Branch' }
      ],
      exportInitialOptions: {
        format: 'xlsx',
        scope: 'all_filtered',
        include_summary: true,
        include_filters: true,
        include_charts: true,
        include_title: true,
        include_generated_metadata: true,
        repeat_table_headings: true
      }
    };
  },
  computed: {
    summaryCards() {
      return [
        { key: 'expired', label: 'Expired Batches', value: Number(this.summary.expired_items || 0), datatype: 'Int', tone: 'danger' },
        { key: 'soon', label: 'Expiring Soon', value: Number(this.summary.expiring_soon || 0), datatype: 'Int', tone: 'warning' },
        { key: 'qty', label: 'Affected Total Qty', value: Number(this.summary.affected_qty || 0), datatype: 'Float' },
        { key: 'warehouses', label: 'Affected Warehouses', value: Number(this.summary.affected_warehouses || 0), datatype: 'Int' },
        { key: 'risk', label: 'Highest Risk Items', value: Number(this.summary.highest_risk_items || 0), datatype: 'Int' }
      ];
    },
    pagination() {
      const pageSize = Number(this.filters.limit || 50);
      return {
        page: this.currentPage,
        page_size: pageSize,
        total_rows: Number(this.totalCount || 0),
        total_pages: Math.max(1, Math.ceil(Number(this.totalCount || 0) / pageSize)),
        has_previous: this.currentPage > 1,
        has_next: this.currentPage * pageSize < Number(this.totalCount || 0)
      };
    },
    filteredNotifications() {
      if (this.notificationFilter === 'unread') return this.notificationItems.filter((item) => item.status === 'Unread');
      if (this.notificationFilter === 'action_required') return this.notificationItems.filter((item) => (item.actions || []).length > 0);
      if (this.notificationFilter === 'done') return this.notificationItems.filter((item) => ['Done', 'Dismissed', 'Archived'].includes(item.status));
      return this.notificationItems;
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
      window.jQuery(document).on('branch-change.vetedge_stock_shell session-defaults-changed.vetedge_stock_shell', this.handleContextChange);
    }
    this.fetchCapabilities();
    this.fetchData();
    this.fetchNotifications();
  },
  beforeUnmount() {
    if (window.jQuery) window.jQuery(document).off('.vetedge_stock_shell');
  },
  methods: {
    retryRuntime() { window.location.reload(); },
    rowKey(row, index) { return `${row?.batch_no || 'batch'}:${row?.warehouse || 'warehouse'}:${index}`; },
    syncShellContext() {
      const boot = window.frappe?.boot || {};
      const user = window.frappe?.session?.user || '';
      this.userName = boot.user_info?.[user]?.fullname || user || 'Veterinary User';
      this.tenantName = boot.sysdefaults?.company || 'Veterinary';
      this.branchName = boot.session_defaults?.branch || boot.edgesuite_product_menu?.branch || boot.user_info?.[user]?.branch || 'All Branches';
    },
    handleContextChange() {
      this.syncShellContext();
      this.currentPage = 1;
      this.fetchCapabilities(true);
      this.fetchData();
    },
    callFrappe(method, args = {}) {
      return new Promise((resolve, reject) => {
        if (!window.frappe?.call) return reject(new Error('Frappe Desk is not ready.'));
        frappe.call({ method, args, callback: (response) => resolve(response?.message || {}), error: reject });
      });
    },
    async fetchCapabilities(refresh = false) {
      try {
        if (window.VetEdgeReportingCapabilities?.get) {
          this.capabilities = await window.VetEdgeReportingCapabilities.get('Stock Expiry Status', 'report', { refresh });
        } else {
          this.capabilities = await this.callFrappe('vetedge.services.reporting_capabilities.get_shell_capabilities', {
            scope_name: 'Stock Expiry Status', scope_type: 'report'
          });
        }
      } catch (_error) {
        this.capabilities = { can_view: true, can_print: false, can_export: false };
      }
    },
    async searchStockFilter(field, term) {
      const result = await this.callFrappe('vetedge.veterinary.page.stock_expiry_monitor.stock_expiry_monitor.search_stock_expiry_filter_options', {
        field, txt: term || '', start: 0, page_length: 20
      });
      return Array.isArray(result) ? result : [];
    },
    searchWarehouse(term) { return this.searchStockFilter('warehouse', term); },
    searchItemGroup(term) { return this.searchStockFilter('item_group', term); },
    async searchItem(term) {
      const result = await this.callFrappe('frappe.desk.search.search_link', {
        doctype: 'Item', txt: term || '', page_length: 20, ignore_user_permissions: 0
      });
      return (Array.isArray(result) ? result : []).map((row) => ({
        value: row.value || row.name || row[0],
        label: row.description ? `${row.value || row.name || row[0]} — ${row.description}` : (row.value || row.name || row[0])
      }));
    },
    applyFilters() {
      this.currentPage = 1;
      this.fetchData();
    },
    async fetchData() {
      this.loading = true;
      this.error = '';
      this.filters.offset = (this.currentPage - 1) * Number(this.filters.limit || 50);
      try {
        const payload = await this.callFrappe('vetedge.veterinary.page.stock_expiry_monitor.stock_expiry_monitor.get_stock_expiry_data', { filters: this.filters });
        this.summary = payload.summary || {};
        this.rows = payload.rows || [];
        this.totalCount = Number(payload.total_count || 0);
      } catch (error) {
        this.error = error?.message || 'Stock expiry data could not be loaded.';
      } finally {
        this.loading = false;
      }
    },
    goToPage(page) {
      this.currentPage = Math.max(1, Number(page || 1));
      this.fetchData();
    },
    setPageSize(size) {
      this.filters.limit = Math.min(100, Math.max(1, Number(size || 50)));
      this.currentPage = 1;
      this.fetchData();
    },
    formatDate(value) { return value ? (window.frappe?.datetime?.str_to_user?.(value) || value) : '—'; },
    formatTime(value) { return value ? (String(value).split(' ')[1] || value) : '—'; },
    formatDays(days) {
      if (days === null || days === undefined || days === '') return '—';
      const value = Number(days);
      if (value < 0) return `Expired (${Math.abs(value)}d ago)`;
      if (value === 0) return 'Expires Today';
      return `${value} days`;
    },
    formatCell(value, column) {
      if (column?.fieldname === 'expiry_date') return this.formatDate(value);
      if (column?.fieldname === 'days_to_expiry') return this.formatDays(value);
      if (column?.fieldname === 'qty') return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
      return value === null || value === undefined || value === '' ? '—' : String(value);
    },
    openCell({ row, column, value }) {
      const doctype = column?.options;
      if (doctype && value && window.frappe?.set_route) frappe.set_route('Form', doctype, value);
    },
    exportRuntime() {
      return window.EdgeSuiteReportExport || window.EdgeSuiteUI?.reportExport || window.EdgeUI?.reportExport || null;
    },
    printRuntime() {
      return window.EdgeSuiteReportPrint || window.EdgeSuiteUI?.reportPrint || window.EdgeUI?.reportPrint || null;
    },
    async runExport(options) {
      const runtime = this.exportRuntime();
      if (!runtime?.normalizeOptions || !runtime?.downloadVerified) {
        frappe.msgprint?.('The shared EdgeSuite export runtime is unavailable.');
        return;
      }
      this.exportBusy = true;
      try {
        const normalized = runtime.normalizeOptions(options || {});
        const formData = new FormData();
        formData.append('filters', JSON.stringify(this.filters));
        formData.append('options', JSON.stringify(normalized));
        formData.append('start', String((this.currentPage - 1) * Number(this.filters.limit || 50)));
        formData.append('page_length', String(this.filters.limit || 50));
        const xhr = await new Promise((resolve, reject) => {
          const request = new XMLHttpRequest();
          request.open('POST', '/api/method/vetedge.services.stock_expiry_reporting_actions.download_stock_expiry_export');
          request.responseType = 'arraybuffer';
          request.setRequestHeader('X-Frappe-CSRF-Token', frappe.csrf_token);
          request.onload = () => request.status >= 200 && request.status < 300 ? resolve(request) : reject(new Error(`Stock Expiry export failed with HTTP ${request.status}.`));
          request.onerror = () => reject(new Error('Stock Expiry export request failed.'));
          request.send(formData);
        });
        runtime.downloadVerified({
          bytes: new Uint8Array(xhr.response || []),
          format: normalized.format,
          mime: xhr.getResponseHeader('Content-Type') || runtime.expectedMime(normalized.format),
          filename: `Stock-Expiry-Monitor.${normalized.format}`
        });
      } catch (error) {
        frappe.msgprint?.(error?.message || 'Stock Expiry export failed.');
      } finally {
        this.exportBusy = false;
      }
    },
    async runPrint() {
      const runtime = this.printRuntime();
      const exports = this.exportRuntime();
      if (!runtime?.open || !exports?.normalizeOptions) {
        frappe.msgprint?.('The shared EdgeSuite print runtime is unavailable.');
        return;
      }
      const printWindow = window.open('', '_blank');
      if (!printWindow) {
        frappe.msgprint?.('Please allow pop-ups for this site before printing.');
        return;
      }
      this.printBusy = true;
      try {
        const options = exports.normalizeOptions({ ...this.exportInitialOptions, format: 'pdf', scope: 'all_filtered' });
        const html = await this.callFrappe('vetedge.services.stock_expiry_reporting_actions.get_stock_expiry_print_html', {
          filters: JSON.stringify(this.filters), options: JSON.stringify(options),
          start: (this.currentPage - 1) * Number(this.filters.limit || 50), page_length: Number(this.filters.limit || 50)
        });
        runtime.open({ html: html || '', title: 'Stock Expiry Monitor', printWindow });
      } catch (error) {
        printWindow.close?.();
        frappe.msgprint?.(error?.message || 'Stock Expiry print generation failed.');
      } finally {
        this.printBusy = false;
      }
    },
    toggleNotificationDrawer() {
      this.notificationDrawerOpen = !this.notificationDrawerOpen;
      if (this.notificationDrawerOpen) this.fetchNotifications();
    },
    setNotificationFilter(value) { this.notificationFilter = value; this.fetchNotifications(); },
    async fetchNotifications() {
      this.notificationLoading = true;
      this.notificationError = '';
      try {
        const message = await this.callFrappe(notificationApi.feed, { filter_key: this.notificationFilter, limit: 30 });
        this.notificationItems = message.items || [];
        this.notificationUnreadCount = Number(message.unread_count || 0);
      } catch (error) {
        this.notificationError = error?.message || 'Notifications could not be loaded.';
      } finally { this.notificationLoading = false; }
    },
    async runNotificationAction(payload) {
      const action = payload?.action;
      const notification = payload?.notification;
      const method = { mark_read: notificationApi.markRead, acknowledge: notificationApi.acknowledge, done: notificationApi.done, dismiss: notificationApi.dismiss }[action?.key];
      if (!method || !notification?.name) return;
      try { await this.callFrappe(method, { notification_name: notification.name }); await this.fetchNotifications(); }
      catch (error) { this.notificationError = error?.message || 'Notification action failed.'; }
    },
    async markAllNotificationsRead() {
      try { await this.callFrappe(notificationApi.markAllRead); await this.fetchNotifications(); }
      catch (error) { this.notificationError = error?.message || 'Could not mark notifications read.'; }
    },
    openNotificationRoute(notification) {
      if (!notification?.route || !window.frappe?.set_route) return;
      frappe.set_route(notification.route.replace(/^\/app\//, '').split('/').filter(Boolean).map(decodeURIComponent));
      this.notificationDrawerOpen = false;
    }
  }
};
</script>

<style scoped>
.stock-expiry-filter-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(12rem, 1fr));
  gap: var(--edge-space-md, 16px);
  width: 100%;
}
.stock-expiry-runtime-error {
  margin: 20px;
  border: 1px solid var(--edge-danger, #ff4d4f);
  border-radius: 8px;
  background: var(--edge-surface, #fff);
  color: var(--edge-text, #172033);
}
.stock-expiry-runtime-error__detail { margin: 10px 0 16px; color: var(--edge-text-muted, #667085); }
@media (max-width: 900px) { .stock-expiry-filter-grid { grid-template-columns: repeat(2, minmax(10rem, 1fr)); } }
@media (max-width: 576px) { .stock-expiry-filter-grid { grid-template-columns: minmax(0, 1fr); } }
</style>

<style>
.vetedge-expiry-monitor-root .edge-sidebar,
.vetedge-expiry-monitor-root .edge-shell-sidebar { display: none !important; }
.vetedge-expiry-monitor-root .edge-shell-body,
.vetedge-expiry-monitor-root .edge-shell-main,
.vetedge-expiry-monitor-root .edge-page-layout,
.vetedge-expiry-monitor-root .edge-page-layout-body { width: 100%; max-width: none; min-width: 0; }
</style>
