<template>
  <div v-if="!edgeUIValid" class="p-6 text-center" style="border: 1px solid var(--edge-danger, #ff4d4f); border-radius: 8px; background-color: var(--edge-surface, #ffffff); margin: 20px;">
    <div style="color: var(--edge-danger, #ff4d4f); font-weight: bold; font-size: 1.2rem; margin-bottom: 12px;">
      EdgeSuite UI failed to load
    </div>
    <div style="color: var(--edge-text-muted, #8c8c8c); margin-bottom: 20px; font-size: 14px;">
      Required EdgeSuite shell components could not be resolved from window.EdgeUI.components.
    </div>
    <div v-if="missingComponents.length" style="color: var(--edge-text, #172033); margin-bottom: 20px; font-size: 13px;">
      Missing components: {{ missingComponents.join(', ') }}
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
        <div class="edge-filter-grid">
        <div class="edge-field filter-group">
          <label class="edge-field-label filter-label">Warehouse</label>
          <select v-model="filters.warehouse" class="edge-select filter-select" :disabled="metadataLoading" @change="fetchData">
            <option value="">All Warehouses</option>
            <option v-for="w in warehouses" :key="w" :value="w">{{ w }}</option>
          </select>
        </div>
        <div class="edge-field filter-group">
          <label class="edge-field-label filter-label">Item Group</label>
          <select v-model="filters.item_group" class="edge-select filter-select" :disabled="metadataLoading" @change="fetchData">
            <option value="">All Item Groups</option>
            <option v-for="g in itemGroups" :key="g" :value="g">{{ g }}</option>
          </select>
        </div>
        <div class="edge-field filter-group">
          <label class="edge-field-label filter-label">Expiry Window</label>
          <select v-model="filters.expiry_window" class="edge-select filter-select" :disabled="metadataLoading" @change="fetchData">
            <option value="all">All Inventory</option>
            <option value="expired">Expired Batches</option>
            <option value="expiring soon">Expiring Soon</option>
          </select>
        </div>
        <div class="edge-field filter-group">
          <label class="edge-field-label filter-label">Days Threshold</label>
          <select v-model="filters.days_threshold" class="edge-select filter-select" :disabled="metadataLoading" @change="fetchData">
            <option :value="30">30 Days</option>
            <option :value="60">60 Days</option>
            <option :value="90">90 Days</option>
            <option :value="180">180 Days</option>
          </select>
        </div>
        <div class="edge-field filter-group">
          <label class="edge-field-label filter-label">Item Code</label>
          <input type="text" v-model="filters.item" placeholder="Enter Item Code" class="edge-input filter-input" :disabled="metadataLoading" @change="fetchData" />
        </div>
        <div class="edge-field filter-group filter-action-group">
          <label class="edge-field-label filter-label" style="visibility: hidden;">Action</label>
          <button class="edge-primary-button filter-btn primary" :disabled="metadataLoading || loading" @click="fetchData">
            Apply / Refresh
          </button>
        </div>
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
        <div class="edge-stat-grid summary-stats-grid">
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
        <div v-if="rows.length > 0" class="edge-table-card table-container-card">
          <div class="table-responsive">
            <table class="edge-dashboard-table dashboard-table">
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
import { h } from 'vue';

const requiredEdgeUIComponents = ['EdgeAppShell', 'EdgePageLayout', 'EdgeFilterBar', 'EdgeStatCard', 'EdgeStatusBadge', 'EdgeLoadingState', 'EdgeEmptyState', 'EdgeErrorState', 'EdgeNotificationBell', 'EdgeNotificationDrawer'];
const notificationApi = {
  feed: 'vetedge.services.notification_api.get_my_edgesuite_notifications',
  markRead: 'vetedge.services.notification_api.mark_my_edgesuite_notification_read',
  markAllRead: 'vetedge.services.notification_api.mark_all_my_notifications_read',
  acknowledge: 'vetedge.services.notification_api.acknowledge_my_notification',
  done: 'vetedge.services.notification_api.mark_my_notification_done',
  dismiss: 'vetedge.services.notification_api.dismiss_my_notification'
};

