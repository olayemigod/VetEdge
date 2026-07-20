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
						v-model="form.owner"
						:selected-label="labels.owner"
						label="Pet Owner"
						placeholder="Search by owner name, phone or email"
						:searcher="searchOwner"
						:creator="bootstrap.can_create_owner ? createOwnerFromQuery : null"
						:can-create="bootstrap.can_create_owner"
						create-label="Create New Pet Owner"
						required
						@select="onOwnerSelected"
						@clear="clearOwner"
						@search-error="handleFieldError"
					/>

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
						v-model="form.patient"
						:selected-label="labels.patient"
						label="Veterinary Patient"
						placeholder="Search the selected owner's patients"
						:searcher="searchPatient"
						:creator="canCreatePatient ? createPatientFromQuery : null"
						:can-create="canCreatePatient"
						:context="{ owner: form.owner, branch: form.branch }"
						:disabled="!form.owner || !form.branch"
						create-label="Create New Veterinary Patient"
						required
						@select="onPatientSelected"
						@clear="clearPatient"
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
			</form>

			<form v-show="screen === 'owner'" class="vetedge-appointment-flow-form" @submit.prevent="saveOwner">
				<div class="vetedge-appointment-flow-grid">
					<label class="vetedge-appointment-flow-field">
						<span>Owner Name <b>*</b></span>
						<input v-model.trim="ownerDraft.owner_name" class="form-control" required />
					</label>
					<label class="vetedge-appointment-flow-field">
						<span>Mobile Number</span>
						<input v-model.trim="ownerDraft.mobile_no" type="tel" class="form-control" />
					</label>
					<label class="vetedge-appointment-flow-field">
						<span>Email</span>
						<input v-model.trim="ownerDraft.email_id" type="email" class="form-control" />
					</label>
				</div>
				<p class="vetedge-appointment-flow-hint">Provide at least a mobile number or email. Existing owners are checked before creation.</p>
			</form>

			<form v-show="screen === 'patient'" class="vetedge-appointment-flow-form" @submit.prevent="savePatient">
				<div class="vetedge-appointment-flow-context">
					<div><span>Owner</span><strong>{{ labels.owner || form.owner }}</strong></div>
					<div><span>Branch</span><strong>{{ labels.branch || form.branch }}</strong></div>
				</div>
				<div class="vetedge-appointment-flow-grid">
					<label class="vetedge-appointment-flow-field">
						<span>Patient Name <b>*</b></span>
						<input v-model.trim="patientDraft.patient_name" class="form-control" required />
					</label>

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
							<option value=""></option>
							<option value="Male">Male</option>
							<option value="Female">Female</option>
							<option value="Unknown">Unknown</option>
						</select>
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Microchip ID</span>
						<input v-model.trim="patientDraft.microchip_id" class="form-control" />
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Colour / Markings</span>
						<input v-model.trim="patientDraft.color_markings" class="form-control" />
					</label>
				</div>
			</form>
		</div>

		<template #footer>
			<template v-if="screen === 'appointment'">
				<button type="button" class="edge-button" :disabled="saving" @click="close">Cancel</button>
				<button type="button" class="edge-button edge-button--primary" :disabled="saving || loading" @click="submitAppointment">
					{{ saving ? 'Creating...' : 'Create Appointment' }}
				</button>
			</template>
			<template v-else>
				<button type="button" class="edge-button" :disabled="saving" @click="cancelInlineCreate">Back to Appointment</button>
				<button type="button" class="edge-button edge-button--primary" :disabled="saving" @click="screen === 'owner' ? saveOwner() : savePatient()">
					{{ saving ? 'Saving...' : screen === 'owner' ? 'Create Owner' : 'Create Patient' }}
				</button>
			</template>
		</template>
	</EdgeModal>
</template>

<script>
function emptyForm() {
	return {
		owner: "",
		patient: "",
		branch: "",
		practitioner: "",
		appointment_datetime: "",
		appointment_type: "Consultation",
		notes: "",
	};
}

function emptyLabels() {
	return { owner: "", patient: "", branch: "", practitioner: "" };
}

function emptyPatientDraft() {
	return {
		patient_name: "",
		species: "",
		breed: "",
		sex: "",
		microchip_id: "",
		color_markings: "",
	};
}

