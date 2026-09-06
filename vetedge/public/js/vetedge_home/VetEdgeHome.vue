<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/desk/vetedge"
		@navigate="openRoute"
	>
		<EdgePageLayout class="vetedge-home-page">
			<template #header>
				<EdgePageHeader
					eyebrow="Veterinary Operations"
					title="Veterinary Home"
					:subtitle="homeSubtitle"
					action-label="Refresh"
					@action="loadHome"
				/>
			</template>

			<EdgeLoadingState v-if="loading && !payload.metrics.length" message="Preparing your Veterinary action centre..." :skeleton="true" />
			<EdgeErrorState
				v-else-if="error && !payload.metrics.length"
				title="Veterinary Home could not load"
				:message="error"
				action-label="Try again"
				@retry="loadHome"
			/>

			<template v-else>
				<section class="vetedge-home-controls" aria-label="Veterinary Home operating context">
					<div class="vetedge-home-control">
						<label for="vetedge-home-branch">Working branch</label>
						<select id="vetedge-home-branch" v-model="selectedBranch" class="form-control input-sm" :disabled="loading" @change="applyContext">
							<option v-for="option in payload.context?.branch_options || []" :key="option.value" :value="option.value">
								{{ option.label }}{{ option.company ? ` · ${option.company}` : '' }}
							</option>
						</select>
					</div>
					<div class="vetedge-home-control">
						<label for="vetedge-home-date">Operational date</label>
						<input id="vetedge-home-date" v-model="selectedDate" class="form-control input-sm" type="date" :disabled="loading" @change="applyContext" />
					</div>
					<div class="vetedge-home-context-note">
						<strong>{{ branchName }}</strong>
						<span>Date-specific cards use {{ selectedDate || payload.context?.operational_date }}. Current/open-work cards remain live backlog.</span>
					</div>
				</section>

				<section class="vetedge-home-context" aria-label="Current access context">
					<div>
						<span class="vetedge-home-context-label">Working as</span>
						<strong>{{ primaryPersonaLabel }}</strong>
					</div>
					<div>
						<span class="vetedge-home-context-label">Branch scope</span>
						<strong>{{ branchName }}</strong>
					</div>
					<div>
						<span class="vetedge-home-context-label">Operational date</span>
						<strong>{{ payload.context?.operational_date || '' }}</strong>
					</div>
					<div v-if="secondaryPersonas.length">
						<span class="vetedge-home-context-label">Additional access</span>
						<strong>{{ secondaryPersonas.join(', ') }}</strong>
					</div>
				</section>

				<section class="vetedge-home-section" aria-labelledby="vetedge-home-attention-heading">
					<div class="vetedge-home-section-heading">
						<div>
							<span>Act first</span>
							<h2 id="vetedge-home-attention-heading">Needs Your Attention</h2>
						</div>
						<small>Each card opens the exact permission-safe records counted here</small>
					</div>

					<div v-if="payload.attention?.length" class="vetedge-home-attention-grid">
						<button
							v-for="item in payload.attention"
							:key="item.key"
							type="button"
							class="vetedge-home-attention-card"
							:class="`is-${item.tone || 'warning'}`"
							@click="openMetric(item.key)"
						>
							<span class="vetedge-home-attention-count">{{ item.count }}</span>
							<span class="vetedge-home-attention-copy">
								<strong>{{ item.title }}</strong>
								<small>{{ item.message }} · {{ item.scope_label || '' }}</small>
							</span>
							<span class="vetedge-home-card-action">View exact records</span>
						</button>
					</div>
					<div v-else class="vetedge-home-clear-state">
						<strong>No urgent operational exceptions are visible.</strong>
						<span>Your access-scoped work queues currently have no highlighted exceptions.</span>
					</div>
				</section>

				<section v-if="payload.metrics?.length" class="vetedge-home-section" aria-labelledby="vetedge-home-overview-heading">
					<div class="vetedge-home-section-heading">
						<div>
							<span>Mini dashboard</span>
							<h2 id="vetedge-home-overview-heading">Your Operational Snapshot</h2>
						</div>
						<small>{{ branchName }} · {{ payload.context?.operational_date }}</small>
					</div>
					<EdgeDashboardLayout class="vetedge-home-kpi-grid" min-column-width="11rem">
						<button
							v-for="metric in payload.metrics"
							:key="metric.key"
							type="button"
							class="vetedge-home-stat-button"
							@click="openMetric(metric.key)"
						>
							<EdgeStatCard
								:label="metric.label"
								:value="metric.value"
								:helper="`${metric.helper || ''}${metric.scope_label ? ` · ${metric.scope_label}` : ''}`"
								:tone="metric.tone || 'neutral'"
							/>
						</button>
					</EdgeDashboardLayout>
				</section>

				<section v-if="drilldown.open" ref="drilldownSection" class="vetedge-home-section vetedge-home-drilldown" aria-labelledby="vetedge-home-drilldown-heading">
					<div class="vetedge-home-section-heading">
						<div>
							<span>Exact card records</span>
							<h2 id="vetedge-home-drilldown-heading">{{ drilldown.metric?.label || 'Operational records' }}</h2>
							<small>{{ drilldown.total }} total · {{ drilldown.context?.branch_label }} · {{ drilldown.metric?.scope_label }}</small>
						</div>
						<div class="vetedge-home-drilldown-actions">
							<button v-if="drilldown.metric?.route" type="button" class="edge-button" @click="openRoute(drilldown.metric.route)">Open operational workspace</button>
							<button type="button" class="edge-button" @click="closeDrilldown">Close</button>
						</div>
					</div>

					<EdgeLoadingState v-if="drilldown.loading" message="Loading exact card records..." :skeleton="true" />
					<EdgeErrorState v-else-if="drilldown.error" title="Card records could not load" :message="drilldown.error" action-label="Try again" @retry="loadDrilldown(drilldown.start)" />
					<div v-else-if="!drilldown.rows.length" class="vetedge-home-clear-state">
						<strong>No records currently match this card.</strong>
						<span>The card total has been refreshed to zero.</span>
					</div>
					<EdgeDataTable
						v-else
						:columns="drilldown.columns"
						:rows="drilldown.rows"
						row-key="name"
						empty-title="No matching records"
						@row-click="openDrilldownRecord"
					>
						<template #footer>
							<span>Showing {{ drilldownFirst }}–{{ drilldownLast }} of {{ drilldown.total }}</span>
							<div class="vetedge-home-drilldown-actions">
								<button type="button" class="edge-button edge-button--compact" :disabled="!drilldownHasPrevious || drilldown.loading" @click="loadDrilldown(Math.max(0, drilldown.start - drilldown.pageLength))">Previous</button>
								<button type="button" class="edge-button edge-button--compact" :disabled="!drilldownHasNext || drilldown.loading" @click="loadDrilldown(drilldown.start + drilldown.pageLength)">Next</button>
							</div>
						</template>
					</EdgeDataTable>
				</section>

				<section class="vetedge-home-section" aria-labelledby="vetedge-home-actions-heading">
					<div class="vetedge-home-section-heading">
						<div>
							<span>Work faster</span>
							<h2 id="vetedge-home-actions-heading">Quick Actions</h2>
						</div>
						<small>Only actions available to your current access are shown</small>
					</div>

					<div v-if="actionGroups.length" class="vetedge-home-action-groups">
						<section v-for="group in actionGroups" :key="group.label" class="vetedge-home-action-group">
							<header><h3>{{ group.label }}</h3></header>
							<div class="vetedge-home-action-grid">
								<button
									v-for="action in group.actions"
									:key="action.key"
									type="button"
									class="vetedge-home-action-card"
									@click="openRoute(action.route)"
								>
									<span class="vetedge-home-action-icon" aria-hidden="true">{{ iconGlyph(action.icon) }}</span>
									<span>{{ action.label }}</span>
								</button>
							</div>
						</section>
					</div>
					<div v-else class="vetedge-home-clear-state">
						<strong>No quick actions are available for the current access.</strong>
						<span>Ask an administrator to review your Veterinary role bundle if this is unexpected.</span>
					</div>
				</section>
			</template>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
