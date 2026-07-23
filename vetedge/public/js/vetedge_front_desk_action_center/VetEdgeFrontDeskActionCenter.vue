<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/app/vetedge-front-desk-action-center"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Front Desk Operations"
					title="Front Desk Action Centre"
					subtitle="Review booking requests, manage the live appointment queue and resolve missed appointments."
					action-label="Refresh"
					@action="refreshAll"
				/>
			</template>

			<section class="vetedge-frontdesk-summary" aria-label="Front desk summary">
				<EdgeStatCard label="Guest requests" :value="summary.guest_requests || 0" icon="file-question-mark" />
				<EdgeStatCard label="Today's appointments" :value="summary.today_appointments || 0" icon="calendar-days" />
				<EdgeStatCard label="Open missed" :value="summary.open_missed || 0" icon="calendar-x" />
			</section>

			<nav class="vetedge-frontdesk-tabs" aria-label="Front desk workflows">
				<button
					v-for="option in tabOptions"
					:key="option.value"
					type="button"
					:class="['vetedge-frontdesk-tab', { 'is-active': tab === option.value }]"
					@click="changeTab(option.value)"
				>
					<span>{{ option.label }}</span>
					<small>{{ option.description }}</small>
				</button>
			</nav>

			<template #filters>
				<EdgeFilterBar title="Filter front desk work">
					<div class="vetedge-frontdesk-filters">
						<EdgeLinkField
							:model-value="filters.branch || ''"
							label="Branch"
							placeholder="All permitted branches"
							:searcher="(query) => linkSearch('branch', query)"
							@update:model-value="(value) => setFilter('branch', value)"
						/>
						<EdgeLinkField
							v-if="tab === 'queue'"
							:model-value="filters.practitioner || ''"
							label="Practitioner"
							placeholder="All doctors"
							:searcher="(query) => linkSearch('practitioner', query)"
							@update:model-value="(value) => setFilter('practitioner', value)"
						/>
						<label v-if="tab === 'queue'" class="vetedge-frontdesk-filter">
							<span>Status</span>
							<select v-model="filters.status" class="form-control">
								<option value="">Active queue statuses</option>
								<option v-for="status in appointmentStatuses" :key="status" :value="status">{{ status }}</option>
							</select>
						</label>
						<label v-if="tab === 'guest'" class="vetedge-frontdesk-filter">
							<span>Status</span>
							<select v-model="filters.status" class="form-control">
								<option value="">All statuses</option>
								<option v-for="status in guestStatuses" :key="status" :value="status">{{ status }}</option>
							</select>
						</label>
						<label v-if="tab === 'missed'" class="vetedge-frontdesk-filter">
							<span>Status</span>
							<select v-model="filters.status" class="form-control">
								<option value="">All statuses</option>
								<option v-for="status in missedStatuses" :key="status" :value="status">{{ status }}</option>
							</select>
						</label>
						<label v-if="tab === 'missed'" class="vetedge-frontdesk-filter">
							<span>Resolution</span>
							<select v-model="filters.resolved" class="form-control">
								<option value="">All</option>
								<option value="0">Open</option>
								<option value="1">Resolved</option>
							</select>
						</label>
						<label v-if="tab !== 'queue'" class="vetedge-frontdesk-filter vetedge-frontdesk-filter--search">
							<span>Search</span>
							<input
								v-model.trim="filters.search"
								type="search"
								class="form-control"
								placeholder="Name, patient, owner or phone"
								@keyup.enter="applyFilters"
							/>
						</label>
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading Front Desk Action Centre..." :skeleton="true" />
			<EdgeErrorState
				v-else-if="error"
				title="The Front Desk Action Centre could not load"
				:message="error"
				action-label="Try again"
				@retry="refreshAll"
			/>

			<template v-else-if="tab === 'queue'">
				<section v-for="section in queueSections" :key="section.key" class="vetedge-frontdesk-section">
					<header>
						<div>
							<h3>{{ section.label }}</h3>
							<p>{{ section.description }}</p>
						</div>
						<strong>{{ section.rows.length }}</strong>
					</header>
					<EdgeDataTable
						:columns="queueColumns"
						:rows="section.rows"
						:actions="openAction"
						empty-title="No appointments"
						empty-description="No appointments match this time bucket and filter."
						@row-click="openQueueDetail"
						@action="({ row }) => openQueueDetail(row)"
					/>
				</section>
			</template>

			<template v-else-if="tab === 'guest'">
				<EdgeDataTable
					:columns="guestColumns"
					:rows="guestList.rows || []"
					:actions="openAction"
					empty-title="No guest booking requests"
					empty-description="No booking requests match the current filters."
					@row-click="openGuestDetail"
					@action="({ row }) => openGuestDetail(row)"
				>
					<template #footer>
						<span>Showing {{ guestFirstVisible }}–{{ guestLastVisible }} of {{ guestList.total || 0 }}</span>
						<div class="vetedge-frontdesk-pagination">
							<button type="button" class="edge-button edge-button--compact" :disabled="!guestHasPrevious" @click="previousGuestPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!guestHasNext" @click="nextGuestPage">Next</button>
						</div>
					</template>
				</EdgeDataTable>
			</template>

			<template v-else>
				<section class="vetedge-frontdesk-notice">
					<strong>Conflict-safe actions</strong>
					<p>Each action uses the latest server timestamp. When another user or the hourly sync changes the record, the Action Centre asks you to refresh instead of overwriting newer work.</p>
				</section>
				<EdgeDataTable
					:columns="missedColumns"
					:rows="missedList.rows || []"
					:actions="openAction"
					empty-title="No missed appointments"
					empty-description="No missed appointments match the current filters."
					@row-click="openMissedDetail"
					@action="({ row }) => openMissedDetail(row)"
				>
					<template #footer>
						<span>Showing {{ missedFirstVisible }}–{{ missedLastVisible }} of {{ missedList.total || 0 }}</span>
						<div class="vetedge-frontdesk-pagination">
							<button type="button" class="edge-button edge-button--compact" :disabled="!missedHasPrevious" @click="previousMissedPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!missedHasNext" @click="nextMissedPage">Next</button>
						</div>
					</template>
				</EdgeDataTable>
			</template>
		</EdgePageLayout>

		<EdgeModal
			:open="detail.open"
			:title="detailTitle"
			:subtitle="detailSubtitle"
			:busy="detail.loading || actionBusy"
			@close="closeDetail"
		>
			<EdgeLoadingState v-if="detail.loading" message="Loading action details..." :skeleton="true" />
			<div v-else-if="detail.payload" class="vetedge-frontdesk-detail">
				<div class="vetedge-frontdesk-detail-status">
					<EdgeStatusBadge :label="detail.payload.status || 'Open'" :status="detail.payload.status || 'Open'" />
				</div>
				<dl>
					<template v-for="entry in detailEntries" :key="entry.label">
						<dt>{{ entry.label }}</dt>
						<dd>{{ formatValue(entry.value, entry.type) }}</dd>
					</template>
				</dl>
				<div class="vetedge-frontdesk-linked-actions">
					<button v-for="link in detailLinks" :key="link.label" type="button" class="edge-button edge-button--compact" @click="openLinked(link)">
						{{ link.label }}
					</button>
				</div>
			</div>
			<template #footer>
				<button type="button" class="edge-button" :disabled="actionBusy" @click="closeDetail">Close</button>
				<button
					v-for="action in detail.payload?.actions || []"
					:key="action.key"
					type="button"
					:class="['edge-button', action.danger ? 'edge-button--danger' : action.primary ? 'edge-button--primary' : '']"
					:disabled="actionBusy"
					@click="prepareAction(action)"
				>
					{{ action.label }}
				</button>
			</template>
		</EdgeModal>

		<EdgeModal
			:open="actionDialog.open"
			:title="actionDialog.title"
			:subtitle="actionDialog.subtitle"
			:busy="actionBusy"
			@close="closeActionDialog"
		>
			<div class="vetedge-frontdesk-action-form">
				<label v-if="actionDialog.action?.key === 'reschedule'">
					<span>New Date</span>
					<input v-model="actionDialog.values.new_date" type="date" class="form-control" required />
				</label>
				<label v-if="actionDialog.action?.key === 'reschedule'">
					<span>New Time</span>
					<input v-model="actionDialog.values.new_time" type="time" class="form-control" />
				</label>
				<label v-if="actionNeedsNote">
					<span>{{ actionDialog.action?.key === 'resolve' ? 'Resolution Note' : 'Note' }}</span>
					<textarea v-model="actionNote" class="form-control" rows="4"></textarea>
				</label>
				<p v-if="!actionNeedsInput">Continue with {{ actionDialog.action?.label }}?</p>
			</div>
			<template #footer>
				<button type="button" class="edge-button" :disabled="actionBusy" @click="closeActionDialog">Cancel</button>
				<button
					type="button"
					:class="['edge-button', actionDialog.action?.danger ? 'edge-button--danger' : 'edge-button--primary']"
					:disabled="actionBusy || !actionFormValid"
					@click="executeAction"
				>
					{{ actionBusy ? 'Working…' : actionDialog.action?.label }}
				</button>
			</template>
		</EdgeModal>
	</EdgeAppShell>
