<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/desk/vetedge-hospitalisation-operations"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Hospital & Services"
					:title="episode.title || episode.name || 'Hospitalisation Episode'"
					:subtitle="episodeSubtitle"
					action-label="Back to Hospitalisation Operations"
					@action="backToOperations"
				/>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading Hospitalisation Episode..." :skeleton="true" />
			<EdgeErrorState
				v-else-if="error"
				title="Hospitalisation Episode could not load"
				:message="error"
				action-label="Try again"
				@retry="refreshEpisode"
			/>

			<div v-else-if="episode.name" class="hospitalisation-episode">
				<section class="episode-statusbar">
					<div class="episode-statuses">
						<EdgeStatusBadge :label="episode.status || 'Draft'" :status="episode.status || 'Draft'" />
						<span>Invoice: <strong>{{ episode.invoice_status || 'Not Invoiced' }}</strong></span>
						<span>Payment Gate: <strong>{{ episode.payment_gate_status || 'Not Checked' }}</strong></span>
						<span v-if="episode.capabilities?.dispensary_enabled && episode.signals?.pending_stock">Stock Pending: <strong>{{ episode.signals.pending_stock }}</strong></span>
						<span v-if="episode.signals?.pending_charges">Charges Pending: <strong>{{ episode.signals.pending_charges }}</strong></span>
					</div>
					<div class="episode-actions">
						<button type="button" class="edge-button" :disabled="busy" @click="refreshEpisode">Refresh</button>
						<button
							v-if="episode.capabilities?.can_open_native_form"
							type="button"
							class="edge-button"
							:disabled="busy"
							@click="openNativeForm"
						>Open Native Form</button>
						<button
							v-if="episode.capabilities?.can_admit"
							type="button"
							class="edge-button edge-button--primary"
							:disabled="busy || dirty"
							@click="admit"
						>Admit Patient</button>
					</div>
				</section>

				<div v-if="episode.payment_gate_message" class="episode-guidance">
					<strong>Payment guidance</strong>
					<span>{{ episode.payment_gate_message }}</span>
				</div>

				<nav class="episode-tabs" aria-label="Hospitalisation sections">
					<button
						v-for="tab in tabs"
						:key="tab.value"
						type="button"
						:class="['episode-tab', { 'is-active': activeTab === tab.value }]"
						@click="activeTab = tab.value"
					>
						<span>{{ tab.label }}</span>
						<small>{{ tab.description }}</small>
					</button>
				</nav>

				<section v-if="activeTab === 'overview'" class="episode-panel">
					<header class="episode-panel-header">
						<div>
							<h3>Episode Overview</h3>
							<p>Patient, owner and branch identity remain server-authoritative. Edit only operational episode context.</p>
						</div>
						<button
							v-if="episode.capabilities?.can_write && !closedEpisode"
							type="button"
							class="edge-button edge-button--primary"
							:disabled="busy || !dirty"
							@click="saveContext"
						>{{ busy ? 'Saving…' : 'Save Context' }}</button>
					</header>

					<div class="episode-grid">
						<EdgeInput :model-value="episode.patient_label || episode.patient" label="Patient" readonly />
						<EdgeInput :model-value="episode.owner_label || episode.owner" label="Pet Owner" readonly />
						<EdgeInput :model-value="episode.service_branch" label="Service Branch" readonly />
						<EdgeInput :model-value="episode.company" label="Company" readonly />
						<EdgeInput :model-value="episode.linked_consultation || 'Direct Admission'" label="Linked Consultation" readonly />
						<EdgeInput :model-value="formatDateTime(episode.admission_datetime)" label="Admission Date/Time" readonly />
						<EdgeLinkField
							:model-value="context.attending_veterinarian"
							:selected-label="context.attending_veterinarian_label"
							label="Attending Veterinarian"
							placeholder="Select veterinarian"
							:disabled="!canEditContext"
							:searcher="(query) => optionSearch('practitioner', query)"
							@update:model-value="setVeterinarian"
						/>
						<EdgeDropdown
							:model-value="context.care_level"
							label="Care Level"
							:disabled="!canEditContext"
							:options="careLevelOptions"
							@update:model-value="(value) => setContextField('care_level', value)"
						/>
						<EdgeDropdown
							:model-value="String(context.isolation_required || 0)"
							label="Isolation Required"
							:disabled="!canEditContext"
							:options="yesNoOptions"
							@update:model-value="(value) => setContextField('isolation_required', Number(value || 0))"
						/>
						<EdgeInput :model-value="episode.admitted_by_label || episode.admitted_by || 'Not admitted'" label="Admitted By" readonly />
						<EdgeTextarea
							class="episode-wide"
							:model-value="context.admission_reason"
							label="Admission Reason"
							:rows="4"
							:disabled="!canEditContext"
							@update:model-value="(value) => setContextField('admission_reason', value)"
						/>
					</div>
				</section>

				<section v-if="activeTab === 'clinical'" class="episode-panel">
					<header class="episode-panel-header">
						<div>
							<h3>Clinical Care</h3>
							<p>Clinical actions write through permission-aware APIs and preserve the existing Hospitalisation controller.</p>
						</div>
					</header>

					<div v-if="episode.capabilities?.can_add_clinical_activity" class="episode-action-grid">
						<button type="button" class="edge-button edge-button--primary" :disabled="busy || dirty" @click="openVitals">Add Vitals</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openVaccination">Add Vaccination</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openLab">Add Lab Order</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openActivity('Medication')">Add Medication</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openActivity('Fluid Therapy')">Add Fluid Therapy</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openActivity('Feeding')">Add Feeding</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openActivity('Nursing Note')">Add Nursing Note</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openActivity('Wound Care')">Add Wound Care</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openActivity('Procedure', true)">Add Procedure</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openActivity('Oxygen / Nebulisation')">Add Oxygen / Nebulisation</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openActivity('Owner Communication')">Add Owner Update</button>
						<button type="button" class="edge-button" :disabled="busy || dirty" @click="openActivity('Other')">Add Other Activity</button>
					</div>

					<div v-if="!(episode.activities || []).length" class="episode-empty">No Hospitalisation activities have been recorded.</div>
					<div v-else class="episode-list">
						<article v-for="row in episode.activities" :key="row.name" class="episode-list-row">
							<div class="episode-list-main">
								<div class="episode-list-heading">
									<strong>{{ row.activity_type }}</strong>
									<EdgeStatusBadge :label="row.billing_status || 'Not Billable'" :status="row.billing_status || 'Not Billable'" />
									<EdgeStatusBadge v-if="episode.capabilities?.dispensary_enabled && row.stock_affecting" :label="row.stock_status || 'Pending'" :status="row.stock_status || 'Pending'" />
								</div>
								<p>{{ row.clinical_notes || 'No clinical note.' }}</p>
								<small>{{ formatDateTime(row.activity_datetime) }} · {{ row.performed_by_label || row.performed_by || 'Unknown user' }}</small>
							</div>
							<div class="episode-list-meta">
								<strong v-if="row.item">{{ row.item_label || row.item }}</strong>
								<span v-if="row.item">{{ row.qty || 0 }} {{ row.uom || '' }}</span>
								<button v-if="row.linked_document" type="button" class="edge-button edge-button--compact" @click="openDocument(row.linked_doctype, row.linked_document)">Open Linked Record</button>
							</div>
						</article>
					</div>
				</section>

				<section v-if="activeTab === 'care'" class="episode-panel">
					<header class="episode-panel-header">
						<div><h3>Care Location & Stock</h3><p>Care location remains available independently; stock movement follows the clinic's Dispensary Flow setting.</p></div>
					</header>

					<div class="episode-two-column">
						<div class="episode-card">
							<h4>Care Location</h4>
							<div class="episode-kv"><span>Current</span><strong>{{ episode.care_location_label || episode.care_location || 'Not Assigned' }}</strong></div>
							<div class="episode-kv"><span>Status</span><strong>{{ episode.care_location_status || 'Not Assigned' }}</strong></div>
							<div class="episode-kv"><span>Type</span><strong>{{ episode.care_location_type || 'Not Assigned' }}</strong></div>
							<div class="episode-actions">
								<button v-if="episode.capabilities?.can_assign_care_location" type="button" class="edge-button edge-button--primary" :disabled="busy || dirty" @click="openCareLocation">Assign / Change</button>
								<button v-if="episode.capabilities?.can_release_care_location" type="button" class="edge-button" :disabled="busy || dirty" @click="releaseCareLocation">Release</button>
							</div>
						</div>

						<div class="episode-card">
							<h4>Stock Usage</h4>
							<template v-if="episode.capabilities?.dispensary_enabled">
								<div class="episode-kv"><span>Pending stock activities</span><strong>{{ episode.signals?.pending_stock || 0 }}</strong></div>
								<p>Preview stock availability and shortages before posting. Repeated posting remains protected by the existing stock service.</p>
								<div class="episode-actions">
									<button v-if="episode.capabilities?.can_preview_stock" type="button" class="edge-button" :disabled="busy || dirty" @click="previewStock">Preview Stock</button>
									<button v-if="episode.capabilities?.can_post_stock" type="button" class="edge-button edge-button--primary" :disabled="busy || dirty || !(episode.signals?.pending_stock)" @click="previewStock(true)">Post Stock Usage</button>
								</div>
							</template>
							<template v-else>
								<div class="episode-kv"><span>Dispensary Flow</span><strong>Off</strong></div>
								<p>Clinical and billing Items can still be recorded. VetEdge will not preview or post Hospitalisation stock while Dispensary Flow is disabled.</p>
							</template>
						</div>
					</div>

					<div v-if="episode.capabilities?.dispensary_enabled" class="episode-list">
						<article v-for="row in stockActivities" :key="row.name" class="episode-list-row">
							<div><strong>{{ row.activity_type }} · {{ row.item_label || row.item || 'Item not set' }}</strong><p>{{ row.stock_posting_message || row.clinical_notes || '' }}</p></div>
							<EdgeStatusBadge :label="row.stock_status || 'Pending'" :status="row.stock_status || 'Pending'" />
						</article>
					</div>
				</section>

				<section v-if="activeTab === 'billing'" class="episode-panel">
					<header class="episode-panel-header">
						<div><h3>Charges & Billing</h3><p>Hospitalisation charges remain governed by Billing Core and ERPNext invoice immutability.</p></div>
						<div class="episode-actions">
							<button type="button" class="edge-button" :disabled="busy" @click="openBilling">Billing & Payment</button>
							<button type="button" class="edge-button" :disabled="busy || dirty || !episode.capabilities?.can_bill" @click="checkPaymentGate">Check Payment Gate</button>
							<button type="button" class="edge-button" :disabled="busy || dirty" @click="viewChargeSummary">View Charge Summary</button>
							<button v-if="episode.capabilities?.can_generate_daily_charges" type="button" class="edge-button" :disabled="busy || dirty" @click="generateDailyCharges">Generate Daily Charges</button>
							<button type="button" class="edge-button" :disabled="busy || dirty || !episode.capabilities?.can_manage_charges" @click="buildCharges">Build Charge Sheet</button>
							<button type="button" class="edge-button edge-button--primary" :disabled="busy || dirty || !episode.capabilities?.can_bill" @click="syncInvoice">Sync Charges to Invoice</button>
						</div>
					</header>

					<div v-if="episode.capabilities?.daily_charges_enabled === false" class="episode-guidance">
						<strong>Daily charges are off</strong>
						<span>The clinic has disabled Hospitalisation Daily Charges in Veterinary Settings. Manual and activity-based charges remain available.</span>
					</div>

					<div class="episode-summary-grid">
						<div class="episode-card"><span>Invoice</span><strong>{{ episode.sales_invoice || 'Not created' }}</strong><small>{{ episode.invoice_status || 'Not Invoiced' }}</small></div>
						<div class="episode-card"><span>Grand Total</span><strong>{{ formatMoney(episode.invoice?.grand_total || chargeTotal) }}</strong><small>{{ episode.invoice?.currency || '' }}</small></div>
						<div class="episode-card"><span>Outstanding</span><strong>{{ formatMoney(episode.invoice?.outstanding_amount || 0) }}</strong><small>{{ episode.invoice?.status || episode.invoice_status || '' }}</small></div>
						<div class="episode-card"><span>Pending Charges</span><strong>{{ episode.signals?.pending_charges || 0 }}</strong><small>Charge sheet rows awaiting invoice sync</small></div>
					</div>

					<div v-if="!(episode.charge_items || []).length" class="episode-empty">No Hospitalisation charge items yet.</div>
					<div v-else class="episode-charge-table">
						<div class="episode-charge-head"><span>Charge</span><span>Qty</span><span>Rate</span><span>Amount</span><span>Status</span><span>Invoice</span><span>Action</span></div>
						<div v-for="row in episode.charge_items" :key="row.name" class="episode-charge-row">
							<div><strong>{{ row.item_name || row.item || row.activity_type }}</strong><small>{{ row.description || row.activity_type || '' }}</small></div>
							<span>{{ row.qty || 0 }} {{ row.uom || '' }}</span>
							<span>{{ formatMoney(row.rate) }}</span>
							<strong>{{ formatMoney(row.amount) }}</strong>
							<EdgeStatusBadge :label="row.billing_status || 'Pending Invoice'" :status="row.billing_status || 'Pending Invoice'" />
							<div class="episode-charge-invoice">
								<button v-if="row.sales_invoice" type="button" class="edge-button edge-button--compact" @click="openDocument('Sales Invoice', row.sales_invoice)">{{ row.sales_invoice }}</button>
								<span v-else>—</span>
								<small v-if="row.invoice_is_draft">Draft</small>
							</div>
							<div>
								<button v-if="row.editable" type="button" class="edge-button edge-button--compact" :disabled="busy" @click="openChargeEdit(row)">Edit</button>
								<span v-else class="episode-muted" :title="row.edit_block_reason || 'Read-only'">Read-only</span>
							</div>
						</div>
					</div>
				</section>

				<section v-if="activeTab === 'discharge'" class="episode-panel">
					<header class="episode-panel-header">
						<div><h3>Discharge</h3><p>Readiness, stock, charge and payment gates remain server-authoritative.</p></div>
						<div class="episode-actions">
							<button v-if="episode.capabilities?.can_check_discharge" type="button" class="edge-button" :disabled="busy || dirty" @click="checkDischargeReadiness">Check Readiness</button>
							<button v-if="episode.capabilities?.can_discharge" type="button" class="edge-button edge-button--primary" :disabled="busy || dirty" @click="openDischarge">Discharge Patient</button>
						</div>
					</header>

					<div v-if="dischargeReadiness" :class="['episode-guidance', dischargeReadiness.can_discharge ? 'is-success' : 'is-warning']">
						<strong>{{ dischargeReadiness.can_discharge ? 'Ready for discharge' : 'Discharge blockers remain' }}</strong>
						<span>{{ (dischargeReadiness.messages || []).join(' ') || dischargeReadiness.discharge_billing_status || '' }}</span>
						<div class="episode-readiness-grid">
							<span>Billable activities: <strong>{{ (dischargeReadiness.pending_billable_activities || []).length }}</strong></span>
							<span>Charge items: <strong>{{ (dischargeReadiness.pending_charge_items || []).length }}</strong></span>
							<span v-if="episode.capabilities?.dispensary_enabled">Stock activities: <strong>{{ (dischargeReadiness.pending_stock_activities || []).length }}</strong></span>
							<span>Billing: <strong>{{ dischargeReadiness.discharge_billing_status || 'Not Checked' }}</strong></span>
						</div>
					</div>

					<div v-if="closedEpisode" class="episode-card">
						<h4>Episode Closed</h4>
						<div class="episode-kv"><span>Status</span><strong>{{ episode.status }}</strong></div>
						<div class="episode-kv"><span>Discharged By</span><strong>{{ episode.discharged_by_label || episode.discharged_by || '—' }}</strong></div>
						<div class="episode-kv"><span>Discharge Date</span><strong>{{ formatDateTime(episode.discharge_datetime) || '—' }}</strong></div>
						<div class="episode-kv"><span>Condition</span><strong>{{ episode.condition_at_discharge || '—' }}</strong></div>
						<p><strong>Summary</strong><br>{{ episode.discharge_summary || 'No discharge summary recorded.' }}</p>
						<p v-if="episode.discharge_instructions"><strong>Instructions</strong><br>{{ episode.discharge_instructions }}</p>
					</div>
				</section>
			</div>
		</EdgePageLayout>

		<EdgeModal :open="activityDialog.open" :title="`Add ${activityDialog.type || 'Activity'}`" subtitle="Hospitalisation Clinical Care" :busy="busy" @close="closeActivity">
			<div class="episode-grid">
				<EdgeInput :model-value="activityDialog.datetime" type="datetime-local" label="Activity Date/Time" @update:model-value="(value) => activityDialog.datetime = value" />
				<EdgeLinkField :model-value="activityDialog.item" :selected-label="activityDialog.item_label" label="ERPNext Item" :placeholder="activityRequiresItem ? 'Required for this activity' : 'Optional ERPNext Item'" :searcher="(query) => optionSearch('item', query)" @update:model-value="selectActivityItem" />
				<EdgeInput :model-value="activityDialog.qty" type="number" min="0.001" step="0.001" label="Quantity" @update:model-value="(value) => activityDialog.qty = value" />
				<EdgeInput :model-value="activityDialog.uom" label="UOM" readonly />
				<EdgeDropdown :model-value="String(activityDialog.billable || 0)" label="Billable" :options="yesNoOptions" @update:model-value="(value) => activityDialog.billable = Number(value || 0)" />
				<EdgeDropdown v-if="episode.capabilities?.dispensary_enabled" :model-value="String(activityDialog.stock_affecting || 0)" label="Stock Affecting" :options="yesNoOptions" @update:model-value="(value) => activityDialog.stock_affecting = Number(value || 0)" />
				<EdgeInput :model-value="activityDialog.rate" label="Resolved Rate" readonly description="Pricing is resolved server-side when the charge sheet is built." />
				<EdgeTextarea class="episode-wide" :model-value="activityDialog.notes" label="Clinical Notes" :rows="5" @update:model-value="(value) => activityDialog.notes = value" />
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeActivity">Cancel</button><button type="button" class="edge-button edge-button--primary" :disabled="busy || (activityRequiresItem && !activityDialog.item)" @click="saveActivity">Add Activity</button></template>
		</EdgeModal>

		<EdgeModal :open="vitalsDialog.open" title="Add Vitals" subtitle="Hospitalisation Clinical Care" :busy="busy" @close="closeVitals">
			<div class="episode-grid">
				<EdgeInput :model-value="vitalsDialog.values.recorded_on" type="datetime-local" label="Recorded On" @update:model-value="(value) => setVital('recorded_on', value)" />
				<EdgeInput :model-value="vitalsDialog.values.temperature" type="number" step="0.1" label="Temperature" @update:model-value="(value) => setVital('temperature', value)" />
				<EdgeInput :model-value="vitalsDialog.values.weight" type="number" step="0.01" label="Weight" @update:model-value="(value) => setVital('weight', value)" />
				<EdgeInput :model-value="vitalsDialog.values.heart_rate" type="number" step="1" label="Heart Rate" @update:model-value="(value) => setVital('heart_rate', value)" />
				<EdgeInput :model-value="vitalsDialog.values.respiratory_rate" type="number" step="1" label="Respiratory Rate" @update:model-value="(value) => setVital('respiratory_rate', value)" />
				<EdgeDropdown :model-value="vitalsDialog.values.hydration_status" label="Hydration" :options="hydrationOptions" @update:model-value="(value) => setVital('hydration_status', value)" />
				<EdgeDropdown :model-value="vitalsDialog.values.pain_score" label="Pain Score" :options="painOptions" @update:model-value="(value) => setVital('pain_score', value)" />
				<EdgeTextarea class="episode-wide" :model-value="vitalsDialog.values.notes" label="Notes" :rows="4" @update:model-value="(value) => setVital('notes', value)" />
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeVitals">Cancel</button><button type="button" class="edge-button edge-button--primary" :disabled="busy" @click="saveVitals">Save Vitals</button></template>
		</EdgeModal>

		<EdgeModal :open="vaccinationDialog.open" title="Add Vaccination" subtitle="Hospitalisation Clinical Care" :busy="busy" @close="closeVaccination">
			<div class="episode-grid">
				<EdgeLinkField :model-value="vaccinationDialog.values.vaccine" label="Vaccine" placeholder="Select active vaccine" :searcher="(query) => optionSearch('vaccine', query)" @update:model-value="(value) => setVaccination('vaccine', value)" />
				<EdgeInput :model-value="vaccinationDialog.values.dose" label="Dose" @update:model-value="(value) => setVaccination('dose', value)" />
				<EdgeDropdown :model-value="vaccinationDialog.values.route" label="Route" :options="vaccinationRouteOptions" @update:model-value="(value) => setVaccination('route', value)" />
				<EdgeInput :model-value="vaccinationDialog.values.administered_on" type="datetime-local" label="Recorded On" @update:model-value="(value) => setVaccination('administered_on', value)" />
				<EdgeInput :model-value="vaccinationDialog.values.next_due_date" type="date" label="Next Due Date" @update:model-value="(value) => setVaccination('next_due_date', value)" />
				<EdgeDropdown :model-value="String(vaccinationDialog.values.billable)" label="Billable" :options="yesNoOptions" @update:model-value="(value) => setVaccination('billable', Number(value || 0))" />
				<EdgeDropdown v-if="episode.capabilities?.dispensary_enabled" :model-value="String(vaccinationDialog.values.stock_affecting)" label="Stock Affecting" :options="yesNoOptions" @update:model-value="(value) => setVaccination('stock_affecting', Number(value || 0))" />
				<EdgeTextarea class="episode-wide" :model-value="vaccinationDialog.values.notes" label="Notes" :rows="4" @update:model-value="(value) => setVaccination('notes', value)" />
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeVaccination">Cancel</button><button type="button" class="edge-button edge-button--primary" :disabled="busy || !vaccinationDialog.values.vaccine" @click="saveVaccination">Create Vaccination Record</button></template>
		</EdgeModal>

		<EdgeModal :open="labDialog.open" title="Add Lab Order" subtitle="Hospitalisation Clinical Care" :busy="busy" @close="closeLab">
			<div class="episode-stack">
				<p v-if="!episode.linked_consultation" class="episode-warning">This direct admission will create a Veterinary Lab Order and link it to this Hospitalisation. The Hospitalisation activity remains the episode timeline entry.</p>
				<div class="episode-inline-picker">
					<EdgeLinkField :model-value="labDialog.pending" label="Lab Test" placeholder="Search active lab tests" :searcher="searchLabTests" @update:model-value="(value) => labDialog.pending = value" />
					<button type="button" class="edge-button" :disabled="!labDialog.pending" @click="addSelectedLabTest">Add Test</button>
				</div>
				<div v-if="labDialog.selected.length" class="episode-chip-list">
					<button v-for="test in labDialog.selected" :key="test" type="button" class="episode-chip" @click="removeSelectedLabTest(test)">{{ labLabel(test) }} ×</button>
				</div>
				<EdgeTextarea :model-value="labDialog.sample_notes" label="Sample Notes" :rows="4" @update:model-value="(value) => labDialog.sample_notes = value" />
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeLab">Cancel</button><button type="button" class="edge-button edge-button--primary" :disabled="busy || !labDialog.selected.length" @click="saveLab">Create Lab Order</button></template>
		</EdgeModal>

		<EdgeModal :open="careDialog.open" title="Assign Care Location" subtitle="Hospitalisation Bed / Kennel Management" :busy="busy" @close="closeCareLocation">
			<div class="episode-stack">
				<EdgeLinkField :model-value="careDialog.care_location" label="Care Location" placeholder="Search available locations for this branch" :searcher="(query) => optionSearch('care_location', query)" @update:model-value="(value) => careDialog.care_location = value" />
				<EdgeTextarea :model-value="careDialog.notes" label="Assignment Notes" :rows="4" @update:model-value="(value) => careDialog.notes = value" />
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeCareLocation">Cancel</button><button type="button" class="edge-button edge-button--primary" :disabled="busy || !careDialog.care_location" @click="assignCareLocation">Assign</button></template>
		</EdgeModal>

		<EdgeModal :open="stockDialog.open" title="Stock Usage Preview" subtitle="Hospitalisation Stock Posting" :busy="busy" @close="closeStock">
			<div class="episode-stack">
				<div class="episode-readiness-grid">
					<span>Ready: <strong>{{ stockDialog.preview.to_post_count || 0 }}</strong></span>
					<span>Skipped: <strong>{{ stockDialog.preview.skipped_count || 0 }}</strong></span>
					<span>Blocked: <strong>{{ stockDialog.preview.blocked_count || 0 }}</strong></span>
					<span>Shortages: <strong>{{ stockDialog.preview.shortage_count || 0 }}</strong></span>
				</div>
				<article v-for="(row, index) in stockPreviewRows" :key="`${row.status}-${row.activity_row_name || row.item}-${index}`" class="episode-list-row">
					<div><strong>{{ row.status }} · {{ row.item_name || row.item || row.activity_type }}</strong><p>{{ row.message || row.warehouse || '' }}</p></div>
					<span>Required {{ row.required_qty || row.qty || 0 }} · Available {{ row.available_qty == null ? '—' : row.available_qty }}</span>
				</article>
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeStock">Close</button><button v-if="stockDialog.postRequested" type="button" class="edge-button edge-button--primary" :disabled="busy || !stockDialog.preview.can_post" @click="postStock">Confirm Post</button></template>
		</EdgeModal>

		<EdgeModal :open="chargeDialog.open" title="Edit Hospitalisation Charge" subtitle="Draft / Unsynced Charge" :busy="busy" @close="closeChargeEdit">
			<div class="episode-grid">
				<EdgeLinkField
					v-if="canEditChargeField('item')"
					:model-value="chargeDialog.item"
					:selected-label="chargeDialog.item_label"
					label="ERPNext Item"
					placeholder="Select Item"
					:searcher="(query) => optionSearch('item', query)"
					@update:model-value="selectChargeItem"
				/>
				<EdgeInput v-else :model-value="chargeDialog.item_label || chargeDialog.item" label="ERPNext Item" readonly />
				<EdgeInput :model-value="chargeDialog.qty" type="number" min="0.001" step="0.001" label="Quantity" :readonly="!canEditChargeField('qty')" @update:model-value="(value) => setChargeField('qty', value)" />
				<EdgeInput :model-value="chargeDialog.uom" label="UOM" :readonly="!canEditChargeField('uom')" @update:model-value="(value) => setChargeField('uom', value)" />
				<EdgeInput :model-value="chargeDialog.rate" type="number" min="0" step="0.01" label="Rate" :readonly="!canEditChargeField('rate')" @update:model-value="(value) => setChargeField('rate', value)" />
				<EdgeTextarea class="episode-wide" :model-value="chargeDialog.description" label="Description" :rows="3" :disabled="!canEditChargeField('description')" @update:model-value="(value) => setChargeField('description', value)" />
				<div v-if="chargeDialog.invoice_is_draft" class="episode-guidance episode-wide">
					<strong>Draft invoice linked</strong>
					<span>Saving changes updates the Hospitalisation charge only. Use Sync Charges to Invoice afterwards to refresh the draft Sales Invoice.</span>
				</div>
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeChargeEdit">Cancel</button><button type="button" class="edge-button edge-button--primary" :disabled="busy || !chargeDialog.item" @click="saveChargeEdit">Save Charge</button></template>
		</EdgeModal>

		<EdgeModal :open="invoiceConfirmation.open" title="Confirm Invoice Sync" subtitle="Hospitalisation Billing" :busy="busy" @close="closeInvoiceConfirmation">
			<p>{{ invoiceConfirmation.message }}</p>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeInvoiceConfirmation">Cancel</button><button type="button" class="edge-button edge-button--danger" :disabled="busy" @click="confirmInvoiceSync">Continue</button></template>
		</EdgeModal>

		<EdgeModal :open="dischargeDialog.open" title="Discharge Patient" subtitle="Hospitalisation Discharge" :busy="busy" @close="closeDischarge">
			<div class="episode-stack">
				<EdgeDropdown :model-value="dischargeDialog.values.condition_at_discharge" label="Condition at Discharge" :options="dischargeConditionOptions" @update:model-value="(value) => setDischarge('condition_at_discharge', value)" />
				<EdgeTextarea :model-value="dischargeDialog.values.discharge_summary" label="Discharge Summary" :rows="5" @update:model-value="(value) => setDischarge('discharge_summary', value)" />
				<EdgeTextarea :model-value="dischargeDialog.values.discharge_instructions" label="Discharge Instructions" :rows="4" @update:model-value="(value) => setDischarge('discharge_instructions', value)" />
				<EdgeInput :model-value="dischargeDialog.values.follow_up_date" type="date" label="Follow Up Date" @update:model-value="(value) => setDischarge('follow_up_date', value)" />
				<EdgeTextarea :model-value="dischargeDialog.values.follow_up_notes" label="Follow Up Notes" :rows="3" @update:model-value="(value) => setDischarge('follow_up_notes', value)" />
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeDischarge">Cancel</button><button type="button" class="edge-button edge-button--primary" :disabled="busy || !dischargeDialog.values.discharge_summary" @click="discharge">Discharge</button></template>
		</EdgeModal>
	</EdgeAppShell>