const EdgeAppShell = {
  name: 'EdgeAppShell',
  props: ['product', 'menuItems', 'activeRoute', 'title', 'tenantName', 'branchName', 'userName'],
  emits: ['navigate'],
  render() {
    const menu = (this.menuItems || []).map((item) =>
      h('button', {
        class: ['edge-sidebar-item', item.route === this.activeRoute ? 'active' : ''],
        type: 'button',
        onClick: () => this.$emit('navigate', item.route)
      }, [h('span', { class: 'edge-sidebar-icon' }, item.icon || ''), h('span', item.label || '')])
    );
    const context = [this.tenantName, this.branchName, this.userName].filter(Boolean).join(' · ');
    return h('div', { class: 'edge-app-shell', 'data-edge-product': this.product }, [
      h('div', { class: 'edge-topbar' }, [
        h('div', { class: 'edge-topbar-title' }, this.title || ''),
        h('div', { class: 'edge-topbar-context' }, context),
        h('div', { class: 'edge-topbar-actions' }, this.$slots.notifications ? this.$slots.notifications() : [])
      ]),
      h('div', { class: 'edge-shell-body' }, [
        h('aside', { class: 'edge-sidebar' }, menu),
        h('main', { class: 'edge-shell-main' }, this.$slots.default ? this.$slots.default() : [])
      ])
    ]);
  }
};

const EdgePageLayout = {
  name: 'EdgePageLayout',
  render() {
    return h('section', { class: 'edge-page-layout' }, [
      this.$slots.header ? h('div', { class: 'edge-page-layout-header' }, this.$slots.header()) : null,
      h('div', { class: 'edge-page-layout-body' }, this.$slots.default ? this.$slots.default() : [])
    ]);
  }
};

const EdgePageHeader = {
  name: 'EdgePageHeader',
  props: ['title', 'subtitle'],
  render() {
    return h('div', { class: 'edge-page-header' }, [
      h('h1', { class: 'edge-page-title' }, this.title || ''),
      this.subtitle ? h('p', { class: 'edge-page-subtitle' }, this.subtitle) : null
    ]);
  }
};

const EdgeFilterBar = {
  name: 'EdgeFilterBar',
  props: ['title'],
  render() {
    return h('section', { class: 'edge-filter-bar' }, [
      this.title ? h('h2', { class: 'edge-filter-title' }, this.title) : null,
      h('div', { class: 'edge-filter-body' }, this.$slots.default ? this.$slots.default() : [])
    ]);
  }
};

const EdgeStatCard = {
  name: 'EdgeStatCard',
  props: ['label', 'value', 'icon', 'tooltip'],
  render() {
    return h('div', { class: 'edge-stat-card', title: this.tooltip || '' }, [
      h('div', { class: 'edge-stat-icon' }, this.icon || ''),
      h('div', { class: 'edge-stat-content' }, [
        h('div', { class: 'edge-stat-label' }, this.label || ''),
        h('div', { class: 'edge-stat-value' }, String(this.value ?? ''))
      ])
    ]);
  }
};

const EdgeStatusBadge = {
  name: 'EdgeStatusBadge',
  props: ['label', 'status'],
  render() {
    const status = String(this.status || this.label || '').toLowerCase().replace(/\s+/g, '-');
    return h('span', { class: ['edge-status-badge', `edge-status-${status}`] }, this.label || this.status || '');
  }
};

const EdgeEmptyState = {
  name: 'EdgeEmptyState',
  props: ['title', 'description', 'icon'],
  render() {
    return h('div', { class: 'edge-empty-state' }, [
      h('div', { class: 'edge-empty-icon' }, this.icon || ''),
      h('h3', this.title || ''),
      h('p', this.description || '')
    ]);
  }
};

const EdgeLoadingState = {
  name: 'EdgeLoadingState',
  props: ['message', 'skeleton'],
  render() {
    return h('div', { class: ['edge-loading-state', this.skeleton ? 'with-skeleton' : ''] }, [
      h('div', { class: 'edge-loading-spinner' }),
      h('p', this.message || 'Loading...')
    ]);
  }
};

const EdgeErrorState = {
  name: 'EdgeErrorState',
  props: ['title', 'message'],
  emits: ['retry'],
  render() {
    return h('div', { class: 'edge-error-state' }, [
      h('h3', this.title || 'Error'),
      h('p', this.message || ''),
      h('button', { class: 'edge-primary-button', type: 'button', onClick: () => this.$emit('retry') }, 'Retry')
    ]);
  }
};