</template>

<script>
const API = Object.freeze({
	summary: "vetedge.services.front_desk_action_center.get_front_desk_summary",
	guestList: "vetedge.services.front_desk_action_center.get_guest_requests",
	guestDetail: "vetedge.services.front_desk_action_center.get_guest_request_detail",
	guestAction: "vetedge.services.front_desk_action_center.perform_guest_request_action",
	queue: "vetedge.services.front_desk_action_center.get_appointment_queue_view",
	queueDetail: "vetedge.services.front_desk_action_center.get_appointment_action_detail",
	queueAction: "vetedge.services.front_desk_action_center.perform_appointment_queue_action",
	missedList: "vetedge.services.front_desk_action_center.get_missed_appointments",
	missedDetail: "vetedge.services.front_desk_action_center.get_missed_appointment_detail",
	missedAction: "vetedge.services.front_desk_action_center.perform_missed_appointment_action",
	link: "vetedge.services.front_desk_action_center.get_front_desk_link_options",
});

const TABS = Object.freeze([
	{ value: "queue", label: "Appointment Queue", description: "Today, tomorrow and future workload" },
	{ value: "guest", label: "Guest Requests", description: "Registration and appointment conversion" },
	{ value: "missed", label: "Missed Appointments", description: "Contact, reschedule, cancel or resolve" },
]);

