<template>
	<div class="vetedge-suite-shell" data-edge-product="vetedge">
		<header class="vetedge-suite-context-bar">
			<div class="vetedge-suite-context-leading">
				<button
					ref="launcherButton"
					type="button"
					class="vetedge-suite-icon-button"
					:aria-expanded="menuOpen ? 'true' : 'false'"
					aria-haspopup="dialog"
					aria-label="Open VetEdge application menu"
					@click="toggleMenu"
				>
					<svg class="vetedge-suite-waffle-icon" viewBox="0 0 20 20" aria-hidden="true">
						<circle v-for="point in wafflePoints" :key="point" :cx="point.split(',')[0]" :cy="point.split(',')[1]" r="1.55" />
					</svg>
				</button>
				<div class="vetedge-suite-context" aria-label="Current VetEdge context">
					<strong>{{ company || 'Veterinary' }}</strong>
					<span aria-hidden="true">·</span>
					<span>{{ branch || 'All Branches' }}</span>
					<span aria-hidden="true">·</span>
					<span>{{ user || 'Veterinary User' }}</span>
				</div>
			</div>
			<div class="vetedge-suite-context-actions">
				<EdgeNotificationBell
					:unreadCount="unreadCount"
					title="Notifications"
					@toggle="$emit('toggle-notifications')"
				>
					<template #icon><span class="vetedge-notification-icon" aria-hidden="true">🔔</span></template>
				</EdgeNotificationBell>
				<EdgeNotificationDrawer
					product="vetedge"
					title="Notifications"
					:open="notificationOpen"
					:notifications="notifications"
					:unreadCount="unreadCount"
					:filter="notificationFilter"
					:loading="notificationLoading"
					:error="notificationError"
					@close="$emit('close-notifications')"
					@update:filter="$emit('update-notification-filter', $event)"
					@retry="$emit('refresh-notifications')"
					@refresh="$emit('refresh-notifications')"
					@mark-all-read="$emit('mark-all-read')"
					@action="$emit('notification-action', $event)"
					@open="$emit('open-notification', $event)"
				/>
			</div>
		</header>

		<main class="vetedge-suite-content">
			<slot />
		</main>

		<div v-if="menuOpen" class="vetedge-mega-menu-backdrop" @mousedown.self="closeMenu">
			<section
				ref="menuPanel"
				class="vetedge-mega-menu"
				role="dialog"
				aria-modal="true"
				aria-label="VetEdge application menu"
				@keydown="handleMenuKeydown"
			>
				<aside class="vetedge-mega-account">
					<div class="vetedge-mega-brand">
						<div class="vetedge-mega-logo">V</div>
						<div><strong>VetEdge</strong><small>Veterinary operations</small></div>
					</div>
					<div class="vetedge-mega-profile">
						<div class="vetedge-mega-avatar">{{ initials }}</div>
						<div><strong>{{ user || 'Veterinary User' }}</strong><small>{{ roleLabel }}</small><small>{{ email }}</small></div>
					</div>
					<div class="vetedge-mega-context-card">
						<label>Company</label><strong>{{ company || 'Veterinary' }}</strong>
						<label>Branch</label><strong>{{ branch || 'All Branches' }}</strong>
					</div>
					<div class="vetedge-mega-product-card">
						<span>Current product</span><strong>VetEdge</strong><small>{{ planLabel }}</small>
					</div>
					<nav class="vetedge-mega-account-links" aria-label="Account actions">
						<button v-for="item in accountItems" :key="item.label" type="button" @click="activate(item)">{{ item.label }}</button>
					</nav>
					<div class="vetedge-mega-status"><span></span>EdgeSuite available</div>
				</aside>

				<div class="vetedge-mega-main">
					<header class="vetedge-mega-heading">
						<div><span>EdgeSuite application map</span><h2>Veterinary workspace</h2></div>
						<button ref="closeButton" type="button" class="vetedge-mega-close" aria-label="Close application menu" @click="closeMenu">×</button>
					</header>
					<div class="vetedge-mega-grid">
						<section v-for="section in menuSections" :key="section.label" class="vetedge-mega-section">
							<h3>{{ section.label }}</h3>
							<button
								v-for="item in section.items"
								:key="item.label"
								type="button"
								:class="['vetedge-mega-link', { 'is-active': isActive(item) }]"
								@click="activate(item)"
							>
								<span class="vetedge-mega-link-icon" aria-hidden="true">{{ item.icon || '•' }}</span>
								<span>{{ item.label }}</span>
							</button>
						</section>
					</div>
					<footer class="vetedge-mega-footer">
						<span>VetEdge by ProcessEdge Solutions</span>
						<span>© {{ currentYear }} · EdgeSuite connected</span>
					</footer>
				</div>
			</section>
		</div>
	</div>
