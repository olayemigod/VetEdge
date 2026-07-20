<template>
	<EdgeModal
		:open="openState"
		:title="modalTitle"
		:subtitle="modalSubtitle"
		size="lg"
		:busy="saving"
		@close="close"
	>
		<div v-if="loading" class="vetedge-appointment-flow-state">Loading appointment form...</div>
		<div v-else>
			<div v-if="error" class="vetedge-appointment-flow-error" role="alert">{{ error }}</div>

			<form v-show="screen === 'appointment'" class="vetedge-appointment-flow-form" @submit.prevent="submitAppointment">
				<div class="vetedge-appointment-flow-grid">
					<EdgeLinkField
						v-model="form.patient"
						:selected-label="labels.patient"
						label="Veterinary Patient"
						placeholder="Search by patient name, ID, microchip or owner"
						:searcher="searchPatient"
						:creator="bootstrap.can_create_patient ? createPatientFromQuery : null"
						:can-create="bootstrap.can_create_patient"
						:context="{ branch: form.branch, company: bootstrap.active_company }"
						create-label="Create New Veterinary Patient"
						required
						@select="onPatientSelected"
						@clear="clearPatient"
						@search-error="handleFieldError"
					/>

					<label class="vetedge-appointment-flow-field vetedge-appointment-flow-owner-summary">
						<span>Pet Owner</span>
						<input :value="labels.owner || form.owner" class="form-control" placeholder="Automatically filled from the selected patient" readonly />
						<small>The owner is loaded from the selected Veterinary Patient record.</small>
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Company</span>
						<input :value="bootstrap.active_company" class="form-control" readonly />
						<small>Controlled by the active EdgeSuite company context.</small>
					</label>

					<EdgeLinkField
						v-model="form.branch"
						:selected-label="labels.branch"
						label="Branch"
						placeholder="Search permitted branches"
						:searcher="searchBranch"
						required
						@select="onBranchSelected"
						@clear="clearBranch"
						@search-error="handleFieldError"
					/>

					<EdgeLinkField
						v-model="form.practitioner"
						:selected-label="labels.practitioner"
						label="Veterinary Practitioner"
						placeholder="Search doctors available for this branch"
						:searcher="searchPractitioner"
						:context="{ branch: form.branch }"
						:disabled="!form.branch"
						required
						@select="onPractitionerSelected"
						@clear="clearPractitioner"
						@search-error="handleFieldError"
					/>

					<label class="vetedge-appointment-flow-field">
						<span>Appointment Date/Time <b>*</b></span>
						<input v-model="form.appointment_datetime" type="datetime-local" class="form-control" required />
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Appointment Type</span>
						<select v-model="form.appointment_type" class="form-control">
							<option v-for="type in bootstrap.appointment_types" :key="type" :value="type">{{ type }}</option>
						</select>
					</label>
				</div>

				<label class="vetedge-appointment-flow-field vetedge-appointment-flow-field--wide">
					<span>Notes</span>
					<textarea v-model.trim="form.notes" class="form-control" rows="3" placeholder="Reason for visit or front-desk notes"></textarea>
				</label>
				<p v-if="bootstrap.patient_create_warning" class="vetedge-appointment-flow-hint">{{ bootstrap.patient_create_warning }} Existing patients can still be booked.</p>
			</form>

			<form v-show="screen === 'patient'" class="vetedge-appointment-flow-form" @submit.prevent="savePatient">
				<div class="vetedge-appointment-flow-section-note">
					<strong>Patient registration</strong>
					<span>Complete the clinical identity fields now. Registration invoice and billing fields remain system-managed.</span>
				</div>
				<div class="vetedge-appointment-flow-grid">
					<label class="vetedge-appointment-flow-field">
						<span>Patient Name <b>*</b></span>
						<input v-model.trim="patientDraft.patient_name" class="form-control" required />
					</label>

					<EdgeLinkField
						v-model="patientDraft.primary_owner"
						:selected-label="patientLabels.owner"
						label="Pet Owner"
						placeholder="Search by owner name, phone or email"
						:searcher="searchOwner"
						:creator="bootstrap.can_create_owner ? createOwnerForPatientFromQuery : null"
						:can-create="bootstrap.can_create_owner"
						:context="{ company: bootstrap.active_company }"
						create-label="Create New Pet Owner"
						required
						@select="onPatientOwnerSelected"
						@clear="clearPatientOwner"
						@search-error="handleFieldError"
					/>

					<label class="vetedge-appointment-flow-field">
						<span>Company</span>
						<input :value="bootstrap.active_company" class="form-control" readonly />
					</label>

					<EdgeLinkField
						v-model="patientDraft.default_branch"
						:selected-label="patientLabels.branch"
						label="Default Branch"
						placeholder="Search permitted branches"
						:searcher="searchBranch"
						required
						@select="onPatientBranchSelected"
						@clear="clearPatientBranch"
						@search-error="handleFieldError"
					/>

					<EdgeLinkField
						v-model="patientDraft.species"
						:selected-label="patientLabels.species"
						label="Species"
						placeholder="Search species"
						:searcher="searchSpecies"
						required
						@select="onSpeciesSelected"
						@clear="clearSpecies"
						@search-error="handleFieldError"
					/>

					<EdgeLinkField
						v-model="patientDraft.breed"
						:selected-label="patientLabels.breed"
						label="Breed"
						placeholder="Search breeds for the selected species"
						:searcher="searchBreed"
						:context="{ species: patientDraft.species }"
						:disabled="!patientDraft.species"
						@select="onBreedSelected"
						@clear="clearBreed"
						@search-error="handleFieldError"
					/>

					<label class="vetedge-appointment-flow-field">
						<span>Sex</span>
						<select v-model="patientDraft.sex" class="form-control">
							<option value=""></option><option value="Male">Male</option><option value="Female">Female</option><option value="Unknown">Unknown</option>
						</select>
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Neuter Status</span>
						<select v-model="patientDraft.neuter_status" class="form-control">
							<option value=""></option><option value="Intact">Intact</option><option value="Neutered">Neutered</option><option value="Spayed">Spayed</option><option value="Unknown">Unknown</option>
						</select>
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Date of Birth</span>
						<input v-model="patientDraft.date_of_birth" :max="todayDate" type="date" class="form-control" />
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Age</span>
						<input :value="patientAge" class="form-control" placeholder="Calculated from Date of Birth" readonly />
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Baseline Weight</span>
						<input v-model="patientDraft.weight_baseline" type="number" min="0" step="0.001" class="form-control" />
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Colour / Markings</span>
						<input v-model.trim="patientDraft.color_markings" class="form-control" />
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Microchip ID</span>
						<input v-model.trim="patientDraft.microchip_id" class="form-control" />
					</label>

					<label class="vetedge-appointment-flow-field vetedge-appointment-flow-field--wide">
						<span>Emergency Contact</span>
						<input v-model.trim="patientDraft.emergency_contact" class="form-control" />
					</label>
				</div>
			</form>

			<form v-show="screen === 'owner'" class="vetedge-appointment-flow-form" @submit.prevent="saveOwner">
				<div class="vetedge-appointment-flow-grid">
					<label class="vetedge-appointment-flow-field"><span>Owner Name <b>*</b></span><input v-model.trim="ownerDraft.owner_name" class="form-control" required /></label>
					<label class="vetedge-appointment-flow-field"><span>Company</span><input :value="bootstrap.active_company" class="form-control" readonly /></label>
					<label class="vetedge-appointment-flow-field"><span>Mobile Number</span><input v-model.trim="ownerDraft.mobile_no" type="tel" class="form-control" /></label>
					<label class="vetedge-appointment-flow-field"><span>Email</span><input v-model.trim="ownerDraft.email_id" type="email" class="form-control" /></label>
					<label v-if="bootstrap.owner_loyalty_programs.length" class="vetedge-appointment-flow-field">
						<span>Loyalty Program <b v-if="bootstrap.owner_requires_loyalty_program">*</b></span>
						<select v-model="ownerDraft.loyalty_program" class="form-control" :required="bootstrap.owner_requires_loyalty_program">
							<option value="">Select Loyalty Program</option>
							<option v-for="program in bootstrap.owner_loyalty_programs" :key="program.value" :value="program.value">{{ program.label }}</option>
						</select>
						<small v-if="bootstrap.owner_requires_loyalty_program">More than one program applies. Select the correct one.</small>
					</label>
				</div>
				<p class="vetedge-appointment-flow-hint">Provide at least a mobile number or email. Existing owners are checked before creation.</p>
				<p v-if="bootstrap.owner_create_warning" class="vetedge-appointment-flow-hint">{{ bootstrap.owner_create_warning }}</p>
			</form>
		</div>

		<template #footer>
			<template v-if="screen === 'appointment'">
				<button type="button" class="edge-button" :disabled="saving" @click="close">Cancel</button>
				<button type="button" class="edge-button edge-button--primary" :disabled="saving || loading" @click="submitAppointment">{{ saving ? 'Creating...' : 'Create Appointment' }}</button>
			</template>
			<template v-else-if="screen === 'patient'">
				<button type="button" class="edge-button" :disabled="saving" @click="cancelPatientCreate">Back to Appointment</button>
				<button type="button" class="edge-button edge-button--primary" :disabled="saving" @click="savePatient">{{ saving ? 'Saving...' : 'Create Patient' }}</button>
			</template>
			<template v-else>
				<button type="button" class="edge-button" :disabled="saving" @click="cancelOwnerCreate">Back to Patient</button>
				<button type="button" class="edge-button edge-button--primary" :disabled="saving" @click="saveOwner">{{ saving ? 'Saving...' : 'Create Owner' }}</button>
			</template>
		</template>
	</EdgeModal>