function errorMessage(error, fallback) {
	return error?.message || error?._server_messages || error?.exc_type || fallback || __("The operation could not be completed.");
}

export default {
	name: "VetEdgeFrontDeskActionCenter",
	data() {
		const route = new URLSearchParams(window.location.search || "");
		const requested = route.get("tab") || "queue";
		return {
			tab: TABS.some((option) => option.value === requested) ? requested : "queue",
			tabOptions: TABS,
			summary: {},
			filters: { branch: "", practitioner: "", status: "", resolved: "", search: "" },
			queue: { today: [], tomorrow: [], future: [] },
			guestList: { rows: [], total: 0, start: 0, page_length: 25 },
			missedList: { rows: [], total: 0, start: 0, page_length: 25 },
			pageLength: 25,
			loading: true,
			error: "",
			actionBusy: false,
			detail: { open: false, loading: false, type: "", payload: null },
			actionDialog: { open: false, title: "Confirm action", subtitle: "", action: null, values: {} },
			appointmentStatuses: ["Awaiting Registration", "Owner Requested", "Scheduled", "Confirmed", "Checked In", "In Consultation", "Completed", "Rescheduled", "Cancelled", "No Show"],
			guestStatuses: ["Registration Requested", "Registration Confirmed", "Converted", "Cancelled"],
			missedStatuses: ["Open", "Contacted", "Rescheduled", "Cancelled", "Resolved", "Reopened"],
		};
	},
	computed: {
		identity() { return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {}; },
		branchName() { return frappe.boot?.edgesuite_product_menu?.branch || frappe.defaults?.get_user_default?.("branch") || "All Branches"; },
		userName() {
			const user = frappe.session?.user || "";
			const info = frappe.boot?.user_info?.[user] || {};
			return info.fullname || info.full_name || user;
		},
		openAction() { return [{ key: "open", label: "Review", primary: true }]; },
		queueColumns() {
			return [
				{ fieldname: "appointment_title", label: "Appointment", fieldtype: "Data" },
				{ fieldname: "appointment_datetime", label: "Date / Time", fieldtype: "Datetime" },
				{ fieldname: "practitioner_name", label: "Practitioner", fieldtype: "Data" },
				{ fieldname: "branch", label: "Branch", fieldtype: "Link" },
				{ fieldname: "status", label: "Status", fieldtype: "Data", status: true },
			];
		},
		guestColumns() {
			return [
				{ fieldname: "guest_name", label: "Guest", fieldtype: "Data" },
				{ fieldname: "pet_name", label: "Pet", fieldtype: "Data" },
				{ fieldname: "preferred_branch", label: "Branch", fieldtype: "Link" },
				{ fieldname: "preferred_datetime", label: "Preferred Time", fieldtype: "Datetime" },
				{ fieldname: "status", label: "Status", fieldtype: "Data", status: true },
			];
		},
		missedColumns() {
			return [
				{ fieldname: "appointment", label: "Appointment", fieldtype: "Link" },
				{ fieldname: "appointment_datetime", label: "Date / Time", fieldtype: "Datetime" },
				{ fieldname: "patient", label: "Patient", fieldtype: "Link" },
				{ fieldname: "branch", label: "Branch", fieldtype: "Link" },
				{ fieldname: "status", label: "Status", fieldtype: "Data", status: true },
			];
		},
		queueSections() {
			return [
				{ key: "today", label: "Today", description: "Appointments scheduled for today", rows: this.queue.today || [] },
				{ key: "tomorrow", label: "Tomorrow", description: "Prepare the next working day", rows: this.queue.tomorrow || [] },
				{ key: "future", label: "Future", description: "Appointments from two days ahead", rows: this.queue.future || [] },
			];
		},
		guestHasPrevious() { return (this.guestList.start || 0) > 0; },
		guestHasNext() { return (this.guestList.start || 0) + (this.guestList.rows?.length || 0) < (this.guestList.total || 0); },
		guestFirstVisible() { return this.guestList.total ? (this.guestList.start || 0) + 1 : 0; },
		guestLastVisible() { return Math.min((this.guestList.start || 0) + (this.guestList.rows?.length || 0), this.guestList.total || 0); },
		missedHasPrevious() { return (this.missedList.start || 0) > 0; },
		missedHasNext() { return (this.missedList.start || 0) + (this.missedList.rows?.length || 0) < (this.missedList.total || 0); },
		missedFirstVisible() { return this.missedList.total ? (this.missedList.start || 0) + 1 : 0; },
		missedLastVisible() { return Math.min((this.missedList.start || 0) + (this.missedList.rows?.length || 0), this.missedList.total || 0); },
		detailTitle() {
			if (!this.detail.payload) return "Review action";
			if (this.detail.type === "guest") return this.detail.payload.values?.guest_name || this.detail.payload.name;
			if (this.detail.type === "missed") return `Missed Appointment · ${this.detail.payload.values?.patient_label || this.detail.payload.name}`;
			return this.detail.payload.values?.appointment_title || this.detail.payload.name;
		},
		detailSubtitle() { return this.detail.payload?.name || ""; },
		detailEntries() {
			const values = this.detail.payload?.values || {};
			if (this.detail.type === "guest") {
				return [
					{ label: "Guest", value: values.guest_name }, { label: "Email", value: values.guest_email },
					{ label: "Phone", value: values.guest_phone }, { label: "Pet", value: values.pet_name },
					{ label: "Species", value: values.species_label || values.species }, { label: "Breed", value: values.breed_label || values.breed },
					{ label: "Branch", value: values.preferred_branch }, { label: "Preferred Time", value: values.preferred_datetime, type: "datetime" },
					{ label: "Reason", value: values.reason_for_visit },
				];
			}
			if (this.detail.type === "missed") {
				return [
					{ label: "Patient", value: values.patient_label || values.patient }, { label: "Owner", value: values.owner_label || values.primary_owner },
					{ label: "Appointment Time", value: values.appointment_datetime, type: "datetime" }, { label: "Branch", value: values.branch },
					{ label: "Practitioner", value: values.practitioner }, { label: "Original Status", value: values.original_status },
					{ label: "Contact Note", value: values.contact_note }, { label: "Resolution", value: values.resolution_status },
					{ label: "Resolution Note", value: values.resolution_note },
				];
			}
			return [
				{ label: "Patient", value: values.patient_label || values.patient }, { label: "Owner", value: values.owner_label || values.primary_owner },
				{ label: "Date / Time", value: values.appointment_datetime, type: "datetime" }, { label: "Practitioner", value: values.practitioner_name || values.practitioner },
				{ label: "Branch", value: values.branch }, { label: "Type", value: values.appointment_type }, { label: "Notes", value: values.notes },
			];
		},
		detailLinks() {
			const values = this.detail.payload?.values || {};
			const links = [];
			if (values.patient) links.push({ label: "Open Patient", kind: "patient", name: values.patient });
			if (values.appointment) links.push({ label: "Open Appointment", kind: "appointment", name: values.appointment });
			if (this.detail.type === "queue") links.push({ label: "Open Appointment", kind: "appointment", name: this.detail.payload.name });
			if (values.linked_appointment) links.push({ label: "Open Appointment", kind: "appointment", name: values.linked_appointment });
			if (values.linked_customer) links.push({ label: "Open Customer", kind: "customer", name: values.linked_customer });
			if (values.registration_invoice) links.push({ label: "Open Invoice", kind: "invoice", name: values.registration_invoice });
			if (values.linked_consultation) links.push({ label: "Open Consultation", kind: "consultation", name: values.linked_consultation });
			return links;
		},
		actionNeedsNote() { return ["mark_contacted", "reschedule", "cancel_appointment", "resolve", "reopen"].includes(this.actionDialog.action?.key); },
		actionNeedsInput() { return this.actionNeedsNote || this.actionDialog.action?.key === "reschedule"; },
		actionNote: {
			get() { return this.actionDialog.action?.key === "resolve" ? this.actionDialog.values.resolution_note || "" : this.actionDialog.values.note || ""; },
			set(value) {
				if (this.actionDialog.action?.key === "resolve") this.actionDialog.values.resolution_note = value;
				else this.actionDialog.values.note = value;
			},
		},
		actionFormValid() { return this.actionDialog.action?.key !== "reschedule" || Boolean(this.actionDialog.values.new_date); },
	},
	mounted() { this.loadRoute(); },
	methods: {
		async call(method, args = {}) { const response = await frappe.call(method, args); return response?.message; },
		async loadRoute() {
			const route = new URLSearchParams(window.location.search || "");
			const requested = route.get("tab") || this.tab;
			this.tab = TABS.some((option) => option.value === requested) ? requested : "queue";
			await this.refreshAll();
			const name = route.get("name");
			if (name) {
				if (this.tab === "guest") await this.openGuestDetail({ name });
				else if (this.tab === "missed") await this.openMissedDetail({ name });
				else await this.openQueueDetail({ name });
			}
		},
		async refreshAll() {
			this.loading = true;
			this.error = "";
			try {
				this.summary = await this.call(API.summary, { branch: this.filters.branch || null });
				await this.loadCurrentTab();
			} catch (error) {
				this.error = errorMessage(error, __("The Front Desk Action Centre could not be loaded."));
			} finally { this.loading = false; }
		},
		async loadCurrentTab() {
			if (this.tab === "queue") return this.loadQueue();
			if (this.tab === "guest") return this.loadGuestList();
			return this.loadMissedList();
		},
		async loadQueue() {
			this.queue = await this.call(API.queue, {
				branch: this.filters.branch || null,
				practitioner: this.filters.practitioner || null,
				status: this.filters.status || null,
			});
		},
		async loadGuestList() {
			this.guestList = await this.call(API.guestList, {
				branch: this.filters.branch || null, status: this.filters.status || null,
				search: this.filters.search || "", start: this.guestList.start || 0, page_length: this.pageLength,
			});
		},
		async loadMissedList() {
			this.missedList = await this.call(API.missedList, {
				branch: this.filters.branch || null, status: this.filters.status || null,
				resolved: this.filters.resolved, search: this.filters.search || "",
				start: this.missedList.start || 0, page_length: this.pageLength,
			});
		},
		async changeTab(next) {
			if (this.tab === next) return;
			this.tab = next;
			this.filters = { branch: this.filters.branch || "", practitioner: "", status: "", resolved: "", search: "" };
			this.guestList.start = 0;
			this.missedList.start = 0;
			this.replaceLocation({ tab: next });
			await this.refreshAll();
		},
		setFilter(fieldname, value) { this.filters = { ...this.filters, [fieldname]: value || "" }; },
		async linkSearch(fieldname, query) { return (await this.call(API.link, { fieldname, query })) || []; },
		async applyFilters() { this.guestList.start = 0; this.missedList.start = 0; await this.refreshAll(); },
		async resetFilters() {
			this.filters = { branch: "", practitioner: "", status: "", resolved: "", search: "" };
			this.guestList.start = 0; this.missedList.start = 0; await this.refreshAll();
		},
		async previousGuestPage() { this.guestList.start = Math.max(0, (this.guestList.start || 0) - this.pageLength); await this.withLoading(this.loadGuestList); },
		async nextGuestPage() { this.guestList.start = (this.guestList.start || 0) + this.pageLength; await this.withLoading(this.loadGuestList); },
		async previousMissedPage() { this.missedList.start = Math.max(0, (this.missedList.start || 0) - this.pageLength); await this.withLoading(this.loadMissedList); },
		async nextMissedPage() { this.missedList.start = (this.missedList.start || 0) + this.pageLength; await this.withLoading(this.loadMissedList); },
		async withLoading(action) { this.loading = true; try { await action(); } catch (error) { this.error = errorMessage(error); } finally { this.loading = false; } },
		async openGuestDetail(row) { await this.openDetail("guest", API.guestDetail, row?.name); },
		async openQueueDetail(row) { await this.openDetail("queue", API.queueDetail, row?.name); },
		async openMissedDetail(row) { await this.openDetail("missed", API.missedDetail, row?.name); },
		async openDetail(type, method, name) {
			if (!name) return;
			this.detail = { open: true, loading: true, type, payload: null };
			try {
				this.detail.payload = await this.call(method, { name });
				this.replaceLocation({ tab: this.tab, name });
			} catch (error) {
				frappe.msgprint({ title: __("Unable to open"), message: errorMessage(error), indicator: "red" });
				this.closeDetail();
			} finally { this.detail.loading = false; }
		},
		closeDetail() { this.detail = { open: false, loading: false, type: "", payload: null }; this.replaceLocation({ tab: this.tab }); },
		prepareAction(action) {
			this.actionDialog = {
				open: true,
				title: action.label,
				subtitle: this.detail.payload?.name || "",
				action,
				values: { note: "", resolution_note: "", new_date: "", new_time: "" },
			};
		},
		closeActionDialog() { if (!this.actionBusy) this.actionDialog = { open: false, title: "", subtitle: "", action: null, values: {} }; },
		async executeAction() {
			if (!this.actionDialog.action || !this.actionFormValid || this.actionBusy) return;
			this.actionBusy = true;
			try {
				const common = { name: this.detail.payload.name, action: this.actionDialog.action.key, modified: this.detail.payload.modified };
				let result;
				if (this.detail.type === "guest") result = await this.call(API.guestAction, common);
				else if (this.detail.type === "queue") result = await this.call(API.queueAction, common);
				else result = await this.call(API.missedAction, { ...common, values: JSON.stringify(this.actionDialog.values) });
				this.detail.payload = this.detail.type === "queue" ? result?.detail : result;
				frappe.show_alert({ message: __("Front desk action completed"), indicator: "green" });
				this.closeActionDialog();
				await this.refreshAll();
				if (result?.consultation?.name) this.openRoute(`/app/veterinary-consultation/${encodeURIComponent(result.consultation.name)}`);
			} catch (error) {
				frappe.msgprint({ title: __("Unable to complete action"), message: errorMessage(error), indicator: "red" });
			} finally { this.actionBusy = false; }
		},
		formatValue(value, type) {
			if (value === undefined || value === null || value === "") return "—";
			if (type === "datetime") return frappe.datetime?.str_to_user?.(value) || String(value);
			return String(value);
		},
		openLinked(link) {
			if (!link?.name) return;
			const routes = {
				patient: `/app/vetedge-document-workspace?resource=patients&name=${encodeURIComponent(link.name)}`,
				appointment: `/app/vetedge-document-workspace?resource=appointments&name=${encodeURIComponent(link.name)}`,
				customer: `/app/customer/${encodeURIComponent(link.name)}`,
				invoice: `/app/sales-invoice/${encodeURIComponent(link.name)}`,
				consultation: `/app/veterinary-consultation/${encodeURIComponent(link.name)}`,
			};
			this.openRoute(routes[link.kind]);
		},
		openRoute(route) { if (route) window.location.href = route; },
		replaceLocation(values) {
			const url = new URL(window.location.href);
			url.search = "";
			for (const [key, value] of Object.entries(values || {})) if (value) url.searchParams.set(key, value);
			window.history.replaceState({}, "", `${url.pathname}${url.search}`);
		},
	},
};
</script>

