<template>
  <div v-if="!edgeUIValid" class="p-6 text-center" style="border: 1px solid var(--edge-danger, #ff4d4f); border-radius: 8px; background-color: var(--edge-surface, #ffffff); margin: 20px;">
    <div style="color: var(--edge-danger, #ff4d4f); font-weight: bold; font-size: 1.2rem; margin-bottom: 12px;">
      EdgeSuite UI Layout Components Resolution Failed
    </div>
    <div style="color: var(--edge-text-muted, #8c8c8c); margin-bottom: 20px; font-size: 14px;">
      Required layout components (EdgeAppShell, EdgePageLayout, EdgeFilterBar) could not be resolved from window.EdgeUI.
    </div>
    <button @click="fetchData" style="padding: 8px 16px; background-color: var(--edge-primary, #1890ff); color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600;">
      Retry Loading Monitor
    </button>
  </div>

  <EdgeAppShell
    v-else
    product="vetedge"
    :menuItems="menuItems"
    activeRoute="/app/stock-expiry-monitor"
    title="VetEdge"
    :tenantName="tenantName"
    :branchName="branchName"
    :userName="userName"
    @navigate="handleNavigation"
    data-edge-product="vetedge"
  >
    <EdgePageLayout>
      <template #header>
        <EdgePageHeader 
          title="Stock Expiry Monitor" 
          subtitle="Track soon-to-expire batch stock and optimize inventory safety windows"
          :withBackButton="false"
        />
      </template>

      <!-- EdgeFilterBar in default slot body flow -->
      <EdgeFilterBar title="Filter Records">
        <div class="filter-group">
          <label class="filter-label">Warehouse</label>
          <select v-model="filters.warehouse" class="filter-select" :disabled="metadataLoading" @change="fetchData">
            <option value="">All Warehouses</option>
            <option v-for="w in warehouses" :key="w" :value="w">{{ w }}</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">Item Group</label>
          <select v-model="filters.item_group" class="filter-select" :disabled="metadataLoading" @change="fetchData">
            <option value="">All Item Groups</option>
            <option v-for="g in itemGroups" :key="g" :value="g">{{ g }}</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">Expiry Window</label>
          <select v-model="filters.expiry_window" class="filter-select" :disabled="metadataLoading" @change="fetchData">
            <option value="all">All Inventory</option>
            <option value="expired">Expired Batches</option>
            <option value="expiring soon">Expiring Soon</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">Days Threshold</label>
          <select v-model="filters.days_threshold" class="filter-select" :disabled="metadataLoading" @change="fetchData">
            <option :value="30">30 Days</option>
            <option :value="60">60 Days</option>
            <option :value="90">90 Days</option>
            <option :value="180">180 Days</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">Item Code</label>
          <input type="text" v-model="filters.item" placeholder="Enter Item Code" class="filter-input" :disabled="metadataLoading" @change="fetchData" />
        </div>
        <div class="filter-group filter-action-group">
          <label class="filter-label" style="visibility: hidden;">Action</label>
          <button class="filter-btn primary" :disabled="metadataLoading || loading" @click="fetchData">
            Apply / Refresh
          </button>
        </div>
      </EdgeFilterBar>

      <!-- Error/Loading states -->
      <div v-if="error" class="p-6">
        <EdgeErrorState 
          title="Inventory Fetch Failed" 
          :message="error" 
          @retry="fetchData"
        />
      </div>

      <div v-else-if="loading" class="p-6">
        <EdgeLoadingState message="Fetching batch inventory data..." :skeleton="true" />
      </div>

      <div v-else>
        <!-- Summary stats grid -->
        <div class="summary-stats-grid">
          <EdgeStatCard 
            label="Expired Batches" 
            :value="summary.expired_items || 0" 
            icon="❌" 
            tooltip="Total number of batches whose expiry date has passed"
          />
          <EdgeStatCard 
            label="Expiring Soon" 
            :value="summary.expiring_soon || 0" 
            icon="⚠️" 
            tooltip="Total number of batches expiring within the selected threshold window"
          />
          <EdgeStatCard 
            label="Affected Total Qty" 
            :value="formatQty(summary.affected_qty)" 
            icon="📦" 
            tooltip="Sum of quantities for all expired and expiring soon batches"
          />
          <EdgeStatCard 
            label="Affected Warehouses" 
            :value="summary.affected_warehouses || 0" 
            icon="🏬" 
            tooltip="Number of distinct warehouses carrying expired/expiring soon stock"
          />
          <EdgeStatCard 
            label="Highest Risk Items" 
            :value="summary.highest_risk_items || 0" 
            icon="🚨" 
            tooltip="Count of unique items with at least one fully expired batch"
          />
          <EdgeStatCard 
            label="Last Recalculated" 
            :value="formatTime(summary.last_updated)" 
            icon="🔄" 
            tooltip="Time of the last server side stock execution query"
          />
        </div>

        <!-- Main Data Table -->
        <div v-if="rows.length > 0" class="table-container-card">
          <div class="table-responsive">
            <table class="dashboard-table">
              <thead>
                <tr>
                  <th>Item Code</th>
                  <th>Item Name</th>
                  <th>Batch No</th>
                  <th>Warehouse</th>
                  <th class="text-right">Quantity</th>
                  <th>Expiry Date</th>
                  <th class="text-right">Days left</th>
                  <th>Risk Status</th>
                  <th>Branch</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in rows" :key="row.batch_no + '-' + row.warehouse">
                  <td class="bold-text">
                    <a href="#" @click.prevent="openDoc('Item', row.item_code)" class="doc-link">
                      {{ row.item_code }}
                    </a>
                  </td>
                  <td class="name-cell">{{ row.item_name }}</td>
                  <td>
                    <a href="#" @click.prevent="openDoc('Batch', row.batch_no)" class="doc-link font-mono">
                      {{ row.batch_no || '--' }}
                    </a>
                  </td>
                  <td>
                    <a href="#" @click.prevent="openDoc('Warehouse', row.warehouse)" class="doc-link">
                      {{ row.warehouse }}
                    </a>
                  </td>
                  <td class="text-right font-mono bold-text">{{ formatQty(row.qty) }} {{ row.stock_uom }}</td>
                  <td>{{ formatDate(row.expiry_date) }}</td>
                  <td class="text-right font-mono" :class="getDaysStyle(row.days_to_expiry)">
                    {{ formatDays(row.days_to_expiry) }}
                  </td>
                  <td>
                    <EdgeStatusBadge :label="row.expiry_status" :status="row.expiry_status" />
                  </td>
                  <td>{{ row.branch || '--' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          <div class="pagination-footer">
            <span class="page-info">Showing page {{ currentPage }} ({{ rows.length }} of {{ totalCount }} records)</span>
            <div class="pagination-buttons">
              <button 
                class="pagination-btn" 
                :disabled="currentPage === 1" 
                @click="changePage(-1)"
              >
                Previous
              </button>
              <button 
                class="pagination-btn" 
                :disabled="currentPage * filters.limit >= totalCount" 
                @click="changePage(1)"
              >
                Next
              </button>
            </div>
          </div>
        </div>

        <!-- Empty State -->
        <div v-else class="empty-state-container">
          <EdgeEmptyState 
            title="No Expiry Records" 
            description="Congratulations! No inventory batch expiries exist matching the current filters."
            icon="check-circle"
          />
        </div>
      </div>
    </EdgePageLayout>
  </EdgeAppShell>
</template>

<script>
// Safely consume CoreEdge EdgeUI elements from the global window namespace
const getRequiredComponent = (name) => {
  if (typeof window === 'undefined') return null;
  const edgeUI = window.EdgeUI || {};
  const componentsSrc = edgeUI.components || edgeUI;
  return componentsSrc[name] || null;
};

const getComponent = (name) => {
  if (typeof window === 'undefined') return 'div';
  const edgeUI = window.EdgeUI || {};
  const componentsSrc = edgeUI.components || edgeUI;
  return componentsSrc[name] || 'div';
};

const EdgeAppShell = getRequiredComponent('EdgeAppShell');
const EdgePageLayout = getRequiredComponent('EdgePageLayout');
const EdgeFilterBar = getRequiredComponent('EdgeFilterBar');
const EdgePageHeader = getComponent('EdgePageHeader');
const EdgeStatCard = getComponent('EdgeStatCard');
const EdgeStatusBadge = getComponent('EdgeStatusBadge');
const EdgeEmptyState = getComponent('EdgeEmptyState');
const EdgeLoadingState = getComponent('EdgeLoadingState');
const EdgeErrorState = getComponent('EdgeErrorState');

export default {
  name: 'VetedgeStockExpiryMonitor',
  components: {
    EdgePageHeader,
    EdgeStatCard,
    EdgeStatusBadge,
    EdgeEmptyState,
    EdgeLoadingState,
    EdgeErrorState,
    EdgeAppShell,
    EdgePageLayout,
    EdgeFilterBar
  },
  data() {
    return {
      edgeUIValid: true,
      metadataLoading: true,
      loading: true,
      error: '',
      summary: {},
      rows: [],
      totalCount: 0,
      warehouses: [],
      itemGroups: [],
      currentPage: 1,
      tenantName: '',
      branchName: '',
      userName: '',
      filters: {
        warehouse: '',
        item_group: '',
        expiry_window: 'all',
        days_threshold: 60,
        item: '',
        limit: 50,
        offset: 0
      },
      menuItems: [
        { label: 'Stock Expiry Monitor', route: '/app/stock-expiry-monitor', icon: '📦' },
        { label: 'Veterinary Settings', route: '/app/veterinary-settings', icon: '⚙️' }
      ]
    };
  },
  created() {
    if (typeof window !== 'undefined') {
      const edgeUI = window.EdgeUI || {};
      const componentsSrc = edgeUI.components || edgeUI;
      if (!componentsSrc.EdgeAppShell || !componentsSrc.EdgePageLayout || !componentsSrc.EdgeFilterBar) {
        this.edgeUIValid = false;
      }
    }
  },
  mounted() {
    this.fetchMetadata();
    this.fetchData();
  },
  methods: {
    formatDate(dateStr) {
      if (!dateStr || typeof frappe === 'undefined') return dateStr;
      return frappe.datetime.str_to_user(dateStr);
    },
    formatQty(val) {
      const num = parseFloat(val || 0);
      return num.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    },
    formatDays(days) {
      if (days === null || days === undefined) return '--';
      if (days < 0) return `Expired (${Math.abs(days)}d ago)`;
      if (days === 0) return 'Expires Today';
      return `${days} days`;
    },
    formatTime(timeStr) {
      if (!timeStr) return '--';
      return timeStr.split(' ')[1] || timeStr;
    },
    getDaysStyle(days) {
      if (days === null || days === undefined) return '';
      if (days < 0) return 'red-text';
      if (days <= this.filters.days_threshold) return 'orange-text';
      return 'green-text';
    },
    openDoc(doctype, name) {
      if (typeof frappe !== 'undefined' && name) {
        frappe.set_route('Form', doctype, name);
      }
    },
    fetchMetadata() {
      if (typeof frappe === 'undefined') {
        this.metadataLoading = false;
        return;
      }
      
      this.metadataLoading = true;

      // Populate user info from frappe.boot if present
      if (frappe.boot) {
        this.userName = frappe.boot.user_info?.[frappe.session.user]?.fullname || frappe.session.user;
        this.tenantName = frappe.boot.sysdefaults?.company || 'VetEdge';
        this.branchName = frappe.boot.user_info?.[frappe.session.user]?.branch || '';
      }

      // Fetch warehouses
      frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Warehouse',
          fields: ['name'],
          filters: { is_group: 0 },
          limit_page_length: 500
        },
        callback: (r) => {
          if (r.message) {
            this.warehouses = r.message.map(w => w.name);
          }
        }
      });

      // Fetch active item groups
      frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Item Group',
          fields: ['name'],
          limit_page_length: 500
        },
        callback: (r) => {
          this.metadataLoading = false;
          if (r.message) {
            this.itemGroups = r.message.map(g => g.name);
          }
        },
        error: () => {
          this.metadataLoading = false;
        }
      });
    },
    fetchData() {
      if (typeof frappe === 'undefined') {
        this.loading = false;
        return;
      }

      this.loading = true;
      this.error = '';
      
      this.filters.offset = (this.currentPage - 1) * this.filters.limit;

      frappe.call({
        method: 'vetedge.veterinary.page.stock_expiry_monitor.stock_expiry_monitor.get_stock_expiry_data',
        args: {
          filters: this.filters
        },
        callback: (r) => {
          this.loading = false;
          if (r.message) {
            this.summary = r.message.summary || {};
            this.rows = r.message.rows || [];
            this.totalCount = r.message.total_count || 0;
          }
        },
        error: (err) => {
          this.loading = false;
          this.error = err.message || 'An error occurred during query execution.';
        }
      });
    },
    changePage(direction) {
      this.currentPage += direction;
      this.fetchData();
    },
    handleNavigation(route) {
      if (typeof frappe !== 'undefined') {
        if (route === '/app/stock-expiry-monitor') {
          frappe.set_route('stock-expiry-monitor');
        } else if (route === '/app/veterinary-settings') {
          frappe.set_route('Form', 'Veterinary Settings', 'Veterinary Settings');
        }
      }
    }
  }
}
</script>