export default {
	name: "VetEdgeAppointmentFlow",
	emits: ["created"],
	data() {
		return {
			openState: false,
			screen: "appointment",
			loading: false,
			saving: false,
			error: "",
			bootstrap: {
				default_branch: "",
				appointment_types: ["Consultation", "Follow Up", "Vaccination", "Grooming", "Boarding", "Other"],
				can_create_owner: false,
				can_create_patient: false,
				can_create_appointment: false,
			},
			form: emptyForm(),
			labels: emptyLabels(),
			ownerDraft: { owner_name: "", mobile_no: "", email_id: "" },
			patientDraft: emptyPatientDraft(),
			patientLabels: { species: "", breed: "" },
			pendingCreateResolve: null,
		};
	},
	computed: {
		canCreatePatient() {
			return Boolean(this.bootstrap.can_create_patient && this.form.owner && this.form.branch);
		},
		modalTitle() {
			if (this.screen === "owner") return "Create Pet Owner";
			if (this.screen === "patient") return "Create Veterinary Patient";
			return "New Veterinary Appointment";
		},
		modalSubtitle() {
			if (this.screen === "owner") return "Create the owner record and return directly to the appointment.";
			if (this.screen === "patient") return "Create the patient for the selected owner and branch without leaving Veterinary.";
			return "Search existing records or create an owner and patient without leaving Veterinary.";
		},
	},
	methods: {
		async open() {
			this.resolvePendingCreate(null);
			this.form = emptyForm();
			this.labels = emptyLabels();
			this.screen = "appointment";
			this.error = "";
			this.openState = true;
			this.loading = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.get_appointment_form_bootstrap");
				this.bootstrap = { ...this.bootstrap, ...(response.message || {}) };
				if (this.bootstrap.default_branch) {
					this.form.branch = this.bootstrap.default_branch;
					this.labels.branch = this.bootstrap.default_branch;
				}
				if (!this.bootstrap.can_create_appointment) {
					this.error = __("You do not have permission to create Veterinary Appointments.");
				}
			} catch (error) {
				this.error = error?.message || __("The appointment form could not be loaded.");
			} finally {
				this.loading = false;
			}
		},
		close() {
			if (this.saving) return;
			this.resolvePendingCreate(null);
			this.screen = "appointment";
			this.openState = false;
		},
		resolvePendingCreate(value) {
			const resolve = this.pendingCreateResolve;
			this.pendingCreateResolve = null;
			if (resolve) resolve(value || null);
		},
		beginInlineCreate(screen, query) {
			this.resolvePendingCreate(null);
			this.error = "";
			this.screen = screen;
			if (screen === "owner") {
				this.ownerDraft = { owner_name: query || "", mobile_no: "", email_id: "" };
			} else {
				this.patientDraft = { ...emptyPatientDraft(), patient_name: query || "" };
				this.patientLabels = { species: "", breed: "" };
			}
			return new Promise((resolve) => {
				this.pendingCreateResolve = resolve;
			});
		},
		cancelInlineCreate() {
			if (this.saving) return;
			this.resolvePendingCreate(null);
			this.error = "";
			this.screen = "appointment";
		},
		createOwnerFromQuery(query) {
			return this.beginInlineCreate("owner", query);
		},
		createPatientFromQuery(query) {
			if (!this.canCreatePatient) return Promise.resolve(null);
			return this.beginInlineCreate("patient", query);
		},
		async searchLink(field, query, context = {}) {
			const response = await frappe.call("vetedge.services.appointment_edgeui.search_appointment_link", {
				field,
				txt: query,
				context,
				start: 0,
				page_length: 20,
			});
			return response.message || [];
		},
		searchOwner(query) {
			return this.searchLink("owner", query);
		},
		searchPatient(query) {
			return this.searchLink("patient", query, { owner: this.form.owner, branch: this.form.branch });
		},
		searchBranch(query) {
			return this.searchLink("branch", query);
		},
		searchPractitioner(query) {
			return this.searchLink("practitioner", query, { branch: this.form.branch });
		},
		searchSpecies(query) {
			return this.searchLink("species", query);
		},
		searchBreed(query) {
			return this.searchLink("breed", query, { species: this.patientDraft.species });
		},
		onOwnerSelected(option) {
			this.form.owner = option.value;
			this.labels.owner = option.label;
			this.clearPatient();
		},
		clearOwner() {
			this.form.owner = "";
			this.labels.owner = "";
			this.clearPatient();
		},
		onPatientSelected(option) {
			this.form.patient = option.value;
			this.labels.patient = option.label;
		},
		clearPatient() {
			this.form.patient = "";
			this.labels.patient = "";
		},
		onBranchSelected(option) {
			const changed = Boolean(this.form.branch && this.form.branch !== option.value);
			this.form.branch = option.value;
			this.labels.branch = option.label;
			this.clearPractitioner();
			if (changed) this.clearPatient();
		},
		clearBranch() {
			this.form.branch = "";
			this.labels.branch = "";
			this.clearPractitioner();
			this.clearPatient();
		},
		onPractitionerSelected(option) {
			this.form.practitioner = option.value;
			this.labels.practitioner = option.label;
		},
		clearPractitioner() {
			this.form.practitioner = "";
			this.labels.practitioner = "";
		},
		onSpeciesSelected(option) {
			this.patientDraft.species = option.value;
			this.patientLabels.species = option.label;
			this.clearBreed();
		},
		clearSpecies() {
			this.patientDraft.species = "";
			this.patientLabels.species = "";
			this.clearBreed();
		},
		onBreedSelected(option) {
			this.patientDraft.breed = option.value;
			this.patientLabels.breed = option.label;
		},
		clearBreed() {
			this.patientDraft.breed = "";
			this.patientLabels.breed = "";
		},
		handleFieldError(error) {
			this.error = error?.message || __("A linked record could not be loaded.");
		},
		async saveOwner() {
			this.error = "";
			if (!this.ownerDraft.owner_name || (!this.ownerDraft.mobile_no && !this.ownerDraft.email_id)) {
				this.error = __("Owner Name and either Mobile Number or Email are required.");
				return;
			}
			this.saving = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.create_appointment_owner", {
					values: this.ownerDraft,
				});
				const created = response.message || null;
				this.screen = "appointment";
				await this.$nextTick();
				this.resolvePendingCreate(created);
			} catch (error) {
				this.error = error?.message || __("The owner could not be created.");
			} finally {
				this.saving = false;
			}
		},
		async savePatient() {
			this.error = "";
			if (!this.form.owner || !this.form.branch || !this.patientDraft.patient_name || !this.patientDraft.species) {
				this.error = __("Owner, Branch, Patient Name and Species are required.");
				return;
			}
			this.saving = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.create_appointment_patient", {
					values: {
						...this.patientDraft,
						primary_owner: this.form.owner,
						default_branch: this.form.branch,
					},
				});
				const created = response.message || null;
				this.screen = "appointment";
				await this.$nextTick();
				this.resolvePendingCreate(created);
			} catch (error) {
				this.error = error?.message || __("The patient could not be created.");
			} finally {
				this.saving = false;
			}
		},
		appointmentPayload() {
			const datetime = String(this.form.appointment_datetime || "").replace("T", " ");
			return {
				patient: this.form.patient,
				branch: this.form.branch,
				practitioner: this.form.practitioner,
				appointment_datetime: datetime.length === 16 ? `${datetime}:00` : datetime,
				appointment_type: this.form.appointment_type,
				notes: this.form.notes,
			};
		},
		async submitAppointment() {
			this.error = "";
			if (!this.bootstrap.can_create_appointment) {
				this.error = __("You do not have permission to create Veterinary Appointments.");
				return;
			}
			if (!this.form.owner || !this.form.patient || !this.form.branch || !this.form.practitioner || !this.form.appointment_datetime) {
				this.error = __("Owner, Patient, Branch, Practitioner and Appointment Date/Time are required.");
				return;
			}
			this.saving = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.create_edgeui_appointment", {
					values: this.appointmentPayload(),
				});
				const created = response.message || {};
				frappe.show_alert({ message: __("Veterinary Appointment created"), indicator: "green" });
				this.$emit("created", created);
				this.openState = false;
			} catch (error) {
				this.error = error?.message || __("The Veterinary Appointment could not be created.");
			} finally {
				this.saving = false;
			}
		},
	},
};
</script>