</template>

<script>
const API = Object.freeze({
	detail: 'vetedge.services.hospitalisation_episode.get_hospitalisation_episode',
	saveContext: 'vetedge.services.hospitalisation_episode.save_hospitalisation_episode_context',
	addActivity: 'vetedge.services.hospitalisation_episode.add_hospitalisation_activity',
	addVitals: 'vetedge.services.hospitalisation_episode.add_hospitalisation_vitals',
	addVaccination: 'vetedge.services.hospitalisation_episode.add_hospitalisation_vaccination',
	addLabOrder: 'vetedge.services.hospitalisation_episode.add_hospitalisation_lab_order',
	updateCharge: 'vetedge.services.hospitalisation_episode_policy.update_hospitalisation_charge_item',
	options: 'vetedge.services.hospitalisation_episode.search_hospitalisation_episode_options',
	itemContext: 'vetedge.services.hospitalisation_episode.get_hospitalisation_episode_item_context',
	action: 'vetedge.services.hospitalisation_episode.perform_hospitalisation_episode_action',
});

const CARE_LEVELS = ['Standard', 'Observation', 'Intensive Care', 'ICU', 'Isolation', 'Recovery'];
const ITEM_REQUIRED_ACTIVITY_TYPES = new Set(['Medication', 'Fluid Therapy']);
const toOptions = (values) => values.map((value) => ({ value, label: value }));
const yesNoOptions = [{ value: '0', label: 'No' }, { value: '1', label: 'Yes' }];
const blankEpisode = () => ({ name: '', status: '', activities: [], charge_items: [], signals: {}, capabilities: {}, invoice: {} });
const blankActivity = () => ({ open: false, type: 'Other', datetime: '', notes: '', item: '', item_label: '', qty: 1, uom: '', rate: '', billable: 0, stock_affecting: 0 });
const blankVitals = () => ({ open: false, values: {} });
const blankVaccination = () => ({ open: false, values: { vaccine: '', dose: '', route: '', administered_on: '', next_due_date: '', billable: 1, stock_affecting: 0, notes: '' } });
const blankLab = () => ({ open: false, pending: '', selected: [], sample_notes: '' });
const blankCare = () => ({ open: false, care_location: '', notes: '' });
const blankStock = () => ({ open: false, postRequested: false, preview: {} });
const blankCharge = () => ({ open: false, row_name: '', item: '', item_label: '', qty: 1, uom: '', rate: 0, description: '', editable_fields: [], invoice_is_draft: false });
const blankInvoiceConfirmation = () => ({ open: false, confirmation_type: '', message: '' });
const blankDischarge = () => ({ open: false, values: {} });

