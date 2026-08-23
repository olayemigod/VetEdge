<template>
	<EdgeModal
		:open="openState"
		title="New Veterinary Appointment"
		subtitle="Choose the appointment type and VetEdge will request only the clinical or service context needed for that workflow."
		size="lg"
		:busy="saving"
		@close="close"
	>
		<div v-if="loading" class="vetedge-appointment-flow-state">Loading appointment form...</div>

		<div v-else class="vetedge-appointment-flow-surface">
			<div v-if="error" class="vetedge-appointment-flow-error" role="alert">{{ error }}</div>

			<form class="vetedge-appointment-flow-form" @submit.prevent="submitAppointment">
				<div class="vetedge-appointment-flow-grid">
					<EdgeLinkField
						v-model="form.patient"
						:selected-label="labels.patient"
						label="Veterinary Patient"
						placeholder="Search patient name, patient ID, owner or microchip"
						:searcher="searchPatient"
						required
						@select="onPatientSelected"
						@clear="clearPatient"
						@search-error="handleFieldError"
					/>

					<div class="vetedge-appointment-flow-field">
						<span class="vetedge-appointment-flow-label">Pet Owner</span>
						<div
							class="vetedge-appointment-flow-readonly"
							:class="{ 'is-placeholder': !(labels.owner || form.owner) }"
							aria-readonly="true"
						>
							{{ labels.owner || form.owner || 'Populated from selected patient' }}
						</div>
					</div>

					<EdgeLinkField
						v-model="form.branch"
						:selected-label="labels.branch"
						label="Service Branch"
						placeholder="Select the branch providing this service"
						:searcher="searchBranch"
						required
						@select="onBranchSelected"
						@clear="clearBranch"
						@search-error="handleFieldError"
					/>

					<EdgeDropdown
						v-model="form.appointment_type"
						label="Appointment Type"
						:options="appointmentTypeOptions"
						placeholder="Select appointment type"
					/>

					<EdgeLinkField
						v-if="hasConsultationContext"
						v-model="form.consultation_type"
						:selected-label="labels.consultationType"
						label="Consultation Type"
						placeholder="Select the kind of consultation"
						:searcher="searchConsultationType"
						required
						@select="onConsultationTypeSelected"
						@clear="clearConsultationType"
						@search-error="handleFieldError"
					/>

					<EdgeLinkField
						v-if="isFollowUp"
						v-model="form.follow_up_reference"
						:selected-label="labels.followUpReference"
						label="Originating Consultation"
						placeholder="Select the earlier consultation for this patient"
						:searcher="searchFollowUpReference"
						:context="{ patient: form.patient }"
						:disabled="!form.patient"
						required
						@select="onFollowUpReferenceSelected"
						@clear="clearFollowUpReference"
						@search-error="handleFieldError"
					/>

					<EdgeLinkField
						v-if="isVaccination"
						v-model="form.vaccine"
						:selected-label="labels.vaccine"
						label="Planned Vaccine"
						placeholder="Search active vaccines applicable to this patient"
						:searcher="searchVaccine"
						:context="{ species: patientSpecies }"
						required
						@select="onVaccineSelected"
						@clear="clearVaccine"
						@search-error="handleFieldError"
					/>

					<EdgeLinkField
						v-if="!isGrooming"
						v-model="form.practitioner"
						:selected-label="labels.practitioner"
						:label="requiresPractitioner ? 'Veterinary Practitioner' : 'Veterinary Practitioner (Optional)'"
						placeholder="Search doctors available for this service branch"
						:searcher="searchPractitioner"
						:context="{ branch: form.branch }"
						:disabled="!form.branch"
						:required="requiresPractitioner"
						@select="onPractitionerSelected"
						@clear="clearPractitioner"
						@search-error="handleFieldError"
					/>

					<EdgeLinkField
						v-if="isGrooming"
						v-model="form.grooming_service"
						:selected-label="labels.groomingService"
						label="Grooming Service"
						placeholder="Search active grooming services"
						:searcher="searchGroomingService"
						required
						@select="onGroomingServiceSelected"
						@clear="clearGroomingService"
						@search-error="handleFieldError"
					/>

					<EdgeLinkField
						v-if="isGrooming"
						v-model="form.groomer"
						:selected-label="labels.groomer"
						label="Groomer"
						placeholder="Search grooming staff available for this branch"
						:searcher="searchGroomer"
						:context="{ branch: form.branch }"
						:disabled="!form.branch"
						required
						@select="onGroomerSelected"
						@clear="clearGroomer"
						@search-error="handleFieldError"
					/>

					<label class="vetedge-appointment-flow-field">
						<span class="vetedge-appointment-flow-label">Appointment Date/Time <b>*</b></span>
						<input
							v-model="form.appointment_datetime"
							type="datetime-local"
							class="vetedge-appointment-flow-control"
							required
						/>
					</label>
				</div>

				<label class="vetedge-appointment-flow-field vetedge-appointment-flow-field--wide">
					<span class="vetedge-appointment-flow-label">{{ notesLabel }} <b v-if="isOther">*</b></span>
					<textarea
						v-model.trim="form.notes"
						class="vetedge-appointment-flow-control vetedge-appointment-flow-textarea"
						rows="3"
						:placeholder="notesPlaceholder"
						:required="isOther"
					></textarea>
				</label>
			</form>
		</div>

		<template #footer>
			<button type="button" class="edge-button" :disabled="saving" @click="close">Cancel</button>
			<button type="button" class="edge-button edge-button--primary" :disabled="saving || loading" @click="submitAppointment">
				{{ saving ? 'Creating...' : 'Create Appointment' }}
			</button>
		</template>
	</EdgeModal>