const EdgeNotificationBell = {
  name: 'EdgeNotificationBell',
  props: ['unreadCount', 'title'],
  emits: ['toggle'],
  render() {
    return h('button', { class: 'edge-notification-bell', type: 'button', title: this.title || 'Notifications', onClick: () => this.$emit('toggle') }, [
      h('span', 'Notifications'),
      this.unreadCount ? h('span', { class: 'edge-notification-count' }, String(this.unreadCount)) : null
    ]);
  }
};

const EdgeNotificationDrawer = {
  name: 'EdgeNotificationDrawer',
  props: ['product', 'title', 'open', 'notifications', 'unreadCount', 'filter', 'loading', 'error'],
  emits: ['close', 'update:filter', 'retry', 'refresh', 'mark-all-read', 'action', 'open'],
  render() {
    if (!this.open) return null;
    const filters = ['all', 'unread', 'action_required', 'done'].map((filter) =>
      h('button', {
        class: ['edge-notification-filter', this.filter === filter ? 'active' : ''],
        type: 'button',
        onClick: () => this.$emit('update:filter', filter)
      }, filter.replace('_', ' '))
    );
    const items = (this.notifications || []).map((item) =>
      h('article', { class: ['edge-notification-item', item.severity || '', item.status || ''] }, [
        h('button', { class: 'edge-notification-title', type: 'button', onClick: () => this.$emit('open', item) }, item.title || item.name || 'Notification'),
        h('p', { class: 'edge-notification-message' }, item.message || ''),
        h('div', { class: 'edge-notification-meta' }, [item.category, item.status, item.created_at].filter(Boolean).join(' · ')),
        h('div', { class: 'edge-notification-actions' }, (item.actions || []).map((action) =>
          h('button', {
            type: 'button',
            disabled: action.enabled === false,
            onClick: () => this.$emit('action', { notification: item, action })
          }, action.label || action.key)
        ))
      ])
    );
    return h('div', { class: 'edge-notification-drawer-backdrop' }, [
      h('aside', { class: 'edge-notification-drawer', 'data-edge-product': this.product }, [
        h('header', { class: 'edge-notification-header' }, [
          h('div', [h('h2', this.title || 'Notifications'), h('span', `${this.unreadCount || 0} unread`)]),
          h('button', { type: 'button', onClick: () => this.$emit('close') }, 'Close')
        ]),
        h('div', { class: 'edge-notification-toolbar' }, [
          ...filters,
          h('button', { type: 'button', onClick: () => this.$emit('refresh') }, 'Refresh'),
          h('button', { type: 'button', onClick: () => this.$emit('mark-all-read') }, 'Mark all read')
        ]),
        this.error ? h('div', { class: 'edge-error-state' }, [
          h('p', this.error),
          h('button', { type: 'button', onClick: () => this.$emit('retry') }, 'Retry')
        ]) : null,
        this.loading ? h('div', { class: 'edge-loading-state' }, 'Loading notifications...') : null,
        !this.loading && !this.error && !items.length ? h('div', { class: 'edge-empty-state' }, 'No notifications') : null,
        h('div', { class: 'edge-notification-list' }, items)
      ])
    ]);
  }
};

const localEdgeUIComponents = {
  EdgeAppShell,
  EdgePageLayout,
  EdgePageHeader,
  EdgeFilterBar,
  EdgeStatCard,
  EdgeStatusBadge,
  EdgeEmptyState,
  EdgeLoadingState,
  EdgeErrorState,
  EdgeNotificationBell,
  EdgeNotificationDrawer
};