function call(method, args = {}) {
	return frappe.call({ method, args }).then((response) => response.message);
}
function errorMessage(error, fallback) {
	if (error?._server_messages) {
		try {
			const messages = JSON.parse(error._server_messages).map((value) => JSON.parse(value).message || value);
			if (messages.length) return messages.join(' ');
		} catch (_error) {}
	}
	return error?.message || error?.exc_type || fallback;
}
function serverDatetime(value) {
	return value ? String(value).replace('T', ' ') : value;
}
function currentLocalDatetime() {
	const now = new Date();
	const pad = (value) => String(value).padStart(2, '0');
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

export default {
	name: 'VetEdgeHospitalisationEpisode',
	data() {
		return {
			identity: window.frappe?.boot?.vetedge_ui_identity || {},
			loading: false,
			busy: false,
			error: '',
			episode: blankEpisode(),
			context: {},
			dirty: false,
			activeTab: 'overview',
			tabs: [
				{ value: 'overview', label: 'Overview', description: 'Patient and admission context' },
				{ value: 'clinical', label: 'Clinical Care', description: 'Vitals, medication and activities' },
				{ value: 'care', label: 'Care & Stock', description: 'Location and stock usage' },
				{ value: 'billing', label: 'Charges & Billing', description: 'Charges, invoice and payment' },
				{ value: 'discharge', label: 'Discharge', description: 'Readiness and discharge summary' },
			],
			careLevelOptions: toOptions(CARE_LEVELS),
			yesNoOptions,
			hydrationOptions: toOptions(['Normal', 'Mild Dehydration', 'Moderate Dehydration', 'Severe Dehydration']),
			painOptions: toOptions(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10']),
			vaccinationRouteOptions: toOptions(['Oral', 'Subcutaneous', 'Intramuscular', 'Intranasal', 'Topical', 'Other']),
			dischargeConditionOptions: toOptions(['Recovered', 'Stable', 'Improved', 'Referred', 'Transferred', 'Died', 'Euthanised', 'Discharged Against Medical Advice']),
			activityDialog: blankActivity(),
			vitalsDialog: blankVitals(),
			vaccinationDialog: blankVaccination(),
			labDialog: blankLab(),
			careDialog: blankCare(),
			stockDialog: blankStock(),
			chargeDialog: blankCharge(),
			invoiceConfirmation: blankInvoiceConfirmation(),
			dischargeDialog: blankDischarge(),
			dischargeReadiness: null,
			labOptionCache: {},
		};
	},
	computed: {
		userName() { return window.frappe?.session?.user_fullname || window.frappe?.session?.user || ''; },
		branchName() { return this.episode.service_branch || ''; },
		episodeSubtitle() {
			return [this.episode.patient_label || this.episode.patient, this.episode.service_branch, this.episode.attending_veterinarian_label || this.episode.attending_veterinarian].filter(Boolean).join(' · ') || 'Operational hospital care episode';
		},
		closedEpisode() { return ['Discharged', 'Cancelled'].includes(this.episode.status); },
		canEditContext() { return Boolean(this.episode.capabilities?.can_write && !this.closedEpisode); },
		activityRequiresItem() {
			return Boolean(
				this.activityDialog.billable ||
				ITEM_REQUIRED_ACTIVITY_TYPES.has(this.activityDialog.type) ||
				(this.episode.capabilities?.dispensary_enabled && this.activityDialog.stock_affecting)
			);
		},
		stockActivities() {
			if (!this.episode.capabilities?.dispensary_enabled) return [];
			return (this.episode.activities || []).filter((row) => row.stock_affecting);
		},
		stockPreviewRows() {
			const preview = this.stockDialog.preview || {};
			return [
				...(preview.items || []).map((row) => ({ ...row, status: row.status || 'Ready' })),
				...(preview.blocked || []).map((row) => ({ ...row, status: row.status || 'Blocked' })),
				...(preview.skipped || []).map((row) => ({ ...row, status: row.status || 'Skipped' })),
			];
		},
		chargeTotal() { return (this.episode.charge_items || []).reduce((total, row) => total + Number(row.amount || 0), 0); },
	},
	async mounted() {
		const name = new URLSearchParams(window.location.search || '').get('name');
		if (name) await this.loadEpisode(name);
		else this.setRouteError(__('Select a Hospitalisation from Hospitalisation Operations.'));
	},
	methods: {
		setRouteError(message) { this.loading = false; this.error = message || __('Hospitalisation is required.'); },
		async loadEpisode(name) {
			this.loading = true; this.error = '';
			try {
				this.applyEpisode(await call(API.detail, { name }));
				window.history.replaceState({}, '', `/desk/vetedge-hospitalisation-episode?name=${encodeURIComponent(name)}`);
			} catch (error) { this.error = errorMessage(error, __('Unable to load Hospitalisation Episode.')); }
			finally { this.loading = false; }
		},
		async refreshEpisode() {
			if (!this.episode.name) {
				const name = new URLSearchParams(window.location.search || '').get('name');
				if (name) return this.loadEpisode(name);
				return;
			}
			if (this.dirty) {
				this.error = __('Save or discard context changes before refreshing.');
				return;
			}
			this.loading = true; this.error = '';
			try { this.applyEpisode(await call(API.detail, { name: this.episode.name })); }
			catch (error) { this.error = errorMessage(error, __('Unable to refresh Hospitalisation Episode.')); }
			finally { this.loading = false; }
		},
		applyEpisode(payload) {
			this.episode = { ...blankEpisode(), ...(payload || {}) };
			this.context = {
				attending_veterinarian: this.episode.attending_veterinarian || '',
				attending_veterinarian_label: this.episode.attending_veterinarian_label || '',
				admission_reason: this.episode.admission_reason || '',
				care_level: this.episode.care_level || 'Standard',
				isolation_required: Number(this.episode.isolation_required || 0),
			};
			this.dirty = false;
		},
		setContextField(field, value) { this.context[field] = value ?? ''; this.dirty = true; },
		setVeterinarian(value) { this.context.attending_veterinarian = value || ''; this.context.attending_veterinarian_label = ''; this.dirty = true; },
		async saveContext() {
			if (!this.episode.name || !this.dirty || this.busy) return;
			this.busy = true; this.error = '';
			try {
				const payload = await call(API.saveContext, { name: this.episode.name, values: this.context, modified: this.episode.modified });
				this.applyEpisode(payload);
				frappe.show_alert({ message: __('Hospitalisation context saved.'), indicator: 'green' });
			} catch (error) { this.error = errorMessage(error, __('Hospitalisation context could not be saved.')); }
			finally { this.busy = false; }
		},
		ensureActionReady() {
			if (!this.dirty) return true;
			this.error = __('Save Hospitalisation context changes before running an operational action.');
			return false;
		},
		async runAction(action, values = {}) {
			if (!this.episode.name || this.busy || !this.ensureActionReady()) return null;
			this.busy = true; this.error = '';
			try {
				const response = await call(API.action, { name: this.episode.name, action, values, modified: this.episode.modified });
				if (response?.episode) this.applyEpisode(response.episode);
				return response?.result || {};
			} catch (error) {
				this.error = errorMessage(error, __('Hospitalisation action failed.'));
				return null;
			} finally { this.busy = false; }
		},
		async admit() {
			const result = await this.runAction('admit');
			if (!result) return;
			if (result.message) frappe.msgprint({ message: result.message, indicator: result.can_proceed ? 'green' : 'orange' });
			if (!result.can_proceed && result.open_billing_modal) this.openBilling();
			else if (result.can_proceed) frappe.show_alert({ message: __('Patient admitted.'), indicator: 'green' });
		},
		openActivity(type, billable = false) {
			this.activityDialog = { ...blankActivity(), open: true, type, datetime: currentLocalDatetime(), billable: billable ? 1 : 0 };
		},
		closeActivity() { if (!this.busy) this.activityDialog = blankActivity(); },
		async selectActivityItem(value) {
			this.activityDialog.item = value || ''; this.activityDialog.item_label = '';
			if (!value) { this.activityDialog.uom = ''; this.activityDialog.rate = ''; return; }
			try {
				const context = await call(API.itemContext, { hospitalisation_name: this.episode.name, item: value });
				if (this.activityDialog.item !== value) return;
				this.activityDialog.item_label = context?.item_name || value;
				this.activityDialog.uom = context?.uom || '';
				this.activityDialog.rate = context?.rate || 0;
				if (this.episode.capabilities?.dispensary_enabled && context?.is_stock_item) this.activityDialog.stock_affecting = 1;
				if (Number(context?.rate || 0) > 0) this.activityDialog.billable = 1;
			} catch (error) { this.error = errorMessage(error, __('Item context could not be loaded.')); }
		},
		async saveActivity() {
			if (!this.activityDialog.type || this.busy || (this.activityRequiresItem && !this.activityDialog.item)) return;
			this.busy = true; this.error = '';
			try {
				const result = await call(API.addActivity, {
					hospitalisation_name: this.episode.name,
					activity_type: this.activityDialog.type,
					activity_datetime: serverDatetime(this.activityDialog.datetime),
					clinical_notes: this.activityDialog.notes,
					billable: this.activityDialog.billable,
					stock_affecting: this.episode.capabilities?.dispensary_enabled ? this.activityDialog.stock_affecting : 0,
					item: this.activityDialog.item,
					qty: this.activityDialog.qty,
					uom: this.activityDialog.uom,
					modified: this.episode.modified,
				});
				this.applyEpisode(result?.episode || this.episode);
				this.activityDialog = blankActivity();
				(result?.warnings || []).forEach((warning) => frappe.show_alert({ message: warning, indicator: 'orange' }));
				frappe.show_alert({ message: __('Hospitalisation activity added.'), indicator: 'green' });
			} catch (error) { this.error = errorMessage(error, __('Activity could not be added.')); }
			finally { this.busy = false; }
		},
		openVitals() { this.vitalsDialog = { open: true, values: { recorded_on: currentLocalDatetime() } }; },
		closeVitals() { if (!this.busy) this.vitalsDialog = blankVitals(); },
		setVital(field, value) { this.vitalsDialog.values = { ...this.vitalsDialog.values, [field]: value }; },
		async saveVitals() {
			this.busy = true; this.error = '';
			try {
				const values = { ...this.vitalsDialog.values, recorded_on: serverDatetime(this.vitalsDialog.values.recorded_on) };
				const result = await call(API.addVitals, { hospitalisation_name: this.episode.name, values, modified: this.episode.modified });
				this.applyEpisode(result?.episode || this.episode); this.vitalsDialog = blankVitals();
				frappe.show_alert({ message: result?.linked_record ? __('Vitals record created and linked.') : __('Vitals added.'), indicator: 'green' });
			} catch (error) { this.error = errorMessage(error, __('Vitals could not be added.')); }
			finally { this.busy = false; }
		},
		openVaccination() {
			const values = { ...blankVaccination().values, administered_on: currentLocalDatetime() };
			if (!this.episode.capabilities?.dispensary_enabled) values.stock_affecting = 0;
			this.vaccinationDialog = { ...blankVaccination(), open: true, values };
		},
		closeVaccination() { if (!this.busy) this.vaccinationDialog = blankVaccination(); },
		setVaccination(field, value) { this.vaccinationDialog.values = { ...this.vaccinationDialog.values, [field]: value }; },
		async saveVaccination() {
			this.busy = true; this.error = '';
			try {
				const values = {
					...this.vaccinationDialog.values,
					administered_on: serverDatetime(this.vaccinationDialog.values.administered_on),
					stock_affecting: this.episode.capabilities?.dispensary_enabled ? this.vaccinationDialog.values.stock_affecting : 0,
				};
				const result = await call(API.addVaccination, { hospitalisation_name: this.episode.name, values, modified: this.episode.modified });
				this.applyEpisode(result?.episode || this.episode); this.vaccinationDialog = blankVaccination();
				if (result?.warning) frappe.show_alert({ message: result.warning, indicator: 'orange' });
				frappe.show_alert({ message: result?.linked_record ? __('Vaccination Record created and linked.') : __('Vaccination added.'), indicator: 'green' });
			} catch (error) { this.error = errorMessage(error, __('Vaccination could not be added.')); }
			finally { this.busy = false; }
		},
		openLab() { this.labDialog = { ...blankLab(), open: true }; this.labOptionCache = {}; },
		closeLab() { if (!this.busy) this.labDialog = blankLab(); },
		async searchLabTests(query) {
			const options = await this.optionSearch('lab_test', query);
			options.forEach((option) => { this.labOptionCache[option.value] = option; });
			return options;
		},
		addSelectedLabTest() {
			const value = this.labDialog.pending;
			if (!value || this.labDialog.selected.includes(value)) { this.labDialog.pending = ''; return; }
			this.labDialog.selected.push(value); this.labDialog.pending = '';
		},
		removeSelectedLabTest(value) { this.labDialog.selected = this.labDialog.selected.filter((item) => item !== value); },
		labLabel(value) { return this.labOptionCache[value]?.label || value; },
		async saveLab() {
			this.busy = true; this.error = '';
			try {
				const result = await call(API.addLabOrder, { hospitalisation_name: this.episode.name, lab_tests: this.labDialog.selected, sample_notes: this.labDialog.sample_notes, modified: this.episode.modified });
				this.applyEpisode(result?.episode || this.episode); this.labDialog = blankLab();
				frappe.show_alert({ message: result?.linked_order ? __('Lab Order created and linked.') : __('Lab tests added.'), indicator: 'green' });
			} catch (error) { this.error = errorMessage(error, __('Lab tests could not be added.')); }
			finally { this.busy = false; }
		},
		openCareLocation() { this.careDialog = { ...blankCare(), open: true, care_location: this.episode.care_location || '' }; },
		closeCareLocation() { if (!this.busy) this.careDialog = blankCare(); },
		async assignCareLocation() {
			const values = { care_location: this.careDialog.care_location, notes: this.careDialog.notes };
			this.careDialog = blankCare();
			const result = await this.runAction('assign_location', values);
			if (result?.message) frappe.show_alert({ message: result.message, indicator: 'green' });
		},
		async releaseCareLocation() {
			if (!window.confirm(__('Release the assigned care location?'))) return;
			const result = await this.runAction('release_location', {});
			if (result?.message) frappe.show_alert({ message: result.message, indicator: 'green' });
		},
		async previewStock(postRequested = false) {
			if (!this.episode.capabilities?.dispensary_enabled) return;
			const result = await this.runAction('stock_preview');
			if (!result || result.disabled) return;
			this.stockDialog = { open: true, postRequested, preview: result };
		},
		closeStock() { if (!this.busy) this.stockDialog = blankStock(); },
		async postStock() {
			if (!this.episode.capabilities?.dispensary_enabled) return;
			this.stockDialog.open = false;
			const result = await this.runAction('post_stock');
			if (result) frappe.msgprint({ title: __('Stock Usage'), message: `${__('Posted')}: ${result.posted_count || 0}<br>${__('Skipped')}: ${result.skipped_count || 0}<br>${__('Blocked')}: ${result.blocked_count || 0}`, indicator: result.blocked_count ? 'orange' : 'green' });
		},
		async generateDailyCharges() {
			if (!this.episode.capabilities?.can_generate_daily_charges) return;
			const result = await this.runAction('generate_daily_charges', {
				care_level: this.episode.care_level || this.context.care_level || 'Standard',
			});
			if (!result) return;
			frappe.msgprint({
				title: __('Daily Hospitalisation Charges'),
				message: [
					result.message || __('Daily hospitalisation charges generated.'),
					`${__('Created')}: ${result.created || 0}`,
					`${__('Updated')}: ${result.updated || 0}`,
					`${__('Skipped Existing')}: ${result.skipped_existing || 0}`,
					`${__('Missing Price')}: ${result.missing_price || 0}`,
					`${__('Total')}: ${this.formatMoney(result.total_amount || 0)}`,
				].join('<br>'),
				indicator: result.missing_price ? 'orange' : 'green',
			});
		},
		async buildCharges() {
			const result = await this.runAction('build_charges');
			if (result) frappe.show_alert({ message: __(`Created ${result.created || 0} charge item(s).`), indicator: 'green' });
		},
		async checkPaymentGate() {
			const result = await this.runAction('check_payment_gate');
			if (!result) return;
			frappe.msgprint({
				title: __('Payment Gate'),
				message: result.message || (result.can_proceed ? __('Payment gate passed.') : __('Payment gate checked.')),
				indicator: result.can_proceed ? 'green' : 'orange',
			});
			if (!result.can_proceed && result.open_billing_modal) this.openBilling();
		},
		async viewChargeSummary() {
			if (!this.episode.name || this.busy || !this.ensureActionReady()) return;
			this.busy = true; this.error = '';
			try {
				this.applyEpisode(await call(API.detail, { name: this.episode.name }));
				const rows = this.episode.charge_items || [];
				const amountFor = (row) => Number(row.amount || (Number(row.qty || 1) * Number(row.rate || 0)) || 0);
				const totalPending = rows.filter((row) => !['Invoiced', 'Cancelled'].includes(row.billing_status)).reduce((total, row) => total + amountFor(row), 0);
				const totalInvoiced = rows.filter((row) => row.billing_status === 'Invoiced').reduce((total, row) => total + amountFor(row), 0);
				const totalCancelled = rows.filter((row) => row.billing_status === 'Cancelled').reduce((total, row) => total + amountFor(row), 0);
				const missingPriceCount = rows.filter((row) => !['Invoiced', 'Cancelled'].includes(row.billing_status) && row.item && (Number(row.rate || 0) <= 0 || amountFor(row) <= 0)).length;
				const notBillableCount = (this.episode.activities || []).filter((row) => !Number(row.billable || 0)).length;
				frappe.msgprint({
					title: __('Charge Summary'),
					message: [
						`${__('Total Hospitalisation Charges')}: ${this.formatMoney(totalPending + totalInvoiced + totalCancelled)}`,
						`${__('Pending Charges')}: ${this.formatMoney(totalPending)}`,
						`${__('Invoiced Charges')}: ${this.formatMoney(totalInvoiced)}`,
						`${__('Cancelled')}: ${this.formatMoney(totalCancelled)}`,
						`${__('Missing Price')}: ${missingPriceCount}`,
						`${__('Not Billable Activities')}: ${notBillableCount}`,
						`${__('Linked Invoice')}: ${this.episode.sales_invoice || '—'}`,
					].join('<br>'),
				});
			} catch (error) { this.error = errorMessage(error, __('Charge summary could not be loaded.')); }
			finally { this.busy = false; }
		},
		openChargeEdit(row) {
			if (!row?.editable || this.busy) return;
			this.chargeDialog = {
				open: true,
				row_name: row.name,
				item: row.item || '',
				item_label: row.item_name || row.item || '',
				qty: row.qty || 1,
				uom: row.uom || '',
				rate: row.rate || 0,
				description: row.description || '',
				editable_fields: row.editable_fields || [],
				invoice_is_draft: Boolean(row.invoice_is_draft),
			};
		},
		closeChargeEdit() { if (!this.busy) this.chargeDialog = blankCharge(); },
		canEditChargeField(field) { return (this.chargeDialog.editable_fields || []).includes(field); },
		setChargeField(field, value) {
			if (!this.canEditChargeField(field)) return;
			this.chargeDialog[field] = value;
		},
		async selectChargeItem(value) {
			if (!this.canEditChargeField('item')) return;
			this.chargeDialog.item = value || '';
			this.chargeDialog.item_label = '';
			if (!value) return;
			try {
				const context = await call(API.itemContext, { hospitalisation_name: this.episode.name, item: value });
				if (this.chargeDialog.item !== value) return;
				this.chargeDialog.item_label = context?.item_name || value;
				if (this.canEditChargeField('uom')) this.chargeDialog.uom = context?.uom || this.chargeDialog.uom;
				if (this.canEditChargeField('rate')) this.chargeDialog.rate = context?.rate || 0;
			} catch (error) { this.error = errorMessage(error, __('Charge Item context could not be loaded.')); }
		},
		async saveChargeEdit() {
			if (!this.chargeDialog.row_name || !this.chargeDialog.item || this.busy) return;
			const values = {};
			for (const field of this.chargeDialog.editable_fields || []) values[field] = this.chargeDialog[field];
			this.busy = true; this.error = '';
			try {
				const result = await call(API.updateCharge, {
					hospitalisation_name: this.episode.name,
					charge_row_name: this.chargeDialog.row_name,
					values,
					modified: this.episode.modified,
				});
				this.applyEpisode(result?.episode || this.episode);
				this.chargeDialog = blankCharge();
				frappe.show_alert({ message: result?.message || __('Hospitalisation charge updated.'), indicator: result?.invoice_sync_required ? 'orange' : 'green' });
			} catch (error) { this.error = errorMessage(error, __('Hospitalisation charge could not be updated.')); }
			finally { this.busy = false; }
		},
		async syncInvoice(values = {}) {
			const result = await this.runAction('sync_invoice', values);
			if (!result) return;
			if (result.requires_confirmation) {
				this.invoiceConfirmation = {
					open: true,
					confirmation_type: result.confirmation_type,
					message: result.confirmation_type === 'remove_empty_draft_invoice'
						? __('Removing these charges will leave the draft invoice empty. Remove the empty draft invoice?')
						: __('This operation requires confirmation before changing the existing unpaid invoice. Continue?'),
				};
				return;
			}
			if (result.blocked) frappe.msgprint({ title: __('Invoice Sync Blocked'), message: result.message || __('Invoice sync was blocked.'), indicator: 'red' });
			else frappe.show_alert({ message: result.message || __('Hospitalisation charges synced to invoice.'), indicator: 'green' });
		},
		closeInvoiceConfirmation() { if (!this.busy) this.invoiceConfirmation = blankInvoiceConfirmation(); },
		async confirmInvoiceSync() {
			const confirmation_type = this.invoiceConfirmation.confirmation_type;
			this.invoiceConfirmation = blankInvoiceConfirmation();
			await this.syncInvoice({ confirm: 1, confirmation_type });
		},
		openBilling() {
			if (!window.vetedgeBillingModal?.open || !this.episode.name) {
				frappe.msgprint(__('Billing modal helper is not available. Please refresh the page.'));
				return;
			}
			const view = this;
			window.vetedgeBillingModal.open({
				doc: { doctype: 'Veterinary Hospitalisation', name: this.episode.name },
				is_new: () => false,
				is_dirty: () => view.dirty,
				save: () => view.saveContext(),
				reload_doc: () => view.refreshEpisode(),
			});
		},
		async checkDischargeReadiness() {
			const result = await this.runAction('check_discharge_readiness');
			if (result) this.dischargeReadiness = result;
		},
		openDischarge() {
			this.dischargeDialog = {
				open: true,
				values: {
					condition_at_discharge: this.episode.condition_at_discharge || '',
					discharge_summary: this.episode.discharge_summary || '',
					discharge_instructions: this.episode.discharge_instructions || '',
					follow_up_date: this.episode.follow_up_date || '',
					follow_up_notes: this.episode.follow_up_notes || '',
				},
			};
		},
		closeDischarge() { if (!this.busy) this.dischargeDialog = blankDischarge(); },
		setDischarge(field, value) { this.dischargeDialog.values = { ...this.dischargeDialog.values, [field]: value }; },
		async discharge() {
			const values = { ...this.dischargeDialog.values };
			this.dischargeDialog = blankDischarge();
			const result = await this.runAction('discharge', { discharge_details: values });
			if (!result) return;
			if (result.blocked) {
				frappe.msgprint({ title: __('Discharge Blocked'), message: result.message || __('Hospitalisation is not ready for discharge.'), indicator: 'orange' });
				if (result.readiness) this.dischargeReadiness = result.readiness;
				if (result.open_stock_action && this.episode.capabilities?.dispensary_enabled) this.previewStock(true);
				return;
			}
			frappe.show_alert({ message: __('Hospitalisation discharged.'), indicator: 'green' });
			this.dischargeReadiness = result.readiness || this.dischargeReadiness;
		},
		async optionSearch(field, txt) {
			if (!this.episode.name) return [];
			try { return (await call(API.options, { hospitalisation_name: this.episode.name, field, txt, start: 0, page_length: 20 })) || []; }
			catch (_error) { return []; }
		},
		backToOperations() { window.location.assign('/desk/vetedge-hospitalisation-operations'); },
		openNativeForm() { if (this.episode.name) frappe.set_route('Form', 'Veterinary Hospitalisation', this.episode.name); },
		openDocument(doctype, name) { if (doctype && name) frappe.set_route('Form', doctype, name); },
		openRoute(route) {
			if (!route) return;
			const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.('navigation:vetedge');
			if (adapter?.open?.(route) === true) return;
			window.location.assign(route);
		},
		formatDateTime(value) { return value ? (frappe.datetime?.str_to_user?.(value) || String(value)) : ''; },
		formatMoney(value) {
			const currency = this.episode.invoice?.currency;
			if (typeof format_currency === 'function') return format_currency(Number(value || 0), currency);
			return Number(value || 0).toFixed(2);
		},
	},
};
</script>

<style scoped>
.hospitalisation-episode,.episode-stack,.episode-list{display:grid;gap:var(--edge-space-4,1rem)}
.episode-statusbar,.episode-panel-header{align-items:center;display:flex;gap:1rem;justify-content:space-between}
.episode-statusbar,.episode-panel,.episode-card,.episode-guidance{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-lg,1rem);padding:1rem}
.episode-statuses,.episode-actions,.episode-list-heading,.episode-chip-list{align-items:center;display:flex;flex-wrap:wrap;gap:.6rem}
.episode-tabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.6rem}
.episode-tab{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);color:var(--edge-color-ink-700,#334b61);display:grid;gap:.2rem;padding:.8rem;text-align:left}
.episode-tab.is-active{background:var(--edge-color-brand-50,#eef7ff);border-color:var(--edge-color-brand-500,#1677c8);color:var(--edge-color-brand-700,#0c4f87)}
.episode-tab small,.episode-panel-header p,.episode-card p,.episode-list-row p{color:var(--edge-color-ink-500,#617589);margin:0}
.episode-panel{display:grid;gap:1rem}.episode-panel h3,.episode-panel h4{margin:0}.episode-panel-header p{margin-top:.25rem}
.episode-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.episode-wide{grid-column:1/-1}
.episode-two-column{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.episode-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem}
.episode-card{display:grid;gap:.65rem}.episode-card>span{color:var(--edge-color-ink-500,#617589);font-size:.75rem}.episode-card>strong{font-size:1.2rem}.episode-card>small,.episode-muted{color:var(--edge-color-ink-500,#617589);font-size:.75rem}
.episode-kv{align-items:center;display:flex;gap:1rem;justify-content:space-between}.episode-kv span{color:var(--edge-color-ink-500,#617589)}
.episode-guidance{display:grid;gap:.35rem}.episode-guidance.is-success{border-color:color-mix(in srgb,var(--edge-color-accent,#22a06b) 45%,var(--edge-color-border,#dfe6ec))}.episode-guidance.is-warning{border-color:#e0a100}.episode-warning{background:#fff8e1;border:1px solid #ecd17a;border-radius:.75rem;padding:.75rem}
.episode-action-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem}
.episode-list-row{align-items:center;background:var(--edge-color-surface-soft,#f9fbfd);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:.75rem;display:flex;gap:1rem;justify-content:space-between;padding:.85rem}.episode-list-main{display:grid;gap:.35rem;min-width:0}.episode-list-main small{color:var(--edge-color-ink-500,#617589)}.episode-list-meta{align-items:flex-end;display:grid;gap:.3rem;text-align:right}
.episode-empty{border:1px dashed var(--edge-color-border,#dfe6ec);border-radius:.75rem;color:var(--edge-color-ink-500,#617589);padding:1.25rem;text-align:center}
.episode-charge-table{border:1px solid var(--edge-color-border,#dfe6ec);border-radius:.75rem;overflow:hidden}.episode-charge-head,.episode-charge-row{align-items:center;display:grid;gap:.75rem;grid-template-columns:minmax(12rem,2fr) .7fr 1fr 1fr 1fr 1.1fr .7fr;padding:.75rem}.episode-charge-head{background:var(--edge-color-surface-muted,#f5f8fc);font-size:.75rem;font-weight:700}.episode-charge-row{border-top:1px solid var(--edge-color-border,#dfe6ec)}.episode-charge-row>div{display:grid;gap:.2rem}.episode-charge-row small{color:var(--edge-color-ink-500,#617589)}.episode-charge-invoice{align-items:start;display:grid;gap:.2rem}
.episode-readiness-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem;margin-top:.5rem}.episode-inline-picker{align-items:end;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.75rem}.episode-chip{background:var(--edge-color-brand-50,#eef7ff);border:1px solid var(--edge-color-brand-200,#b8dcff);border-radius:999px;color:var(--edge-color-brand-700,#0c4f87);cursor:pointer;padding:.35rem .7rem}
@media(max-width:1100px){.episode-tabs{grid-template-columns:repeat(3,minmax(0,1fr))}.episode-action-grid,.episode-summary-grid,.episode-readiness-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.episode-charge-head,.episode-charge-row{grid-template-columns:minmax(10rem,2fr) .6fr 1fr 1fr 1fr 1fr}.episode-charge-head>span:nth-child(6),.episode-charge-row>:nth-child(6){display:none}}
@media(max-width:720px){.episode-statusbar,.episode-panel-header,.episode-list-row{align-items:stretch;flex-direction:column}.episode-tabs,.episode-grid,.episode-two-column,.episode-action-grid,.episode-summary-grid,.episode-readiness-grid{grid-template-columns:minmax(0,1fr)}.episode-wide{grid-column:auto}.episode-list-meta{align-items:start;text-align:left}.episode-charge-table{overflow-x:auto}.episode-charge-head,.episode-charge-row{min-width:50rem}.episode-inline-picker{grid-template-columns:minmax(0,1fr)}}
</style>