</template>

<script>
function emptyForm() {
	return { owner: "", patient: "", branch: "", practitioner: "", appointment_datetime: "", appointment_type: "Consultation", notes: "" };
}
function emptyLabels() {
	return { owner: "", patient: "", branch: "", practitioner: "" };
}
function emptyPatientDraft() {
	return {
		patient_name: "", primary_owner: "", company: "", default_branch: "", species: "", breed: "", sex: "",
		neuter_status: "", date_of_birth: "", weight_baseline: "", color_markings: "", microchip_id: "", emergency_contact: "",
	};
}
function localDate(value) {
	if (!value) return null;
	const date = new Date(`${value}T00:00:00`);
	return Number.isNaN(date.getTime()) ? null : date;
}
function formatAgeUnit(value, unit) {
	return `${value} ${value === 1 ? unit : `${unit}s`}`;
}
function calculateAgeLabel(value) {
	const birthDate = localDate(value);
	const today = localDate(new Date().toISOString().slice(0, 10));
	if (!birthDate || !today || birthDate > today) return "";
	let years = today.getFullYear() - birthDate.getFullYear();
	let months = today.getMonth() - birthDate.getMonth();
	let days = today.getDate() - birthDate.getDate();
	if (days < 0) {
		months -= 1;
		days += new Date(today.getFullYear(), today.getMonth(), 0).getDate();
	}
	if (months < 0) {
		years -= 1;
		months += 12;
	}
	const parts = [];
	if (years) parts.push(formatAgeUnit(years, "year"));
	if (months) parts.push(formatAgeUnit(months, "month"));
	if (!parts.length) parts.push(formatAgeUnit(days, "day"));
	return parts.join(" ");
}