</template>

<script>
const configuredSections = [
	{ label: 'Dashboards', items: [
		{ label: 'Executive Dashboard', icon: '◫', link_type: 'Page', link_to: 'vetedge-executive-dashboard' },
		{ label: 'Financial Dashboard', icon: '◩', link_type: 'Page', link_to: 'veterinary-financial-dashboard' },
		{ label: 'Clinical Dashboard', icon: '✚', link_type: 'Page', link_to: 'veterinary-clinical-dashboard' }
	]},
	{ label: 'Veterinary Records', items: [
		{ label: 'Patients', icon: 'P', link_type: 'DocType', link_to: 'Veterinary Patient' },
		{ label: 'Owners', icon: 'O', link_type: 'DocType', link_to: 'Customer' },
		{ label: 'Appointments', icon: 'A', link_type: 'DocType', link_to: 'Veterinary Appointment' },
		{ label: 'Consultations', icon: 'C', link_type: 'DocType', link_to: 'Veterinary Consultation' },
		{ label: 'Vaccinations', icon: 'V', link_type: 'DocType', link_to: 'Veterinary Vaccination' },
		{ label: 'Laboratory', icon: 'L', link_type: 'DocType', link_to: 'Veterinary Lab Test' },
		{ label: 'Medical History', icon: 'M', link_type: 'Report', link_to: 'Veterinary Medical History' }
	]},
	{ label: 'Clinical Operations', items: [
		{ label: 'Treatment Plans', icon: 'T', link_type: 'DocType', link_to: 'Veterinary Treatment Plan' },
		{ label: 'Hospitalisation', icon: 'H', link_type: 'DocType', link_to: 'Veterinary Hospitalisation' },
		{ label: 'Procedures', icon: 'P', link_type: 'DocType', link_to: 'Veterinary Procedure' },
		{ label: 'Dispensary', icon: 'D', link_type: 'Page', link_to: 'vetedge-dispensary' },
		{ label: 'Missed Appointments', icon: '!', link_type: 'Report', link_to: 'Missed Veterinary Appointments' }
	]},
	{ label: 'Services', items: [
		{ label: 'Grooming', icon: 'G', link_type: 'DocType', link_to: 'Pet Grooming Booking' },
		{ label: 'Boarding', icon: 'B', link_type: 'DocType', link_to: 'Pet Boarding Booking' },
		{ label: 'House Calls', icon: 'H', link_type: 'DocType', link_to: 'Veterinary House Call' }
	]},
	{ label: 'Billing & Payments', items: [
		{ label: 'Billing Sessions', icon: 'B', link_type: 'DocType', link_to: 'Veterinary Billing Session' },
		{ label: 'Sales Invoices', icon: 'S', link_type: 'DocType', link_to: 'Sales Invoice' },
		{ label: 'Payments', icon: 'P', link_type: 'DocType', link_to: 'Payment Entry' },
		{ label: 'Outstanding Invoices', icon: 'O', link_type: 'Report', link_to: 'Accounts Receivable' }
	]},
	{ label: 'Inventory & Pharmacy', items: [
		{ label: 'Items', icon: 'I', link_type: 'DocType', link_to: 'Item' },
		{ label: 'Stock', icon: 'S', link_type: 'Report', link_to: 'Stock Balance' },
		{ label: 'Expiry Monitor', icon: 'E', link_type: 'Page', link_to: 'stock-expiry-monitor' },
		{ label: 'Warehouses', icon: 'W', link_type: 'DocType', link_to: 'Warehouse' }
	]},
	{ label: 'Reports', items: [
		{ label: 'Clinical Reports', icon: 'C', link_type: 'Workspace', link_to: 'Veterinary Clinical Reports' },
		{ label: 'Appointment Reports', icon: 'A', link_type: 'Workspace', link_to: 'Veterinary Appointment Reports' },
		{ label: 'Financial Reports', icon: 'F', link_type: 'Workspace', link_to: 'Veterinary Financial Reports' },
		{ label: 'Inventory Reports', icon: 'I', link_type: 'Workspace', link_to: 'Veterinary Inventory Reports' },
		{ label: 'Management Reports', icon: 'M', link_type: 'Workspace', link_to: 'Veterinary Management Reports' }
	]},
	{ label: 'Setup', items: [
		{ label: 'Veterinary Settings', icon: 'S', link_type: 'DocType', link_to: 'Veterinary Settings' },
		{ label: 'Consultation Types', icon: 'C', link_type: 'DocType', link_to: 'Veterinary Consultation Type' },
		{ label: 'Branches', icon: 'B', link_type: 'DocType', link_to: 'Branch' },
		{ label: 'Practitioners', icon: 'P', link_type: 'DocType', link_to: 'Healthcare Practitioner' },
		{ label: 'Care Locations', icon: 'L', link_type: 'DocType', link_to: 'Healthcare Service Unit' },
		{ label: 'Notification Settings', icon: 'N', link_type: 'DocType', link_to: 'Veterinary Notification Settings' }
	]}
];