<style scoped>
.vetedge-frontdesk-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin-bottom: 1rem; }
.vetedge-frontdesk-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin-bottom: 1rem; }
.vetedge-frontdesk-tab { text-align: left; border: 1px solid var(--edge-border, #dfe3e8); border-radius: 12px; background: var(--edge-surface, #fff); padding: .9rem 1rem; }
.vetedge-frontdesk-tab span { display: block; font-weight: 700; }
.vetedge-frontdesk-tab small { display: block; margin-top: .2rem; opacity: .7; }
.vetedge-frontdesk-tab.is-active { border-color: var(--edge-accent, #2563eb); box-shadow: 0 0 0 2px color-mix(in srgb, var(--edge-accent, #2563eb) 16%, transparent); }
.vetedge-frontdesk-filters { display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: .75rem; width: 100%; }
.vetedge-frontdesk-filter { display: grid; gap: .35rem; }
.vetedge-frontdesk-filter span { font-size: .78rem; font-weight: 600; }
.vetedge-frontdesk-section { margin-bottom: 1.25rem; }
.vetedge-frontdesk-section > header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: .6rem; }
.vetedge-frontdesk-section h3 { margin: 0; font-size: 1rem; }
.vetedge-frontdesk-section p { margin: .15rem 0 0; opacity: .7; }
.vetedge-frontdesk-section header strong { min-width: 2rem; text-align: center; border-radius: 999px; padding: .25rem .6rem; background: var(--edge-muted, #eef2f7); }
.vetedge-frontdesk-pagination, .vetedge-frontdesk-linked-actions { display: flex; flex-wrap: wrap; gap: .5rem; }
.vetedge-frontdesk-notice { border: 1px solid var(--edge-border, #dfe3e8); border-left: 4px solid var(--edge-accent, #2563eb); border-radius: 10px; padding: .85rem 1rem; margin-bottom: 1rem; }
.vetedge-frontdesk-notice p { margin: .25rem 0 0; }
.vetedge-frontdesk-detail-status { margin-bottom: 1rem; }
.vetedge-frontdesk-detail dl { display: grid; grid-template-columns: minmax(120px, .45fr) 1fr; gap: .55rem 1rem; margin: 0 0 1rem; }
.vetedge-frontdesk-detail dt { font-weight: 600; opacity: .75; }
.vetedge-frontdesk-detail dd { margin: 0; overflow-wrap: anywhere; }
.vetedge-frontdesk-action-form { display: grid; gap: .9rem; }
.vetedge-frontdesk-action-form label { display: grid; gap: .35rem; }
@media (max-width: 900px) {
	.vetedge-frontdesk-summary, .vetedge-frontdesk-tabs { grid-template-columns: 1fr; }
	.vetedge-frontdesk-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
	.vetedge-frontdesk-filters { grid-template-columns: 1fr; }
	.vetedge-frontdesk-detail dl { grid-template-columns: 1fr; gap: .15rem; }
	.vetedge-frontdesk-detail dd { margin-bottom: .65rem; }
}
</style>
