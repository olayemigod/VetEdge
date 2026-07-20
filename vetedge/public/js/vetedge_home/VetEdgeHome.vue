<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="context.tenant_name || ''"
		:branch-name="context.active_label || ''"
		:user-name="context.user?.full_name || ''"
		:menu-items="context.menu_items || []"
		active-route="/app/vetedge-home"
		:hide-native-sidebar="true"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Veterinary Practice Management"
					title="Veterinary Operations"
					subtitle="Appointments, clinical care, laboratory, pharmacy, services, billing, and branch performance in one working context."
					action-label="New Appointment"
					@action="openRoute('/app/vetedge-resource-center?resource=appointments')"
				/>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading Veterinary operations..." :skeleton="true" />
			<EdgeErrorState v-else-if="error" title="Veterinary Home could not load" :message="error" action-label="Try again" @retry="loadContext" />
			<template v-else>
				<EdgeBranchContextSwitcher
					v-model="selectedBranch"
					:current-label="context.active_label || ''"
					:current-company="context.active_company || ''"
					:options="context.allowed_branches || []"
					:can-switch="context.can_switch_branch"
					:busy="switchingBranch"
					:required="true"
					label="Working branch"
					helper="Appointments, patient registration, practitioners, stock, billing defaults, dashboards, and reports use this branch until you switch again."
					@switch="switchBranch"
				/>

				<section v-if="context.requires_branch_selection" class="vetedge-home-attention">
					<strong>Select a configured working branch before starting Veterinary operations.</strong>
					<span>Each branch must have a Veterinary Company. Cost Center, Warehouse, and Price List defaults can also be configured on the Branch master.</span>
				</section>

				<section v-if="context.unconfigured_branch_count" class="vetedge-home-warning">
					<EdgeStatusBadge
						:label="`${context.unconfigured_branch_count} branch${context.unconfigured_branch_count === 1 ? '' : 'es'} need Veterinary Company setup`"
						status="warning"
						tone="warning"
					/>
					<button v-if="isAdministrator" type="button" class="edge-button" @click="openNative('/app/branch')">Configure Branches</button>
				</section>

				<section class="vetedge-home-context">
					<div>
						<p class="edge-eyebrow">Active working defaults</p>
						<strong>{{ context.active_label || "No branch selected" }}</strong>
						<span>{{ context.active_company || "No active company" }}</span>
					</div>
					<div class="vetedge-home-defaults">
						<EdgeStatusBadge :label="defaultLabel('Cost Center', context.active_defaults?.cost_center)" status="default" :tone="context.active_defaults?.cost_center ? 'success' : 'neutral'" />
						<EdgeStatusBadge :label="defaultLabel('Warehouse', context.active_defaults?.warehouse)" status="default" :tone="context.active_defaults?.warehouse ? 'success' : 'neutral'" />
						<EdgeStatusBadge :label="defaultLabel('Price List', context.active_defaults?.price_list)" status="default" :tone="context.active_defaults?.price_list ? 'success' : 'neutral'" />
					</div>
				</section>

				<EdgeDashboardLayout min-column-width="11.5rem">
					<EdgeStatCard label="Patients" :value="context.counts.patients" helper="Active patients registered to this branch" />
					<EdgeStatCard label="Today's Appointments" :value="context.counts.today_appointments" helper="Scheduled in the working branch" />
					<EdgeStatCard label="Active Consultations" :value="context.counts.active_consultations" helper="Clinical work in progress" />
					<EdgeStatCard label="Open Lab Orders" :value="context.counts.open_lab_orders" helper="Awaiting completion or review" />
					<EdgeStatCard label="Hospitalisations" :value="context.counts.active_hospitalisations" helper="Current inpatient care" />
					<EdgeStatCard label="Grooming" :value="context.counts.open_grooming" helper="Open grooming bookings" />
					<EdgeStatCard label="Boarding" :value="context.counts.open_boarding" helper="Open boarding bookings" />
					<EdgeStatCard label="Outstanding Invoices" :value="context.counts.outstanding_invoices" helper="Submitted invoices with balances" />
				</EdgeDashboardLayout>

				<section class="vetedge-home-grid">
					<article v-for="module in context.modules" :key="module.route" class="vetedge-home-module">
						<div>
							<p class="edge-eyebrow">{{ module.eyebrow }}</p>
							<h2>{{ module.title }}</h2>
							<p>{{ module.description }}</p>
						</div>
						<button type="button" class="edge-button edge-button--primary" @click="openModule(module)">{{ module.action }}</button>
					</article>
				</section>
			</template>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