<style scoped>
/* Filter Group styles */
.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--edge-space-xs);
}

.filter-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--edge-text-muted);
}

.filter-input, .filter-select {
  padding: 8px 12px;
  border: 1px solid var(--edge-border);
  border-radius: var(--edge-radius-md);
  background-color: var(--edge-bg);
  color: var(--edge-text);
  font-size: var(--edge-text-sm);
  transition: border-color 0.2s ease;
  width: 100%;
}

.filter-input:focus, .filter-select:focus {
  border-color: var(--edge-primary);
  outline: none;
}

.filter-action-group {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.filter-btn {
  padding: 8px 16px;
  border-radius: var(--edge-radius-md);
  font-size: var(--edge-text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
  width: 100%;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.filter-btn.primary {
  background-color: var(--edge-primary);
  color: white;
}

.filter-btn.primary:hover:not(:disabled) {
  opacity: 0.9;
}

.filter-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Stats grid */
.summary-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--edge-space-md);
  margin-bottom: var(--edge-space-lg);
}

/* Table Card */
.table-container-card {
  background-color: var(--edge-surface);
  border: 1px solid var(--edge-border);
  border-radius: var(--edge-radius-lg);
  box-shadow: var(--edge-shadow-sm);
  overflow: hidden;
  margin-top: var(--edge-space-lg);
}

.table-responsive {
  overflow-x: auto;
}

.dashboard-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--edge-text-sm);
}

