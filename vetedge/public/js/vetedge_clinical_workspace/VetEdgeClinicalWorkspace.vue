<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/app/vetedge-clinical-workspace"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Veterinary Clinical Care"
					:title="pageTitle"
					:subtitle="pageSubtitle"
					:action-label="headerActionLabel"
					@action="handleHeaderAction"
				/>
			</template>

			<nav class="vetedge-clinical-tabs" aria-label="Clinical workspace sections">
				<button
					v-for="option in tabOptions"
					:key="option.value"
					type="button"
					:class="['vetedge-clinical-tab', { 'is-active': tab === option.value }]"
					@click="changeTab(option.value)"
				>
					<strong>{{ option.label }}</strong>
					<span>{{ option.description }}</span>
				</button>
			</nav>

			<section v-if="showSummary" class="vetedge-clinical-summary" aria-label="Clinical summary">
				<EdgeStatCard label="Active Consultations" :value="summary.active_consultations || 0" icon="stethoscope" />
				<EdgeStatCard label="Awaiting Payment" :value="summary.awaiting_payment || 0" icon="wallet" />
				<EdgeStatCard label="Pending Dispensary" :value="summary.pending_dispensary || 0" icon="inventory" />
				<EdgeStatCard label="Vitals Today" :value="summary.today_vitals || 0" icon="pulse" />
			</section>

			<template #filters>
				<EdgeFilterBar v-if="listMode && tab !== 'history'" :title="tab === 'consultations' ? 'Find consultations' : 'Find vital signs'">
					<div class="vetedge-clinical-filters">
						<label class="vetedge-clinical-filter vetedge-clinical-filter--search">
							<span>Search</span>
							<input
								v-model.trim="filters.search"
								type="search"
								class="form-control"
								:placeholder="tab === 'consultations' ? 'Patient, owner, complaint or consultation' : 'Patient, consultation or recorder'"
								@keyup.enter="applyFilters"
							/>
						</label>
						<label v-if="tab === 'consultations'" class="vetedge-clinical-filter">
							<span>Status</span>
							<select v-model="filters.status" class="form-control">
								<option value="">All statuses</option>
								<option v-for="status in consultationStatuses" :key="status" :value="status">{{ status }}</option>
							</select>
						</label>
						<EdgeLinkField
							:model-value="filters.branch"
							label="Branch"
							placeholder="All permitted branches"
							:searcher="(query) => filterLinkSearch('service_branch', query)"
							@update:model-value="(value) => setFilter('branch', value)"
						/>
						<EdgeLinkField
							:model-value="filters.patient"
							label="Patient"
							placeholder="All patients"
							:searcher="(query) => filterLinkSearch('patient', query)"
							@update:model-value="(value) => setFilter('patient', value)"
						/>
						<EdgeLinkField
							v-if="tab === 'consultations'"
							:model-value="filters.practitioner"
							label="Practitioner"
							placeholder="All Veterinary Doctors"
							:searcher="(query) => filterLinkSearch('consulting_practitioner', query)"
							@update:model-value="(value) => setFilter('practitioner', value)"
						/>
						<EdgeLinkField
							v-if="tab === 'vitals'"
							:model-value="filters.consultation"
							label="Consultation"
							placeholder="All consultations"
							:searcher="(query) => filterLinkSearch('consultation', query)"
							@update:model-value="(value) => setFilter('consultation', value)"
						/>
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>

				<EdgeFilterBar v-else-if="tab === 'history'" title="Patient medical history">
					<div class="vetedge-clinical-filters vetedge-clinical-filters--history">
						<EdgeLinkField
							:model-value="historyFilters.patient"
							label="Patient"
							placeholder="Select a patient"
							:searcher="(query) => filterLinkSearch('patient', query)"
							@update:model-value="setHistoryPatient"
						/>
						<label class="vetedge-clinical-filter">
							<span>From Date</span>
							<input v-model="historyFilters.from_date" type="date" class="form-control" />
						</label>
						<label class="vetedge-clinical-filter">
							<span>To Date</span>
							<input v-model="historyFilters.to_date" type="date" class="form-control" />
						</label>
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading || !historyFilters.patient" @click="loadHistory">
							Load History
						</button>
					</template>
				</EdgeFilterBar>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading Veterinary clinical workspace..." :skeleton="true" />
			<EdgeErrorState
				v-else-if="error"
				title="The Veterinary clinical workspace could not load"
				:message="error"
				action-label="Try again"
				@retry="reloadCurrentView"
			/>

			<template v-else-if="listMode && tab === 'consultations'">
				<EdgeDataTable
					:columns="definitions.consultations?.columns || consultationColumns"
					:rows="consultationList.rows || []"
					:actions="openAction"
					empty-title="No matching consultations"
					empty-description="Change the filters or create a new consultation."
					@row-click="openConsultationRow"
					@action="handleConsultationRowAction"
				>
					<template #footer>
						<span>Showing {{ firstVisible(consultationList) }}–{{ lastVisible(consultationList) }} of {{ consultationList.total || 0 }}</span>
						<div class="vetedge-clinical-pagination">
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious(consultationList)" @click="previousPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext(consultationList)" @click="nextPage">Next</button>
						</div>
					</template>
				</EdgeDataTable>
			</template>

			<template v-else-if="listMode && tab === 'vitals'">
				<EdgeDataTable
					:columns="definitions.vitals?.columns || vitalsColumns"
					:rows="vitalsList.rows || []"
					:actions="openAction"
					empty-title="No matching vital signs"
					empty-description="Change the filters or record new vital signs."
					@row-click="openVitalsRow"
					@action="handleVitalsRowAction"
				>
					<template #footer>
						<span>Showing {{ firstVisible(vitalsList) }}–{{ lastVisible(vitalsList) }} of {{ vitalsList.total || 0 }}</span>
						<div class="vetedge-clinical-pagination">
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious(vitalsList)" @click="previousPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext(vitalsList)" @click="nextPage">Next</button>
						</div>
					</template>
				</EdgeDataTable>
			</template>

			<template v-else-if="documentMode && documentReady">
				<EdgeWorkflowBar
					:state="document.state || (document.is_new ? 'New' : 'Draft')"
					:docstatus="document.docstatus || 0"
					:dirty="dirty"
					:saving="saving"
					:can-save="canSave"
					:can-delete="false"
					:transitions="tab === 'consultations' ? document.transitions || [] : []"
					@save="saveDocument"
					@transition="requestTransition"
					@back="backToList"
				/>

				<section v-if="tab === 'consultations' && document.actions?.length" class="vetedge-clinical-action-rail" aria-label="Consultation actions">
					<button
						v-for="action in document.actions"
						:key="action.key"
						type="button"
						:class="['edge-button', action.primary ? 'edge-button--primary' : '']"
						:disabled="actionBusy"
						@click="handleConsultationAction(action)"
					>
						{{ action.label }}
					</button>
				</section>

				<section v-if="tab === 'consultations'" class="vetedge-clinical-context-strip">
					<div><span>Patient</span><strong>{{ model.patient || '—' }}</strong></div>
					<div><span>Owner</span><strong>{{ model.primary_owner || '—' }}</strong></div>
					<div><span>Branch</span><strong>{{ model.service_branch || '—' }}</strong></div>
					<div><span>Payment</span><strong>{{ model.payment_status || 'Not Billed' }}</strong></div>
					<div><span>Dispensary</span><strong>{{ model.dispensary_status || 'Not Required' }}</strong></div>
				</section>

				<EdgeDocumentForm
					:schema="document.schema || { tabs: [] }"
					:model-value="model"
					:errors="fieldErrors"
					:readonly="!canEdit"
					:link-searcher="linkSearch"
					:child-link-searcher="childLinkSearch"
					@update:model-value="onModelUpdate"
					@change="onDocumentChange"
					@search-options="onSearchOption"
				/>

				<section v-if="tab === 'consultations' && !document.is_new" class="vetedge-clinical-related">
					<div class="vetedge-clinical-related__header">
						<div>
							<h3>Related Clinical Activity</h3>
							<p>Read-only records created through existing VetEdge services.</p>
						</div>
						<button type="button" class="edge-button edge-button--compact" @click="reloadDocument">Refresh</button>
					</div>
					<div class="vetedge-clinical-related__grid">
						<article>
							<h4>Latest Vitals</h4>
							<p v-if="!document.related?.latest_vitals" class="text-muted">No vitals recorded.</p>
							<dl v-else>
								<dt>Recorded</dt><dd>{{ formatDateTime(document.related.latest_vitals.recorded_on) }}</dd>
								<dt>Weight</dt><dd>{{ valueOrDash(document.related.latest_vitals.weight) }}</dd>
								<dt>Temperature</dt><dd>{{ valueOrDash(document.related.latest_vitals.temperature) }}</dd>
							</dl>
						</article>
						<article>
							<h4>Lab Orders</h4>
							<p v-if="!document.related?.lab_orders?.length" class="text-muted">No linked lab orders.</p>
							<button v-for="row in document.related?.lab_orders || []" :key="row.name" type="button" class="vetedge-clinical-record-link" @click="openDoc('Veterinary Lab Order', row.name)">
								<span>{{ row.lab_order_title || row.name }}</span><small>{{ row.status }}</small>
							</button>
						</article>
						<article>
							<h4>Vaccinations</h4>
							<p v-if="!document.related?.vaccinations?.length" class="text-muted">No linked vaccinations.</p>
							<button v-for="row in document.related?.vaccinations || []" :key="row.name" type="button" class="vetedge-clinical-record-link" @click="openDoc('Veterinary Vaccination Record', row.name)">
								<span>{{ row.vaccination_title || row.vaccine || row.name }}</span><small>{{ row.status }}</small>
							</button>
						</article>
						<article>
							<h4>Hospitalisation</h4>
							<p v-if="!document.related?.hospitalisations?.length" class="text-muted">No linked hospitalisation.</p>
							<button v-for="row in document.related?.hospitalisations || []" :key="row.name" type="button" class="vetedge-clinical-record-link" @click="openDoc('Veterinary Hospitalisation', row.name)">
								<span>{{ row.name }}</span><small>{{ row.status }}</small>
							</button>
						</article>
					</div>
				</section>
			</template>

			<template v-else-if="tab === 'history'">
				<EdgeEmptyState
					v-if="!historyFilters.patient"
					title="Choose a patient"
					description="Select a patient to review consultations, vital signs, diagnoses, treatment, laboratory and vaccination history."
				/>
				<EdgeEmptyState
					v-else-if="!historyLoaded"
					title="Medical history not loaded"
					description="Apply the patient and date filters to load the medical history."
					action-label="Load History"
					@action="loadHistory"
				/>
				<template v-else>
					<section class="vetedge-history-hero">
						<div>
							<span>Patient Medical History</span>
							<h2>{{ history.summary?.patient_name || history.patient }}</h2>
							<p>{{ history.summary?.species || 'Species not set' }} · {{ history.summary?.breed || 'Breed not set' }} · {{ history.summary?.default_branch || 'No default branch' }}</p>
						</div>
						<button type="button" class="edge-button" @click="openDoc('Veterinary Patient', history.patient)">Open Patient</button>
					</section>
					<section class="vetedge-clinical-summary">
						<EdgeStatCard label="Consultations" :value="history.consultations?.length || 0" icon="stethoscope" />
						<EdgeStatCard label="Diagnosis Entries" :value="history.diagnoses?.length || 0" icon="clipboard" />
						<EdgeStatCard label="Treatment Entries" :value="history.treatments?.length || 0" icon="prescription" />
						<EdgeStatCard label="Latest Weight" :value="valueOrDash(history.summary?.latest_weight)" icon="scale" />
					</section>

					<section class="vetedge-history-section">
						<h3>Consultation Timeline</h3>
						<EdgeDataTable :columns="historyConsultationColumns" :rows="history.consultations || []" :actions="openHistoryConsultationAction" empty-title="No consultation history" @action="openHistoryConsultation" />
					</section>
					<section class="vetedge-history-two-column">
						<div class="vetedge-history-section">
							<h3>Vital Signs</h3>
							<EdgeDataTable :columns="historyVitalsColumns" :rows="history.vitals || []" empty-title="No vital signs in this range" compact />
						</div>
						<div class="vetedge-history-section">
							<h3>Latest Trends</h3>
							<div class="vetedge-history-trends">
								<div v-for="trend in trendSummaries" :key="trend.key">
									<span>{{ trend.label }}</span><strong>{{ trend.latest }}</strong><small>{{ trend.points }} readings</small>
								</div>
							</div>
						</div>
					</section>
					<section class="vetedge-history-section">
						<h3>Diagnoses</h3>
						<EdgeDataTable :columns="historyDiagnosisColumns" :rows="history.diagnoses || []" empty-title="No diagnoses in this range" compact />
					</section>
					<section class="vetedge-history-section">
						<h3>Treatments</h3>
						<EdgeDataTable :columns="historyTreatmentColumns" :rows="history.treatments || []" empty-title="No treatment plan entries" compact />
					</section>
					<section class="vetedge-history-two-column">
						<div class="vetedge-history-section">
							<h3>Laboratory</h3>
							<EdgeDataTable :columns="historyLabColumns" :rows="history.labs || []" empty-title="No lab history" compact />
						</div>
						<div class="vetedge-history-section">
							<h3>Vaccinations</h3>
							<EdgeDataTable :columns="historyVaccinationColumns" :rows="history.vaccinations || []" empty-title="No vaccination history" compact />
						</div>
					</section>
				</template>
			</template>

			<EdgeEmptyState v-else title="Clinical record unavailable" description="Return to the list and choose another record." action-label="Back to list" @action="backToList" />
		</EdgePageLayout>

		<EdgeModal
			:open="actionDialog.open"
			:title="actionDialog.title"
			:subtitle="actionDialog.subtitle"
			:busy="actionBusy"
			@close="closeActionDialog"
		>
			<div class="vetedge-clinical-action-form">
				<template v-if="actionDialog.kind === 'info'">
					<dl class="vetedge-clinical-info-list">
						<template v-for="entry in actionDialog.entries" :key="entry.label">
							<dt>{{ entry.label }}</dt><dd>{{ entry.value || '—' }}</dd>
						</template>
					</dl>
				</template>

				<template v-else-if="actionDialog.kind === 'follow_up'">
					<label><span>Appointment Date / Time</span><input v-model="actionDialog.values.appointment_datetime" type="datetime-local" class="form-control" required /></label>
					<label><span>Notes</span><textarea v-model="actionDialog.values.notes" class="form-control" rows="4"></textarea></label>
				</template>

				<template v-else-if="actionDialog.kind === 'lab'">
					<div class="vetedge-clinical-choice-list">
						<label v-for="test in actionDialog.options.lab_tests || []" :key="test.name || test.value">
							<input v-model="actionDialog.values.lab_tests" type="checkbox" :value="test.name || test.value" />
							<span><strong>{{ test.test_name || test.label || test.name }}</strong><small>{{ test.default_rate ? `Default rate: ${test.default_rate}` : '' }}</small></span>
						</label>
					</div>
					<label><span>Sample / Request Notes</span><textarea v-model="actionDialog.values.sample_notes" class="form-control" rows="4"></textarea></label>
				</template>

				<template v-else-if="actionDialog.kind === 'vaccination'">
					<label><span>Vaccine</span><select v-model="actionDialog.values.vaccine" class="form-control" required><option value="">Select vaccine</option><option v-for="vaccine in actionDialog.options.vaccines || []" :key="vaccine.name" :value="vaccine.name">{{ vaccine.vaccine_name || vaccine.name }}</option></select></label>
					<div class="vetedge-clinical-action-grid">
						<label><span>Dose</span><input v-model="actionDialog.values.dose" class="form-control" /></label>
						<label><span>Route</span><input v-model="actionDialog.values.route" class="form-control" /></label>
						<label><span>Administered On</span><input v-model="actionDialog.values.administered_on" type="datetime-local" class="form-control" /></label>
						<label><span>Next Due Date</span><input v-model="actionDialog.values.next_due_date" type="date" class="form-control" /></label>
						<label><span>Rate</span><input v-model.number="actionDialog.values.rate" type="number" min="0" step="0.01" class="form-control" /></label>
					</div>
					<label><span>Notes</span><textarea v-model="actionDialog.values.notes" class="form-control" rows="3"></textarea></label>
					<label class="vetedge-clinical-check"><input v-model="actionDialog.values.create_invoice" type="checkbox" :true-value="1" :false-value="0" /><span>Create or update billing session invoice</span></label>
				</template>

				<template v-else-if="actionDialog.kind === 'dispensary'">
					<p class="vetedge-clinical-notice">Confirming may create a submitted Material Issue through the existing dispensary service. FEFO batch allocation and stock validation remain server controlled.</p>
					<div v-for="(row, index) in actionDialog.values.dispensed_items || []" :key="row.planned_treatment_row || index" class="vetedge-clinical-dispensary-row">
						<div><strong>{{ row.item }}</strong><small>{{ row.treatment_type || 'Treatment item' }} · Planned {{ row.planned_qty }} {{ row.uom || '' }}</small></div>
						<label><span>Dispensed Qty</span><input v-model.number="row.dispensed_qty" type="number" min="0.0001" step="0.01" class="form-control" /></label>
						<label><span>Notes</span><input v-model="row.notes" class="form-control" /></label>
					</div>
				</template>

				<template v-else-if="actionDialog.kind === 'cancellation'">
					<p :class="['vetedge-clinical-notice', actionDialog.options.can_cancel ? 'is-safe' : 'is-blocked']">{{ actionDialog.options.message || (actionDialog.options.can_cancel ? 'This consultation can be cancelled safely.' : 'Financial or operational records must be resolved first.') }}</p>
					<div v-if="actionDialog.options.warnings?.length"><h4>Warnings</h4><ul><li v-for="warning in actionDialog.options.warnings" :key="String(warning)">{{ warning.message || warning }}</li></ul></div>
					<div v-if="actionDialog.options.blockers?.length"><h4>Blockers</h4><ul><li v-for="blocker in actionDialog.options.blockers" :key="String(blocker)">{{ blocker.message || blocker }}</li></ul></div>
					<p v-if="!actionDialog.options.can_cancel" class="text-muted">Use the dedicated Cancellation Resolution workflow. It remains native because it controls invoice credit notes, payment allocations and other accounting-safe resolution choices.</p>
				</template>

				<template v-else>
					<p>{{ actionDialog.message || 'Continue with this clinical action?' }}</p>
				</template>
			</div>
			<template #footer>
				<button type="button" class="edge-button" :disabled="actionBusy" @click="closeActionDialog">Close</button>
				<button v-if="actionDialog.kind === 'cancellation' && !actionDialog.options.can_cancel" type="button" class="edge-button edge-button--primary" :disabled="actionBusy" @click="openCancellationResolution">Open Resolution</button>
				<button v-else-if="actionDialog.kind !== 'info'" type="button" :class="['edge-button', actionDialog.danger ? 'edge-button--danger' : 'edge-button--primary']" :disabled="actionBusy || !actionFormValid" @click="executeActionDialog">
					{{ actionBusy ? 'Working…' : actionDialog.confirmLabel || 'Continue' }}
				</button>
			</template>
		</EdgeModal>
	</EdgeAppShell>