export default {
	name: "VetEdgeAppointmentFlowV2",
	emits: ["created"],
	data() {
		return {
			openState: false, screen: "appointment", loading: false, saving: false, error: "",
			bootstrap: {
				active_company: "", default_branch: "", appointment_types: ["Consultation", "Follow Up", "Vaccination", "Grooming", "Boarding", "Other"],
				can_create_owner: false, can_create_patient: false, can_create_appointment: false, owner_create_warning: "", patient_create_warning: "",
				owner_loyalty_programs: [], owner_requires_loyalty_program: false, owner_default_loyalty_program: "", company_currency: "",
			},
			form: emptyForm(), labels: emptyLabels(), ownerDraft: { owner_name: "", mobile_no: "", email_id: "", company: "", branch: "", loyalty_program: "" },
			patientDraft: emptyPatientDraft(), patientLabels: { owner: "", branch: "", species: "", breed: "" }, patientCreateResolve: null, ownerCreateResolve: null,
		};
	},
	computed: {
		modalTitle() {
			if (this.screen === "owner") return "Create Pet Owner";
			if (this.screen === "patient") return "Create Veterinary Patient";
			return "New Veterinary Appointment";
		},
		modalSubtitle() {
			if (this.screen === "owner") return "Create the owner and return directly to the patient registration.";
			if (this.screen === "patient") return "Complete the patient registration and return directly to the appointment.";
			return "Search the patient first. The linked owner is filled automatically.";
		},
		patientAge() { return calculateAgeLabel(this.patientDraft.date_of_birth); },
		todayDate() { return new Date().toISOString().slice(0, 10); },
	},
	methods: {
		async open() {
			this.resolvePatientCreate(null); this.resolveOwnerCreate(null); this.form = emptyForm(); this.labels = emptyLabels();
			this.patientDraft = emptyPatientDraft(); this.patientLabels = { owner: "", branch: "", species: "", breed: "" };
			this.screen = "appointment"; this.error = ""; this.openState = true; this.loading = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.get_appointment_form_bootstrap");
				this.bootstrap = { ...this.bootstrap, ...(response.message || {}) };
				if (this.bootstrap.default_branch) { this.form.branch = this.bootstrap.default_branch; this.labels.branch = this.bootstrap.default_branch; }
				if (!this.bootstrap.can_create_appointment) this.error = __("You do not have permission to create Veterinary Appointments.");
			} catch (error) { this.error = error?.message || __("The appointment form could not be loaded."); }
			finally { this.loading = false; }
		},
		close() { if (this.saving) return; this.resolveOwnerCreate(null); this.resolvePatientCreate(null); this.screen = "appointment"; this.openState = false; },
		resolvePatientCreate(value) { const resolve = this.patientCreateResolve; this.patientCreateResolve = null; if (resolve) resolve(value || null); },
		resolveOwnerCreate(value) { const resolve = this.ownerCreateResolve; this.ownerCreateResolve = null; if (resolve) resolve(value || null); },
		createPatientFromQuery(query) {
			if (!this.bootstrap.can_create_patient) { this.error = this.bootstrap.patient_create_warning || __("New patient registration is temporarily unavailable."); return Promise.resolve(null); }
			this.resolvePatientCreate(null); this.error = "";
			this.patientDraft = { ...emptyPatientDraft(), patient_name: query || "", company: this.bootstrap.active_company, default_branch: this.form.branch || this.bootstrap.default_branch || "" };
			this.patientLabels = { owner: "", branch: this.labels.branch || this.form.branch || this.bootstrap.default_branch || "", species: "", breed: "" };
			this.screen = "patient"; return new Promise((resolve) => { this.patientCreateResolve = resolve; });
		},
		createOwnerForPatientFromQuery(query) {
			if (!this.bootstrap.can_create_owner) { this.error = this.bootstrap.owner_create_warning || __("New Pet Owner creation is temporarily unavailable."); return Promise.resolve(null); }
			this.resolveOwnerCreate(null); this.error = "";
			this.ownerDraft = {
				owner_name: query || "", mobile_no: "", email_id: "", company: this.bootstrap.active_company,
				branch: this.form.branch || this.bootstrap.default_branch || "", loyalty_program: this.bootstrap.owner_default_loyalty_program || "",
			};
			this.screen = "owner"; return new Promise((resolve) => { this.ownerCreateResolve = resolve; });
		},
		cancelPatientCreate() { if (this.saving) return; this.resolvePatientCreate(null); this.error = ""; this.screen = "appointment"; },
		cancelOwnerCreate() { if (this.saving) return; this.resolveOwnerCreate(null); this.error = ""; this.screen = "patient"; },
		async searchLink(field, query, context = {}) {
			const response = await frappe.call("vetedge.services.appointment_edgeui.search_appointment_link", { field, txt: query, context, start: 0, page_length: 20 });
			return response.message || [];
		},
		searchPatient(query) { return this.searchLink("patient", query, { branch: this.form.branch, company: this.bootstrap.active_company }); },
		searchOwner(query) { return this.searchLink("owner", query, { company: this.bootstrap.active_company }); },
		searchBranch(query) { return this.searchLink("branch", query); },
		searchPractitioner(query) { return this.searchLink("practitioner", query, { branch: this.form.branch }); },
		searchSpecies(query) { return this.searchLink("species", query); },
		searchBreed(query) { return this.searchLink("breed", query, { species: this.patientDraft.species }); },
		async onPatientSelected(option) {
			this.error = ""; this.form.patient = option.value; this.labels.patient = option.label; this.form.owner = ""; this.labels.owner = "";
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.get_patient_selection_context", { patient: option.value, company: this.bootstrap.active_company });
				const context = response.message || {}; this.form.owner = context.primary_owner || ""; this.labels.owner = context.primary_owner_label || context.primary_owner || "";
				if (!this.form.branch && context.default_branch) { this.form.branch = context.default_branch; this.labels.branch = context.default_branch; }
				if (!this.form.owner) throw new Error(__("The selected patient does not have a linked Pet Owner."));
			} catch (error) { this.clearPatient(); this.error = error?.message || __("The patient could not be used for the active Company."); }
		},
		clearPatient() { this.form.patient = ""; this.labels.patient = ""; this.form.owner = ""; this.labels.owner = ""; },
		onBranchSelected(option) { const changed = Boolean(this.form.branch && this.form.branch !== option.value); this.form.branch = option.value; this.labels.branch = option.label; this.clearPractitioner(); if (changed) this.clearPatient(); },
		clearBranch() { this.form.branch = ""; this.labels.branch = ""; this.clearPractitioner(); this.clearPatient(); },
		onPractitionerSelected(option) { this.form.practitioner = option.value; this.labels.practitioner = option.label; },
		clearPractitioner() { this.form.practitioner = ""; this.labels.practitioner = ""; },
		onPatientOwnerSelected(option) { this.patientDraft.primary_owner = option.value; this.patientLabels.owner = option.label; },
		clearPatientOwner() { this.patientDraft.primary_owner = ""; this.patientLabels.owner = ""; },
		onPatientBranchSelected(option) { this.patientDraft.default_branch = option.value; this.patientLabels.branch = option.label; },
		clearPatientBranch() { this.patientDraft.default_branch = ""; this.patientLabels.branch = ""; },
		onSpeciesSelected(option) { this.patientDraft.species = option.value; this.patientLabels.species = option.label; this.clearBreed(); },
		clearSpecies() { this.patientDraft.species = ""; this.patientLabels.species = ""; this.clearBreed(); },
		onBreedSelected(option) { this.patientDraft.breed = option.value; this.patientLabels.breed = option.label; },
		clearBreed() { this.patientDraft.breed = ""; this.patientLabels.breed = ""; },
		handleFieldError(error) { this.error = error?.message || __("A linked record could not be loaded."); },
		async saveOwner() {
			this.error = "";
			if (!this.ownerDraft.owner_name || (!this.ownerDraft.mobile_no && !this.ownerDraft.email_id)) { this.error = __("Owner Name and either Mobile Number or Email are required."); return; }
			if (this.bootstrap.owner_requires_loyalty_program && !this.ownerDraft.loyalty_program) { this.error = __("Select a Loyalty Program for this Pet Owner."); return; }
			this.saving = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.create_appointment_owner", { values: { ...this.ownerDraft, company: this.bootstrap.active_company } });
				const created = response.message || null; this.screen = "patient"; await this.$nextTick(); this.resolveOwnerCreate(created);
			} catch (error) { this.error = error?.message || __("The owner could not be created."); }
			finally { this.saving = false; }
		},
		async savePatient() {
			this.error = "";
			if (!this.patientDraft.primary_owner || !this.patientDraft.default_branch || !this.patientDraft.patient_name || !this.patientDraft.species) { this.error = __("Patient Name, Pet Owner, Branch and Species are required."); return; }
			if (this.patientDraft.date_of_birth && !this.patientAge) { this.error = __("Date of Birth cannot be in the future."); return; }
			this.saving = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_patient_quick_create.create_full_appointment_patient", { values: { ...this.patientDraft, company: this.bootstrap.active_company } });
				const created = response.message || null; const selected = created ? { ...created, raw: { ...(created.raw || {}), primary_owner: this.patientDraft.primary_owner, primary_owner_label: this.patientLabels.owner || this.patientDraft.primary_owner, company: this.bootstrap.active_company, default_branch: this.patientDraft.default_branch } } : null;
				this.screen = "appointment"; await this.$nextTick(); this.resolvePatientCreate(selected);
			} catch (error) { this.error = error?.message || __("The patient could not be created."); }
			finally { this.saving = false; }
		},
		appointmentPayload() {
			const datetime = String(this.form.appointment_datetime || "").replace("T", " ");
			return { company: this.bootstrap.active_company, patient: this.form.patient, branch: this.form.branch, practitioner: this.form.practitioner, appointment_datetime: datetime.length === 16 ? `${datetime}:00` : datetime, appointment_type: this.form.appointment_type, notes: this.form.notes };
		},
		async submitAppointment() {
			this.error = "";
			if (!this.bootstrap.can_create_appointment) { this.error = __("You do not have permission to create Veterinary Appointments."); return; }
			if (!this.form.patient || !this.form.owner || !this.form.branch || !this.form.practitioner || !this.form.appointment_datetime) { this.error = __("Patient, linked Pet Owner, Branch, Practitioner and Appointment Date/Time are required."); return; }
			this.saving = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.create_edgeui_appointment", { values: this.appointmentPayload() }); const created = response.message || {};
				frappe.show_alert({ message: __("Veterinary Appointment created"), indicator: "green" }); this.$emit("created", created); this.openState = false;
			} catch (error) { this.error = error?.message || __("The Veterinary Appointment could not be created."); }
			finally { this.saving = false; }
		},
	},
};
</script>