export default {
	name: 'VetedgeEdgeSuiteShell',
	props: {
		company: { type: String, default: '' },
		branch: { type: String, default: 'All Branches' },
		user: { type: String, default: '' },
		notificationOpen: { type: Boolean, default: false },
		notifications: { type: Array, default: () => [] },
		unreadCount: { type: Number, default: 0 },
		notificationFilter: { type: String, default: 'all' },
		notificationLoading: { type: Boolean, default: false },
		notificationError: { type: String, default: '' }
	},
	emits: ['toggle-notifications', 'close-notifications', 'update-notification-filter', 'refresh-notifications', 'mark-all-read', 'notification-action', 'open-notification'],
	data() {
		return {
			menuOpen: false,
			menuSections: configuredSections,
			wafflePoints: ['4,4', '10,4', '16,4', '4,10', '10,10', '16,10', '4,16', '10,16', '16,16'],
			currentYear: new Date().getFullYear()
		};
	},
	computed: {
		initials() {
			return String(this.user || 'V').split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
		},
		email() {
			return window.frappe?.session?.user || '';
		},
		roleLabel() {
			return window.frappe?.boot?.user?.designation || window.frappe?.boot?.user?.role_profile_name || 'Veterinary user';
		},
		planLabel() {
			return window.frappe?.boot?.subscription?.plan_name || window.frappe?.boot?.edgesuite_plan || 'Active workspace';
		},
		accountItems() {
			return [
				{ label: 'My Profile', link_type: 'Form', link_to: 'User/' + (window.frappe?.session?.user || '') },
				{ label: 'My Preferences', link_type: 'Form', link_to: 'User/' + (window.frappe?.session?.user || '') },
				{ label: 'Change Password', action: 'change-password' },
				{ label: 'Logout', action: 'logout' }
			];
		}
	},
	mounted() {
		window.VetedgeProductMenu?.setInlineMode?.(true);
		const hydrated = window.VetedgeProductMenu?.getSections?.();
		if (hydrated?.length) this.menuSections = hydrated;
	},
	beforeUnmount() {
		window.VetedgeProductMenu?.setInlineMode?.(false);
	},
	methods: {
		toggleMenu() {
			this.menuOpen ? this.closeMenu() : this.openMenu();
		},
		openMenu() {
			this.menuOpen = true;
			this.$nextTick(() => this.$refs.closeButton?.focus());
		},
		closeMenu() {
			this.menuOpen = false;
			this.$nextTick(() => this.$refs.launcherButton?.focus());
		},
		isActive(item) {
			const route = (window.frappe?.get_route?.() || []).join('/').toLowerCase();
			const target = String(item.link_to || '').toLowerCase();
			return Boolean(target) && (route === target || route.endsWith('/' + target));
		},
		handleMenuKeydown(event) {
			if (event.key === 'Escape') {
				event.preventDefault();
				this.closeMenu();
			}
		},
		activate(item) {
			if (item.action === 'logout') {
				window.frappe?.app?.logout?.();
				return;
			}
			if (item.action === 'change-password') {
				window.frappe?.set_route?.('update-password');
				this.closeMenu();
				return;
			}
			window.VetedgeProductMenu?.navigate?.(item);
			this.closeMenu();
		}
	}
};
</script>