.dashboard-table th {
  background-color: var(--edge-bg);
  border-bottom: 1px solid var(--edge-border);
  padding: var(--edge-space-md);
  text-align: left;
  font-weight: 600;
  color: var(--edge-text-muted);
  white-space: nowrap;
}

.dashboard-table td {
  padding: var(--edge-space-md);
  border-bottom: 1px solid var(--edge-border);
  white-space: nowrap;
}

.dashboard-table tr:last-child td {
  border-bottom: none;
}

.doc-link {
  color: var(--edge-primary);
  text-decoration: none;
  font-weight: 500;
}

.doc-link:hover {
  text-decoration: underline;
}

.name-cell {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bold-text {
  font-weight: 600;
}

.text-right {
  text-align: right !important;
}

.font-mono {
  font-family: monospace;
}

.red-text {
  color: var(--edge-danger);
  font-weight: 600;
}

.orange-text {
  color: var(--edge-warning, #fa8c16);
  font-weight: 600;
}

.green-text {
  color: var(--edge-success, #52c41a);
}

/* Pagination */
.pagination-footer {
  padding: var(--edge-space-md) var(--edge-space-lg);
  border-top: 1px solid var(--edge-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--edge-space-md);
  background-color: var(--edge-bg);
}

.page-info {
  font-size: 0.815rem;
  color: var(--edge-text-muted);
}

.pagination-buttons {
  display: flex;
  gap: var(--edge-space-sm);
}

.pagination-btn {
  padding: 6px 12px;
  border: 1px solid var(--edge-border);
  border-radius: var(--edge-radius-md);
  background-color: var(--edge-surface);
  color: var(--edge-text);
  font-size: 0.815rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.pagination-btn:hover:not(:disabled) {
  border-color: var(--edge-primary);
  color: var(--edge-primary);
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-state-container {
  padding: var(--edge-space-xl) 0;
}
</style>