const ICON_GLYPHS = Object.freeze({
	dashboard: '▦', settings: '⚙', folder: '▤', education: '◫', calendar: '◷',
	clipboard: '▧', heart: '♡', home: '⌂', stock: '▣', users: '◎', assessment: '≡',
	list: '☷', globe: '◉', alert: '!', invoice: '▥', payment: '¤', package: '□', scissors: '✂',
});
const DRILLDOWN_PAGE_LENGTH = 25;

function readInitialContext() {
	const params = new URLSearchParams(window.location.search || '');
	return {
		branch: params.get('branch') || '',
		date: params.get('date') || '',
	};
}

export default {
	name: 'VetEdgeHome',
	data() {
		const initial = readInitialContext();
		return {
			loading: true,
			error: '',
			selectedBranch: initial.branch,
			selectedDate: initial.date,
			payload: {
				primary_persona: {}, personas: [], context: {}, metrics: [], attention: [], quick_actions: [],
			},
			drilldown: {
				open: false, loading: false, error: '', metricKey: '', metric: {}, doctype: '',
				total: 0, rows: [], columns: [], start: 0, pageLength: DRILLDOWN_PAGE_LENGTH, context: {},
			},
		};
	},
	computed: {
		identity() {
			return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {};
		},
		userName() {
			const user = frappe.session?.user || '';
			const info = frappe.boot?.user_info?.[user] || {};
			return info.fullname || info.full_name || user;
		},
		branchName() {
			return this.payload.context?.branch_label
				|| frappe.boot?.edgesuite_product_menu?.branch
				|| frappe.defaults?.get_user_default?.('branch')
				|| 'All permitted branches';
		},
		primaryPersonaLabel() {
			return this.payload.primary_persona?.label || 'Veterinary Staff';
		},
		secondaryPersonas() {
			const primary = this.payload.primary_persona?.key || '';
			return (this.payload.personas || []).filter((persona) => persona.key !== primary).map((persona) => persona.label);
		},
		homeSubtitle() {
			return `${this.primaryPersonaLabel} action centre — branch-aware, date-aware, and reconciled to exact operational records.`;
		},
		actionGroups() {
			const groups = [];
			const byLabel = new Map();
			for (const action of this.payload.quick_actions || []) {
				const label = action.group || 'Veterinary';
				if (!byLabel.has(label)) {
					const group = { label, actions: [] };
					byLabel.set(label, group);
					groups.push(group);
				}
				byLabel.get(label).actions.push(action);
			}
			return groups;
		},
		drilldownFirst() {
			return this.drilldown.total ? this.drilldown.start + 1 : 0;
		},
		drilldownLast() {
			return Math.min(this.drilldown.start + this.drilldown.rows.length, this.drilldown.total);
		},
		drilldownHasPrevious() {
			return this.drilldown.start > 0;
		},
		drilldownHasNext() {
			return this.drilldown.start + this.drilldown.rows.length < this.drilldown.total;
		},
	},
	mounted() {
		this.loadHome();
	},
	methods: {
		iconGlyph(icon) {
			return ICON_GLYPHS[icon] || '→';
		},
		openRoute(route) {
			if (!route) return;
			const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.('navigation:vetedge');
			if (adapter?.open?.(route) === true) return;
			window.location.assign(route);
		},
		updateLocation() {
			const url = new URL(window.location.href);
			if (this.selectedBranch) url.searchParams.set('branch', this.selectedBranch);
			else url.searchParams.delete('branch');
			if (this.selectedDate) url.searchParams.set('date', this.selectedDate);
			else url.searchParams.delete('date');
			window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
		},
		async applyContext() {
			this.closeDrilldown();
			await this.loadHome();
		},
		async loadHome() {
			this.loading = true;
			this.error = '';
			try {
				const response = await frappe.call('vetedge.services.home.get_home_payload', {
					operational_date: this.selectedDate || undefined,
					branch: this.selectedBranch || undefined,
				});
				this.payload = response?.message || this.payload;
				this.selectedBranch = this.payload.context?.branch_value || this.selectedBranch || '';
				this.selectedDate = this.payload.context?.operational_date || this.selectedDate || '';
				this.updateLocation();
			} catch (error) {
				this.error = error?.message || __('Veterinary Home could not be loaded.');
			} finally {
				this.loading = false;
			}
		},
		async openMetric(metricKey) {
			this.drilldown = {
				...this.drilldown,
				open: true,
				metricKey,
				start: 0,
				error: '',
			};
			await this.loadDrilldown(0);
			this.$nextTick(() => this.$refs.drilldownSection?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }));
		},
		async loadDrilldown(start = 0) {
			if (!this.drilldown.metricKey) return;
			this.drilldown.loading = true;
			this.drilldown.error = '';
			try {
				const response = await frappe.call('vetedge.services.home.get_metric_drilldown', {
					metric_key: this.drilldown.metricKey,
					operational_date: this.selectedDate || undefined,
					branch: this.selectedBranch || undefined,
					limit_start: start,
					limit_page_length: this.drilldown.pageLength,
				});
				const result = response?.message || {};
				this.drilldown = {
					...this.drilldown,
					open: true,
					loading: false,
					metric: result.metric || {},
					doctype: result.doctype || '',
					total: Number(result.total || 0),
					rows: result.rows || [],
					columns: result.columns || [],
					start: Number(result.limit_start || 0),
					pageLength: Number(result.limit_page_length || DRILLDOWN_PAGE_LENGTH),
					context: result.context || {},
				};
				this.reconcileMetricCount(this.drilldown.metricKey, this.drilldown.total);
			} catch (error) {
				this.drilldown.loading = false;
				this.drilldown.error = error?.message || __('The exact card records could not be loaded.');
			}
		},
		reconcileMetricCount(metricKey, total) {
			const metric = (this.payload.metrics || []).find((row) => row.key === metricKey);
			if (metric) metric.value = total;
			const attention = (this.payload.attention || []).find((row) => row.key === metricKey);
			if (attention) attention.count = total;
		},
		closeDrilldown() {
			this.drilldown = {
				open: false, loading: false, error: '', metricKey: '', metric: {}, doctype: '',
				total: 0, rows: [], columns: [], start: 0, pageLength: DRILLDOWN_PAGE_LENGTH, context: {},
			};
		},
		openDrilldownRecord(row) {
			if (!row?.name || !this.drilldown.doctype) return;
			if (frappe.set_route) {
				frappe.set_route('Form', this.drilldown.doctype, row.name);
				return;
			}
			const slug = this.drilldown.doctype.toLowerCase().replace(/\s+/g, '-');
			window.location.assign(`/desk/${slug}/${encodeURIComponent(row.name)}`);
		},
	},
};
</script>