<style scoped>
.vetedge-appointment-flow-form { display: grid; gap: 1rem; }
.vetedge-appointment-flow-grid { display: grid; gap: .9rem; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.vetedge-appointment-flow-field { display: grid; gap: .35rem; min-width: 0; }
.vetedge-appointment-flow-field > span { color: var(--edge-color-ink-700, #415469); font-size: .75rem; font-weight: 700; }
.vetedge-appointment-flow-field small { color: var(--edge-color-ink-500, #6b7d90); font-size: .7rem; }
.vetedge-appointment-flow-field--wide { grid-column: 1 / -1; }
.vetedge-appointment-flow-owner-summary input[readonly], .vetedge-appointment-flow-field input[readonly] { background: var(--edge-color-surface-soft, #f7fafc); }
.vetedge-appointment-flow-error { background: color-mix(in srgb, var(--edge-color-danger, #c53a3a) 10%, white); border: 1px solid color-mix(in srgb, var(--edge-color-danger, #c53a3a) 25%, white); border-radius: .7rem; color: var(--edge-color-danger, #a92f2f); font-size: .8rem; margin-bottom: 1rem; padding: .75rem .85rem; }
.vetedge-appointment-flow-state { color: var(--edge-color-ink-500, #6b7d90); padding: 2rem; text-align: center; }
.vetedge-appointment-flow-hint { color: var(--edge-color-ink-500, #6b7d90); font-size: .75rem; margin: 0; }
.vetedge-appointment-flow-section-note { background: var(--edge-color-surface-soft, #f7fafc); border-radius: .7rem; display: grid; gap: .2rem; padding: .75rem .85rem; }
.vetedge-appointment-flow-section-note span { color: var(--edge-color-ink-500, #6b7d90); font-size: .75rem; }
@media (max-width: 47.99rem) { .vetedge-appointment-flow-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