<style scoped>
.vetedge-appointment-flow-form {
	display: grid;
	gap: 1rem;
}

.vetedge-appointment-flow-grid {
	display: grid;
	gap: .9rem;
	grid-template-columns: repeat(2, minmax(0, 1fr));
}

.vetedge-appointment-flow-field {
	display: grid;
	gap: .35rem;
	min-width: 0;
}

.vetedge-appointment-flow-field > span,
.vetedge-appointment-flow-context span {
	color: var(--edge-color-ink-700, #415469);
	font-size: .75rem;
	font-weight: 700;
}

.vetedge-appointment-flow-field--wide {
	grid-column: 1 / -1;
}

.vetedge-appointment-flow-error {
	background: color-mix(in srgb, var(--edge-color-danger, #c53a3a) 10%, white);
	border: 1px solid color-mix(in srgb, var(--edge-color-danger, #c53a3a) 25%, white);
	border-radius: .7rem;
	color: var(--edge-color-danger, #a92f2f);
	font-size: .8rem;
	margin-bottom: 1rem;
	padding: .75rem .85rem;
}

.vetedge-appointment-flow-state {
	color: var(--edge-color-ink-500, #6b7d90);
	padding: 2rem;
	text-align: center;
}

.vetedge-appointment-flow-hint {
	color: var(--edge-color-ink-500, #6b7d90);
	font-size: .75rem;
	margin: 0;
}

.vetedge-appointment-flow-context {
	display: grid;
	gap: .75rem;
	grid-template-columns: repeat(2, minmax(0, 1fr));
}

.vetedge-appointment-flow-context > div {
	background: var(--edge-color-surface-soft, #f7fafc);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: .7rem;
	display: grid;
	gap: .2rem;
	padding: .7rem .8rem;
}

.vetedge-appointment-flow-context strong {
	font-size: .85rem;
	overflow-wrap: anywhere;
}

@media (max-width: 47.99rem) {
	.vetedge-appointment-flow-grid,
	.vetedge-appointment-flow-context {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>