<style scoped>
.vetedge-home-page { padding-bottom: 2rem; }
.vetedge-home-controls {
	display: grid;
	grid-template-columns: minmax(12rem, 1fr) minmax(11rem, 0.55fr) minmax(16rem, 1.4fr);
	gap: 0.75rem;
	align-items: end;
	padding: 1rem;
	margin-bottom: 1rem;
	border: 1px solid var(--edge-color-border, var(--border-color));
	border-radius: 0.85rem;
	background: var(--edge-color-surface, var(--card-bg));
}
.vetedge-home-control { display: grid; gap: 0.35rem; }
.vetedge-home-control label { font-size: 0.75rem; font-weight: 700; color: var(--text-muted); }
.vetedge-home-context-note { display: grid; gap: 0.2rem; }
.vetedge-home-context-note span { color: var(--text-muted); font-size: 0.82rem; }
.vetedge-home-context {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
	gap: 0.75rem;
	margin-bottom: 1.25rem;
}
.vetedge-home-context > div,
.vetedge-home-clear-state,
.vetedge-home-attention-card,
.vetedge-home-action-group,
.vetedge-home-drilldown {
	border: 1px solid var(--edge-color-border, var(--border-color));
	background: var(--edge-color-surface, var(--card-bg));
	border-radius: 0.85rem;
}
.vetedge-home-context > div { padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.2rem; }
.vetedge-home-context-label,
.vetedge-home-section-heading span {
	font-size: 0.72rem;
	font-weight: 700;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--text-muted);
}
.vetedge-home-section { margin-top: 1.5rem; }
.vetedge-home-section-heading {
	display: flex;
	align-items: end;
	justify-content: space-between;
	gap: 1rem;
	margin-bottom: 0.8rem;
}
.vetedge-home-section-heading h2,
.vetedge-home-action-group h3 { margin: 0.15rem 0 0; }
.vetedge-home-section-heading small,
.vetedge-home-clear-state span,
.vetedge-home-attention-copy small { color: var(--text-muted); }
.vetedge-home-attention-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr));
	gap: 0.75rem;
}
.vetedge-home-attention-card {
	appearance: none;
	width: 100%;
	text-align: left;
	padding: 0.95rem;
	display: grid;
	grid-template-columns: auto 1fr auto;
	align-items: center;
	gap: 0.8rem;
	color: inherit;
	cursor: pointer;
}
.vetedge-home-attention-card:hover,
.vetedge-home-action-card:hover,
.vetedge-home-stat-button:hover { transform: translateY(-1px); }
.vetedge-home-attention-count {
	min-width: 2.3rem;
	height: 2.3rem;
	border-radius: 999px;
	display: inline-flex;
	align-items: center;
	justify-content: center;
	font-weight: 800;
	background: var(--control-bg);
}
.vetedge-home-attention-copy { display: flex; flex-direction: column; gap: 0.2rem; }
.vetedge-home-card-action { font-size: 0.78rem; font-weight: 700; }
.vetedge-home-clear-state { padding: 1rem; display: flex; flex-direction: column; gap: 0.25rem; }
.vetedge-home-kpi-grid { align-items: stretch; }
.vetedge-home-stat-button {
	appearance: none;
	border: 0;
	background: transparent;
	padding: 0;
	text-align: inherit;
	color: inherit;
	cursor: pointer;
	transition: transform 120ms ease;
}
.vetedge-home-stat-button > * { height: 100%; }
.vetedge-home-drilldown { padding: 1rem; }
.vetedge-home-drilldown-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
.vetedge-home-action-groups { display: grid; gap: 1rem; }
.vetedge-home-action-group { padding: 1rem; }
.vetedge-home-action-group header { margin-bottom: 0.75rem; }
.vetedge-home-action-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
	gap: 0.65rem;
}
.vetedge-home-action-card {
	appearance: none;
	border: 1px solid var(--edge-color-border, var(--border-color));
	background: var(--control-bg);
	border-radius: 0.7rem;
	padding: 0.8rem 0.9rem;
	color: inherit;
	text-align: left;
	display: flex;
	align-items: center;
	gap: 0.65rem;
	font-weight: 650;
	cursor: pointer;
	transition: transform 120ms ease;
}
.vetedge-home-action-icon {
	width: 1.75rem;
	height: 1.75rem;
	border-radius: 0.55rem;
	display: inline-flex;
	align-items: center;
	justify-content: center;
	background: var(--edge-color-surface, var(--card-bg));
}
@media (max-width: 820px) {
	.vetedge-home-controls { grid-template-columns: 1fr; align-items: stretch; }
}
@media (max-width: 720px) {
	.vetedge-home-section-heading { align-items: start; flex-direction: column; }
	.vetedge-home-attention-card { grid-template-columns: auto 1fr; }
	.vetedge-home-card-action { grid-column: 2; }
}
</style>