</template>
<script>
import controller from "./clinical_workspace_controller";
export default controller;
</script>

<style scoped>
.vetedge-clinical-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }
.vetedge-clinical-tab { border: 1px solid var(--edge-border); border-radius: 10px; background: var(--edge-surface); padding: 12px 14px; text-align: left; color: var(--edge-text); }
.vetedge-clinical-tab strong, .vetedge-clinical-tab span { display: block; }
.vetedge-clinical-tab span { margin-top: 3px; color: var(--edge-text-muted); font-size: 12px; }
.vetedge-clinical-tab.is-active { border-color: var(--edge-primary); box-shadow: inset 3px 0 0 var(--edge-primary); }
.vetedge-clinical-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.vetedge-clinical-filters { display: grid; grid-template-columns: minmax(220px, 1.4fr) repeat(4, minmax(170px, 1fr)); gap: 12px; align-items: end; }
.vetedge-clinical-filters--history { grid-template-columns: minmax(260px, 1.5fr) repeat(2, minmax(170px, 1fr)); }
.vetedge-clinical-filter { display: flex; flex-direction: column; gap: 5px; }
.vetedge-clinical-filter span { color: var(--edge-text-muted); font-size: 12px; font-weight: 600; }
.vetedge-clinical-pagination { display: flex; gap: 8px; }
.vetedge-clinical-action-rail { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px; border: 1px solid var(--edge-border); border-radius: 10px; background: var(--edge-surface); margin-bottom: 12px; }
.vetedge-clinical-context-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
.vetedge-clinical-context-strip div { border: 1px solid var(--edge-border); border-radius: 8px; padding: 9px 10px; background: var(--edge-bg); min-width: 0; }
.vetedge-clinical-context-strip span, .vetedge-clinical-context-strip strong { display: block; overflow-wrap: anywhere; }
.vetedge-clinical-context-strip span { color: var(--edge-text-muted); font-size: 11px; }
.vetedge-clinical-context-strip strong { margin-top: 3px; font-size: 13px; }
.vetedge-clinical-related { margin-top: 16px; border: 1px solid var(--edge-border); border-radius: 10px; padding: 14px; background: var(--edge-surface); }
.vetedge-clinical-related__header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; margin-bottom: 12px; }
.vetedge-clinical-related__header h3, .vetedge-clinical-related__header p { margin: 0; }
.vetedge-clinical-related__header p { color: var(--edge-text-muted); font-size: 12px; margin-top: 3px; }
.vetedge-clinical-related__grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.vetedge-clinical-related article { border: 1px solid var(--edge-border); border-radius: 8px; padding: 10px; min-width: 0; }
.vetedge-clinical-related h4 { margin: 0 0 8px; font-size: 13px; }
.vetedge-clinical-related dl, .vetedge-clinical-info-list { display: grid; grid-template-columns: minmax(100px, .7fr) 1fr; gap: 6px 10px; margin: 0; }
.vetedge-clinical-related dt, .vetedge-clinical-info-list dt { color: var(--edge-text-muted); font-size: 12px; }
.vetedge-clinical-related dd, .vetedge-clinical-info-list dd { margin: 0; overflow-wrap: anywhere; }
.vetedge-clinical-record-link { width: 100%; display: flex; justify-content: space-between; gap: 8px; border: 0; border-top: 1px solid var(--edge-border); background: transparent; padding: 7px 0; text-align: left; }
.vetedge-clinical-record-link small { color: var(--edge-text-muted); }
.vetedge-history-hero { display: flex; justify-content: space-between; gap: 16px; align-items: center; border: 1px solid var(--edge-border); border-radius: 10px; padding: 16px; background: var(--edge-surface); margin-bottom: 14px; }
.vetedge-history-hero span { color: var(--edge-primary); text-transform: uppercase; font-size: 11px; font-weight: 700; letter-spacing: .06em; }
.vetedge-history-hero h2, .vetedge-history-hero p { margin: 0; }
.vetedge-history-hero p { color: var(--edge-text-muted); margin-top: 4px; }
.vetedge-history-section { border: 1px solid var(--edge-border); border-radius: 10px; background: var(--edge-surface); padding: 14px; margin-bottom: 14px; min-width: 0; }
.vetedge-history-section h3 { margin: 0 0 10px; font-size: 15px; }
.vetedge-history-two-column { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.vetedge-history-trends { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.vetedge-history-trends div { border: 1px solid var(--edge-border); border-radius: 8px; padding: 10px; background: var(--edge-bg); }
.vetedge-history-trends span, .vetedge-history-trends strong, .vetedge-history-trends small { display: block; }
.vetedge-history-trends span, .vetedge-history-trends small { color: var(--edge-text-muted); font-size: 11px; }
.vetedge-history-trends strong { font-size: 18px; margin: 2px 0; }
.vetedge-clinical-action-form { display: flex; flex-direction: column; gap: 12px; }
.vetedge-clinical-action-form label { display: flex; flex-direction: column; gap: 5px; }
.vetedge-clinical-action-form label > span { color: var(--edge-text-muted); font-size: 12px; font-weight: 600; }
.vetedge-clinical-action-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.vetedge-clinical-choice-list { display: grid; gap: 8px; max-height: 300px; overflow: auto; }
.vetedge-clinical-choice-list label { flex-direction: row; align-items: flex-start; border: 1px solid var(--edge-border); border-radius: 8px; padding: 9px; }
.vetedge-clinical-choice-list span, .vetedge-clinical-choice-list small { display: block; }
.vetedge-clinical-choice-list small { color: var(--edge-text-muted); }
.vetedge-clinical-check { flex-direction: row !important; align-items: center; }
.vetedge-clinical-dispensary-row { display: grid; grid-template-columns: 1.4fr .6fr 1fr; gap: 10px; align-items: end; border: 1px solid var(--edge-border); border-radius: 8px; padding: 10px; }
.vetedge-clinical-dispensary-row strong, .vetedge-clinical-dispensary-row small { display: block; }
.vetedge-clinical-dispensary-row small { color: var(--edge-text-muted); margin-top: 3px; }
.vetedge-clinical-notice { border-radius: 8px; padding: 10px 12px; background: var(--edge-bg); border: 1px solid var(--edge-border); }
.vetedge-clinical-notice.is-safe { background: #ecfdf3; border-color: #a6f4c5; }
.vetedge-clinical-notice.is-blocked { background: #fff7ed; border-color: #fed7aa; }
@media (max-width: 1100px) {
	.vetedge-clinical-summary, .vetedge-clinical-related__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.vetedge-clinical-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.vetedge-clinical-context-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 767px) {
	.vetedge-clinical-tabs, .vetedge-clinical-summary, .vetedge-clinical-filters, .vetedge-clinical-filters--history, .vetedge-clinical-context-strip, .vetedge-clinical-related__grid, .vetedge-history-two-column, .vetedge-clinical-action-grid, .vetedge-clinical-dispensary-row { grid-template-columns: 1fr; }
	.vetedge-history-hero, .vetedge-clinical-related__header { flex-direction: column; align-items: stretch; }
}
</style>