export default {
  name: 'VetedgeStockExpiryMonitor',
  components: localEdgeUIComponents,
  data() {
    return {
      edgeUIValid: true,
      missingComponents: [],
      metadataLoading: true,
      loading: true,
      error: '',
      summary: {},
      rows: [],
      totalCount: 0,
      notificationDrawerOpen: false,
      notificationLoading: false,
      notificationError: '',
      notificationFilter: 'all',
      notificationItems: [],
      notificationUnreadCount: 0,
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
    this.missingComponents = requiredEdgeUIComponents.filter((name) => !localEdgeUIComponents[name]);
    this.edgeUIValid = this.missingComponents.length === 0;
  },
  mounted() {
    this.fetchMetadata();
    this.fetchData();
    this.fetchNotifications();
  },
  computed: {
    filteredNotifications() {
      if (this.notificationFilter === 'unread') {
        return this.notificationItems.filter((item) => item.status === 'Unread');
      }
      if (this.notificationFilter === 'action_required') {
        return this.notificationItems.filter((item) => (item.actions || []).length > 0);
      }
      if (this.notificationFilter === 'done') {
        return this.notificationItems.filter((item) => ['Done', 'Dismissed', 'Archived'].includes(item.status));
      }
      return this.notificationItems;
    }
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
    callFrappe(method, args) {
      return new Promise((resolve, reject) => {
        if (typeof frappe === 'undefined' || !frappe.call) {
          reject(new Error('Frappe Desk is not ready.'));
          return;
        }
        frappe.call({
          method,
          args: args || {},
          callback: (response) => resolve((response && response.message) || {}),
          error: (error) => reject(error)
        });
      });
    },
    toggleNotificationDrawer() {
      this.notificationDrawerOpen = !this.notificationDrawerOpen;
      if (this.notificationDrawerOpen) {
        this.fetchNotifications();
      }
    },
    setNotificationFilter(filterKey) {
      this.notificationFilter = filterKey;
      this.fetchNotifications();
    },
    fetchNotifications() {
      if (typeof frappe === 'undefined') {
        return;
      }
      this.notificationLoading = true;
      this.notificationError = '';
      this.callFrappe(notificationApi.feed, { filter_key: this.notificationFilter, limit: 30 })
        .then((message) => {
          this.notificationItems = message.items || [];
          this.notificationUnreadCount = Number(message.unread_count || 0);
        })
        .catch((error) => {
          this.notificationError = error.message || 'Notifications could not be loaded.';
        })
        .finally(() => {
          this.notificationLoading = false;
        });
    },
    runNotificationAction(payload) {
      const action = payload && payload.action;
      const notification = payload && payload.notification;
      if (!action || !notification || !notification.name) {
        return;
      }
      const methodByAction = {
        mark_read: notificationApi.markRead,
        acknowledge: notificationApi.acknowledge,
        done: notificationApi.done,
        dismiss: notificationApi.dismiss
      };
      const method = methodByAction[action.key];
      if (!method) {
        return;
      }
      this.notificationLoading = true;
      this.callFrappe(method, { notification_name: notification.name })
        .then((message) => {
          this.notificationUnreadCount = Number(message.unread_count || this.notificationUnreadCount || 0);
          return this.fetchNotifications();
        })
        .catch((error) => {
          this.notificationError = error.message || 'Notification action failed.';
        })
        .finally(() => {
          this.notificationLoading = false;
        });
    },
    markAllNotificationsRead() {
      this.notificationLoading = true;
      this.callFrappe(notificationApi.markAllRead)
        .then((message) => {
          this.notificationUnreadCount = Number(message.unread_count || 0);
          return this.fetchNotifications();
        })
        .catch((error) => {
          this.notificationError = error.message || 'Could not mark notifications read.';
        })
        .finally(() => {
          this.notificationLoading = false;
        });
    },
    openNotificationRoute(notification) {
      if (!notification || !notification.route || typeof frappe === 'undefined' || !frappe.set_route) {
        return;
      }
      const route = notification.route.replace(/^\/app\//, '').split('/').filter(Boolean).map(decodeURIComponent);
      frappe.set_route(route);
      this.notificationDrawerOpen = false;
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
.edge-filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--edge-space-md, 16px);
  align-items: end;
}

.edge-field {
  min-width: 0;
}

.edge-field-label {
  color: var(--edge-muted-text, var(--edge-text-muted));
}

.edge-input,
.edge-select {
  min-height: 38px;
  border-color: var(--edge-border);
  border-radius: var(--edge-radius, var(--edge-radius-md));
  background: var(--edge-surface);
  color: var(--edge-text);
}

.edge-primary-button {
  background: var(--edge-primary);
  color: #fff;
  border-radius: var(--edge-radius, var(--edge-radius-md));
}

.edge-primary-button:hover:not(:disabled) {
  background: var(--edge-primary-hover, var(--edge-primary));
}

.edge-stat-grid {
  width: 100%;
}

.edge-table-card {
  background: var(--edge-surface);
  border: 1px solid var(--edge-border);
  border-radius: var(--edge-radius, var(--edge-radius-lg));
  box-shadow: var(--edge-shadow, var(--edge-shadow-sm));
}

.edge-dashboard-table {
  color: var(--edge-text);
}

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