<style>
.vetedge-suite-shell { position: relative; display: flex; flex: 1 1 auto; flex-direction: column; width: 100%; max-width: none; min-width: 0; box-sizing: border-box; background: var(--edge-bg, #f6f9fc); color: var(--edge-text, #172033); }
.vetedge-suite-context-bar { position: relative; z-index: 20; display: flex; align-items: center; justify-content: space-between; min-height: 52px; padding: 8px 24px; border-bottom: 1px solid var(--edge-border, #dbe4f0); background: rgba(255,255,255,.96); }
.vetedge-suite-context-leading, .vetedge-suite-context-actions, .vetedge-suite-context { display: flex; align-items: center; min-width: 0; }
.vetedge-suite-context-leading { gap: 10px; }
.vetedge-suite-context { gap: 8px; color: var(--edge-text-muted, #667085); font-size: 13px; white-space: nowrap; }
.vetedge-suite-context strong { overflow: hidden; max-width: 260px; color: var(--edge-text, #172033); text-overflow: ellipsis; }
.vetedge-suite-icon-button { display: inline-grid; place-items: center; width: 34px; height: 34px; min-width: 34px; padding: 0; border: 1px solid transparent; border-radius: 8px; background: var(--control-bg, #f3f4f6); color: var(--edge-text, #172033); cursor: pointer; }
.vetedge-suite-icon-button:hover { border-color: var(--edge-primary-soft, #cfe2ff); background: var(--edge-primary-soft, #e8f2ff); color: var(--edge-primary, #1677ff); }
.vetedge-suite-waffle-icon { width: 18px; height: 18px; fill: currentColor; }
.vetedge-suite-content { display: flex; flex: 1 1 auto; width: 100%; max-width: none; min-width: 0; box-sizing: border-box; }
.vetedge-suite-content > * { flex: 1 1 auto; width: 100%; max-width: none; min-width: 0; box-sizing: border-box; }
.vetedge-mega-menu-backdrop { position: fixed; inset: 0; z-index: 1090; padding: 64px 20px 20px; background: rgba(15,23,42,.28); }
.vetedge-mega-menu { display: grid; grid-template-columns: minmax(230px, 280px) minmax(0, 1fr); width: min(1180px, calc(100vw - 40px)); max-height: calc(100vh - 84px); margin: 0 auto; overflow: hidden; border: 1px solid var(--edge-border, #dbe4f0); border-radius: 16px; background: #fff; box-shadow: 0 24px 64px rgba(15,23,42,.24); }
.vetedge-mega-account { display: flex; flex-direction: column; gap: 16px; overflow-y: auto; padding: 22px; border-right: 1px solid var(--edge-border, #dbe4f0); background: linear-gradient(180deg, #eef6ff, #f8fbff); }
.vetedge-mega-brand, .vetedge-mega-profile { display: flex; align-items: center; gap: 10px; }
.vetedge-mega-logo, .vetedge-mega-avatar { display: grid; place-items: center; flex: 0 0 auto; border-radius: 10px; background: var(--edge-primary, #1677ff); color: #fff; font-weight: 700; }
.vetedge-mega-logo { width: 38px; height: 38px; }.vetedge-mega-avatar { width: 44px; height: 44px; border-radius: 50%; }
.vetedge-mega-brand div, .vetedge-mega-profile div { display: grid; min-width: 0; }.vetedge-mega-brand small, .vetedge-mega-profile small { overflow: hidden; color: var(--edge-text-muted, #667085); font-size: 12px; text-overflow: ellipsis; }
.vetedge-mega-context-card, .vetedge-mega-product-card { display: grid; gap: 4px; padding: 12px; border: 1px solid var(--edge-border, #dbe4f0); border-radius: 10px; background: rgba(255,255,255,.82); }
.vetedge-mega-context-card label, .vetedge-mega-product-card span { color: var(--edge-text-muted, #667085); font-size: 11px; }.vetedge-mega-context-card strong { margin-bottom: 6px; font-size: 13px; }
.vetedge-mega-product-card { border-color: var(--edge-primary-soft, #cfe2ff); }.vetedge-mega-product-card strong { color: var(--edge-primary, #1677ff); font-size: 18px; }.vetedge-mega-product-card small { color: var(--edge-text-muted, #667085); }
.vetedge-mega-account-links { display: grid; gap: 3px; }.vetedge-mega-account-links button, .vetedge-mega-link { border: 0; border-radius: 8px; background: transparent; color: var(--edge-text, #172033); text-align: left; cursor: pointer; }
.vetedge-mega-account-links button { padding: 8px 10px; }.vetedge-mega-account-links button:hover, .vetedge-mega-link:hover { background: var(--edge-primary-soft, #e8f2ff); color: var(--edge-primary, #1677ff); }
.vetedge-mega-status { display: flex; align-items: center; gap: 7px; margin-top: auto; color: var(--edge-text-muted, #667085); font-size: 12px; }.vetedge-mega-status span { width: 8px; height: 8px; border-radius: 50%; background: var(--edge-success, #16a34a); }
.vetedge-mega-main { display: flex; min-width: 0; flex-direction: column; overflow: hidden; }
.vetedge-mega-heading { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px 12px; }.vetedge-mega-heading span { color: var(--edge-primary, #1677ff); font-size: 12px; font-weight: 600; }.vetedge-mega-heading h2 { margin: 3px 0 0; font-size: 18px; }.vetedge-mega-close { width: 32px; height: 32px; border: 0; border-radius: 8px; background: var(--control-bg, #f3f4f6); font-size: 22px; cursor: pointer; }
.vetedge-mega-grid { display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 22px 18px; overflow-y: auto; padding: 12px 22px 24px; }
.vetedge-mega-section h3 { margin: 0 0 7px; color: var(--edge-text-muted, #667085); font-size: 12px; font-weight: 700; }.vetedge-mega-link { display: grid; grid-template-columns: 24px minmax(0,1fr); align-items: center; width: 100%; min-height: 32px; padding: 5px 6px; font-size: 13px; }
.vetedge-mega-link-icon { display: grid; place-items: center; width: 20px; height: 20px; border-radius: 6px; background: var(--control-bg, #f3f4f6); color: var(--edge-primary, #1677ff); font-size: 10px; font-weight: 700; }.vetedge-mega-link.is-active { background: var(--edge-primary-soft, #e8f2ff); color: var(--edge-primary, #1677ff); font-weight: 600; }
.vetedge-mega-footer { display: flex; justify-content: space-between; gap: 12px; padding: 12px 22px; border-top: 1px solid var(--edge-border, #dbe4f0); color: var(--edge-text-muted, #667085); font-size: 11px; }
@media (max-width: 980px) { .vetedge-mega-grid { grid-template-columns: repeat(3, minmax(140px, 1fr)); }.vetedge-suite-context-bar { padding: 8px 18px; } }
@media (max-width: 760px) { .vetedge-mega-menu-backdrop { padding: 52px 8px 8px; }.vetedge-mega-menu { grid-template-columns: 1fr; width: calc(100vw - 16px); max-height: calc(100vh - 60px); }.vetedge-mega-account { display: none; }.vetedge-mega-grid { grid-template-columns: repeat(2, minmax(130px, 1fr)); }.vetedge-suite-context { gap: 5px; font-size: 12px; }.vetedge-suite-context strong { max-width: 130px; } }
@media (max-width: 520px) { .vetedge-suite-context-bar { padding: 7px 12px; }.vetedge-suite-context span:nth-of-type(2), .vetedge-suite-context span:nth-of-type(3) { display: none; }.vetedge-mega-grid { grid-template-columns: 1fr; }.vetedge-mega-footer { flex-direction: column; } }
</style>