</template>

<script>
function emptyForm() {
	return {
		patient: "",
		owner: "",
		branch: "",
		practitioner: "",
		consultation_type: "",
		follow_up_reference: "",
		vaccine: "",
		grooming_service: "",
		groomer: "",
		appointment_datetime: "",
		appointment_type: "Consultation",
		notes: "",
	};
}

function emptyLabels() {
	return {
		patient: "",
		owner: "",
		branch: "",
		practitioner: "",
		consultationType: "",
		followUpReference: "",
		vaccine: "",
		groomingService: "",
		groomer: "",
	};
}

export default {
	name: "VetEdgeAppointmentFlow",
	emits: ["created"],
	data() {
		return {
			openState: false,
			loading: false,
			saving: false,
			error: "",
			patientSpecies: "",
			bootstrap: {
				default_branch: "",
				default_consultation_type: "",
				appointment_types: ["Consultation", "Follow Up", "Vaccination", "Grooming", "Other"],
				can_create_appointment: false,
			},
			form: emptyForm(),
			labels: emptyLabels(),
		};
	},
	computed: {
		appointmentTypeOptions() {
			return (this.bootstrap.appointment_types || []).map((type) => ({ value: type, label: type }));
		},
		isGrooming() {
			return this.form.appointment_type === "Grooming";
		},
		isFollowUp() {
			return this.form.appointment_type === "Follow Up";
		},
		isVaccination() {
			return this.form.appointment_type === "Vaccination";
		},
		isOther() {
			return this.form.appointment_type === "Other";
		},
		hasConsultationContext() {
			return ["Consultation", "Follow Up"].includes(this.form.appointment_type);
		},
		requiresPractitioner() {
			return ["Consultation", "Follow Up", "Vaccination"].includes(this.form.appointment_type);
		},
		notesLabel() {
			return this.isOther ? "Reason / Notes" : "Notes";
		},
		notesPlaceholder() {
			if (this.isOther) return "Describe the purpose of this appointment";
			if (this.isVaccination) return "Vaccination notes or instructions";
			if (this.isFollowUp) return "Follow-up reason or front-desk notes";
			return "Reason for visit or front-desk notes";
		},
	},
	watch: {
		"form.appointment_type"(value, previous) {
			if (value === previous) return;
			this.error = "";
			if (value === "Grooming") this.clearPractitioner();
			else {
				this.clearGroomingService();
				this.clearGroomer();
			}
			if (!["Consultation", "Follow Up"].includes(value)) this.clearConsultationType();
			else if (!this.form.consultation_type && this.bootstrap.default_consultation_type) {
				this.form.consultation_type = this.bootstrap.default_consultation_type;
				this.labels.consultationType = this.bootstrap.default_consultation_type;
			}
			if (value !== "Follow Up") this.clearFollowUpReference();
			if (value !== "Vaccination") this.clearVaccine();
		},
	},
	methods: {
		async open(options = {}) {
			this.form = emptyForm();
			this.labels = emptyLabels();
			this.patientSpecies = "";
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
				const requestedType = String(options?.appointment_type || "").trim();
				if (requestedType && (this.bootstrap.appointment_types || []).includes(requestedType)) {
					this.form.appointment_type = requestedType;
				}
				if (this.hasConsultationContext && this.bootstrap.default_consultation_type) {
					this.form.consultation_type = this.bootstrap.default_consultation_type;
					this.labels.consultationType = this.bootstrap.default_consultation_type;
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
			this.openState = false;
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
		searchPatient(query) {
			return this.searchLink("patient", query);
		},
		searchBranch(query) {
			return this.searchLink("branch", query);
		},
		searchPractitioner(query) {
			return this.searchLink("practitioner", query, { branch: this.form.branch });
		},
		searchConsultationType(query) {
			return this.searchLink("consultation_type", query);
		},
		searchFollowUpReference(query) {
			return this.searchLink("follow_up_reference", query, { patient: this.form.patient });
		},
		searchVaccine(query) {
			return this.searchLink("vaccine", query, { species: this.patientSpecies });
		},
		searchGroomingService(query) {
			return this.searchLink("grooming_service", query);
		},
		searchGroomer(query) {
			return this.searchLink("groomer", query, { branch: this.form.branch });
		},
		async onPatientSelected(option) {
			const patient = String(option?.value || "").trim();
			this.form.patient = patient;
			this.labels.patient = option?.label || patient;
			this.form.owner = "";
			this.labels.owner = "";
			this.patientSpecies = "";
			this.clearFollowUpReference();
			this.clearVaccine();
			if (!patient) return;

			try {
				const matches = await this.searchLink("patient", patient);
				if (this.form.patient !== patient) return;
				const exact = matches.find((row) => String(row?.value || "") === patient) || null;
				const patientRow = exact?.raw || {};
				const owner = String(patientRow.primary_owner || exact?.primary_owner || "").trim();
				if (!owner) {
					this.error = __("The selected patient does not have a Pet Owner configured.");
					return;
				}
				this.form.owner = owner;
				this.labels.owner = owner;
				this.patientSpecies = String(patientRow.species || "").trim();
				if (!this.form.branch && patientRow.default_branch) {
					this.form.branch = patientRow.default_branch;
					this.labels.branch = patientRow.default_branch;
				}
				this.error = "";
			} catch (error) {
				if (this.form.patient !== patient) return;
				this.error = error?.message || __("The Pet Owner could not be loaded from the selected patient.");
			}
		},
		clearPatient() {
			this.form.patient = "";
			this.labels.patient = "";
			this.form.owner = "";
			this.labels.owner = "";
			this.patientSpecies = "";
			this.clearFollowUpReference();
			this.clearVaccine();
		},
		onBranchSelected(option) {
			this.form.branch = option.value;
			this.labels.branch = option.label;
			this.clearPractitioner();
			this.clearGroomer();
		},
		clearBranch() {
			this.form.branch = "";
			this.labels.branch = "";
			this.clearPractitioner();
			this.clearGroomer();
		},
		onPractitionerSelected(option) {
			this.form.practitioner = option.value;
			this.labels.practitioner = option.label;
		},
		clearPractitioner() {
			this.form.practitioner = "";
			this.labels.practitioner = "";
		},
		onConsultationTypeSelected(option) {
			this.form.consultation_type = option.value;
			this.labels.consultationType = option.label;
		},
		clearConsultationType() {
			this.form.consultation_type = "";
			this.labels.consultationType = "";
		},
		onFollowUpReferenceSelected(option) {
			this.form.follow_up_reference = option.value;
			this.labels.followUpReference = option.label;
			const origin = option?.raw || {};
			if (origin.service_branch) {
				this.form.branch = origin.service_branch;
				this.labels.branch = origin.service_branch;
			}
			if (origin.consulting_practitioner) {
				this.form.practitioner = origin.consulting_practitioner;
				this.labels.practitioner = origin.consulting_practitioner_name || origin.consulting_practitioner;
			}
			if (origin.consultation_type) {
				this.form.consultation_type = origin.consultation_type;
				this.labels.consultationType = origin.consultation_type;
			}
		},
		clearFollowUpReference() {
			this.form.follow_up_reference = "";
			this.labels.followUpReference = "";
		},
		onVaccineSelected(option) {
			this.form.vaccine = option.value;
			this.labels.vaccine = option.label;
		},
		clearVaccine() {
			this.form.vaccine = "";
			this.labels.vaccine = "";
		},
		onGroomingServiceSelected(option) {
			this.form.grooming_service = option.value;
			this.labels.groomingService = option.label;
		},
		clearGroomingService() {
			this.form.grooming_service = "";
			this.labels.groomingService = "";
		},
		onGroomerSelected(option) {
			this.form.groomer = option.value;
			this.labels.groomer = option.label;
		},
		clearGroomer() {
			this.form.groomer = "";
			this.labels.groomer = "";
		},
		handleFieldError(error) {
			this.error = error?.message || __("A linked record could not be loaded.");
		},
		appointmentPayload() {
			const datetime = String(this.form.appointment_datetime || "").replace("T", " ");
			return {
				patient: this.form.patient,
				branch: this.form.branch,
				practitioner: this.isGrooming ? "" : this.form.practitioner,
				consultation_type: this.hasConsultationContext ? this.form.consultation_type : "",
				follow_up_reference: this.isFollowUp ? this.form.follow_up_reference : "",
				vaccine: this.isVaccination ? this.form.vaccine : "",
				grooming_service: this.isGrooming ? this.form.grooming_service : "",
				groomer: this.isGrooming ? this.form.groomer : "",
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
			if (!this.form.patient || !this.form.branch || !this.form.appointment_datetime) {
				this.error = __("Patient, Service Branch and Appointment Date/Time are required.");
				return;
			}
			if (this.hasConsultationContext && !this.form.consultation_type) {
				this.error = __("Consultation Type is required for Consultation and Follow Up appointments.");
				return;
			}
			if (this.isFollowUp && !this.form.follow_up_reference) {
				this.error = __("Originating Consultation is required for Follow Up appointments.");
				return;
			}
			if (this.isVaccination && !this.form.vaccine) {
				this.error = __("Planned Vaccine is required for Vaccination appointments.");
				return;
			}
			if (this.isGrooming && (!this.form.grooming_service || !this.form.groomer)) {
				this.error = __("Grooming Service and Groomer are required for Grooming appointments.");
				return;
			}
			if (this.requiresPractitioner && !this.form.practitioner) {
				this.error = __("Veterinary Practitioner is required for this appointment type.");
				return;
			}
			if (this.isOther && !this.form.notes) {
				this.error = __("Reason / Notes is required for Other appointments.");
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
.vetedge-appointment-flow-surface {
	background: var(--edge-color-surface, #fff);
}

.vetedge-appointment-flow-form {
	display: grid;
	gap: 1.15rem;
}

.vetedge-appointment-flow-grid {
	display: grid;
	gap: 1rem;
	grid-template-columns: repeat(2, minmax(0, 1fr));
}

.vetedge-appointment-flow-field {
	display: grid;
	gap: .4rem;
	min-width: 0;
}

.vetedge-appointment-flow-label {
	color: var(--edge-color-ink-700, #415469);
	font-size: .75rem;
	font-weight: 700;
	letter-spacing: .01em;
}

.vetedge-appointment-flow-field--wide {
	grid-column: 1 / -1;
}

.vetedge-appointment-flow-control,
.vetedge-appointment-flow-readonly {
	background: var(--edge-color-surface, #fff);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: .7rem;
	box-sizing: border-box;
	color: var(--edge-color-ink-900, #172b3a);
	font: inherit;
	min-height: 2.55rem;
	outline: none;
	padding: .62rem .75rem;
	transition: border-color .16s ease, box-shadow .16s ease, background .16s ease;
	width: 100%;
}

.vetedge-appointment-flow-control:focus {
	border-color: var(--edge-color-primary, #2563eb);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--edge-color-primary, #2563eb) 14%, transparent);
}

.vetedge-appointment-flow-readonly {
	align-items: center;
	background: var(--edge-color-surface-soft, #f7fafc);
	display: flex;
}

.vetedge-appointment-flow-readonly.is-placeholder {
	color: var(--edge-color-ink-400, #8494a5);
}

.vetedge-appointment-flow-textarea {
	min-height: 5.25rem;
	resize: vertical;
}

.vetedge-appointment-flow-error {
	background: color-mix(in srgb, var(--edge-color-danger, #c53a3a) 8%, white);
	border: 1px solid color-mix(in srgb, var(--edge-color-danger, #c53a3a) 22%, white);
	border-radius: .75rem;
	color: var(--edge-color-danger, #a92f2f);
	font-size: .8rem;
	margin-bottom: 1rem;
	padding: .8rem .9rem;
}

.vetedge-appointment-flow-state {
	color: var(--edge-color-ink-500, #6b7d90);
	padding: 2rem;
	text-align: center;
}

@media (max-width: 47.99rem) {
	.vetedge-appointment-flow-grid {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>