function emptyContext() {
	return {
		tenant_name: "",
		user: { roles: [] },
		current_branch: null,
		allowed_branches: [],
		active_branch: "",
		active_company: "",
		active_label: "",
		active_defaults: {},
		can_switch_branch: false,
		requires_branch_selection: false,
		unconfigured_branch_count: 0,
		menu_items: [],
		modules: [],
		counts: {
			patients: 0, today_appointments: 0, active_consultations: 0, open_lab_orders: 0,
			active_hospitalisations: 0, open_grooming: 0, open_boarding: 0, outstanding_invoices: 0,
		},
	};
}

export default {
	name: "VetEdgeHome",
	data() {
		return { loading: true, switchingBranch: false, error: "", selectedBranch: "", context: emptyContext() };
	},
	computed: {
		isAdministrator() {
			const roles = new Set(this.context.user?.roles || []);
			return roles.has("System Manager") || roles.has("VetEdge Administrator");
		},
	},
	mounted() { this.loadContext(); },
	methods: {
		defaultLabel(label, value) { return value ? `${label}: ${value}` : `${label}: Not configured`; },
		menuItem(route) { return (this.context.menu_items || []).find((item) => item.route === route) || {}; },
		openRoute(route) {
			const item = this.menuItem(route);
			if (item.native) { this.openNative(route); return; }
			window.location.href = route;
		},
		openNative(route) {
			const opened = window.open(route, "_blank", "noopener,noreferrer");
			if (opened) opened.opener = null;
		},
		openModule(module) {
			if (module.native) this.openNative(module.route);
			else window.location.href = module.route;
		},
		async loadContext() {
			this.loading = true;
			this.error = "";
			try {
				const response = await frappe.call("vetedge.services.home.get_home_context");
				this.context = { ...emptyContext(), ...(response.message || {}) };
				this.selectedBranch = this.context.active_branch || "";
			} catch (error) {
				this.error = error?.message || __("Veterinary Home context could not be loaded.");
			} finally { this.loading = false; }
		},
		async switchBranch(option) {
			if (!option?.value || option.value === this.context.active_branch) return;
			this.switchingBranch = true;
			try {
				const response = await frappe.call("vetedge.services.branch_context.switch_veterinary_branch", { branch: option.value });
				const changed = response.message || {};
				window.dispatchEvent(new CustomEvent("edgesuite:branch-context-changed", { detail: changed }));
				frappe.show_alert({ message: __("Working branch changed to {0}", [changed.active_label || option.label]), indicator: "green" });
				await this.loadContext();
			} catch (error) {
				this.selectedBranch = this.context.active_branch || "";
				frappe.msgprint({ title: __("Unable to switch branch"), message: error?.message || __("The selected working branch could not be activated."), indicator: "red" });
			} finally { this.switchingBranch = false; }
		},
	},
};
</script>

<style scoped>
.vetedge-home-attention,.vetedge-home-warning,.vetedge-home-context{align-items:center;background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--edge-radius-lg,12px);display:flex;gap:1rem;justify-content:space-between;margin-top:1rem;padding:1rem}.vetedge-home-attention{align-items:flex-start;flex-direction:column}.vetedge-home-warning{background:color-mix(in srgb,var(--orange-500,#f59e0b) 6%,var(--card-bg))}.vetedge-home-context>div:first-child{display:grid;gap:.2rem}.vetedge-home-context span,.vetedge-home-module p{color:var(--text-muted)}.vetedge-home-defaults{align-items:center;display:flex;flex-wrap:wrap;gap:.5rem;justify-content:flex-end}.vetedge-home-grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(17rem,1fr));margin-top:1.25rem}.vetedge-home-module{background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--edge-radius-lg,12px);display:flex;flex-direction:column;gap:1rem;justify-content:space-between;min-height:13rem;padding:1.25rem}.vetedge-home-module h2{margin:.25rem 0 .5rem}@media(max-width:47.99rem){.vetedge-home-warning,.vetedge-home-context{align-items:flex-start;flex-direction:column}.vetedge-home-defaults{justify-content:flex-start}}
</style>
