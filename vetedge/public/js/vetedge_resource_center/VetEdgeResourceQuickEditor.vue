<template>
	<EdgeModal
		:open="openState"
		:title="schema.title || 'Quick Edit'"
		subtitle="Update this Veterinary record without leaving the EdgeSuite workspace."
		size="lg"
		:busy="loading || saving"
		@close="close"
	>
		<div v-if="loading" class="vetedge-quick-editor-state">Loading record...</div>

		<div v-else class="vetedge-quick-editor-surface">
			<div v-if="error" class="vetedge-quick-editor-error" role="alert">{{ error }}</div>

			<form class="vetedge-quick-editor-form" @submit.prevent="save">
				<template v-for="field in schema.fields || []" :key="field.fieldname">
					<EdgeInput
						v-if="field.read_only"
						:model-value="readOnlyValue(field)"
						:label="field.label"
						:description="field.description || ''"
						readonly
					/>

					<EdgeLinkField
						v-else-if="field.fieldtype === 'Link'"
						v-model="values[field.fieldname]"
						:selected-label="linkLabels[field.fieldname] || values[field.fieldname] || ''"
						:label="field.label"
						:placeholder="`Search ${field.label}`"
						:description="field.description || ''"
						:required="Boolean(field.reqd)"
						:searcher="(query) => searchLink(field, query)"
						@select="(option) => onLinkSelected(field, option)"
						@clear="() => clearLink(field)"
						@search-error="handleFieldError"
					/>

					<EdgeDropdown
						v-else-if="field.fieldtype === 'Select'"
						v-model="values[field.fieldname]"
						:label="field.label"
						:options="selectOptions(field)"
						:description="field.description || ''"
						:required="Boolean(field.reqd)"
						:placeholder="`Select ${field.label}`"
					/>

					<EdgeCheckbox
						v-else-if="field.fieldtype === 'Check'"
						v-model="values[field.fieldname]"
						:label="field.label"
						:description="field.description || ''"
					/>

					<div v-else-if="isTextArea(field)" class="vetedge-quick-editor-field--wide">
						<EdgeTextarea
							v-model="values[field.fieldname]"
							:label="field.label"
							:description="field.description || ''"
							:rows="field.fieldtype === 'Long Text' ? 5 : 3"
							:required="Boolean(field.reqd)"
						/>
					</div>

					<EdgeInput
						v-else
						v-model="values[field.fieldname]"
						:label="field.label"
						:description="field.description || ''"
						:type="inputType(field)"
						:step="inputStep(field)"
						:required="Boolean(field.reqd)"
					/>
				</template>
			</form>
		</div>

		<template #footer>
			<button type="button" class="edge-button" :disabled="saving" @click="close">Cancel</button>
			<button
				type="button"
				class="edge-button edge-button--primary"
				:disabled="loading || saving || !schema.can_save"
				@click="save"
			>
				{{ saving ? 'Saving...' : (schema.name ? 'Save Changes' : 'Create Record') }}
			</button>
		</template>
	</EdgeModal>
</template>

<script>
const TEXTAREA_TYPES = new Set(["Small Text", "Text", "Long Text"]);
const NUMBER_TYPES = new Set(["Int", "Float", "Currency", "Percent"]);

function blankSchema() {
	return {
		resource: "",
		doctype: "",
		name: null,
		title: "Quick Edit",
		fields: [],
		values: {},
		can_save: false,
		full_form_route: "",
	};
}

export default {
	name: "VetEdgeResourceQuickEditor",
	emits: ["saved"],
	data() {
		return {
			openState: false,
			loading: false,
			saving: false,
			error: "",
			schema: blankSchema(),
			values: {},
			linkLabels: {},
		};
	},
	methods: {
		async open({ resource, name = null } = {}) {
			this.error = "";
			this.schema = blankSchema();
			this.values = {};
			this.linkLabels = {};
			this.openState = true;
			this.loading = true;
			try {
				const response = await frappe.call("vetedge.services.resource_center.get_resource_editor", {
					resource,
					name,
				});
				const schema = response.message || {};
				this.schema = { ...blankSchema(), ...schema };
				this.values = this.normalizeValues(schema.fields || [], schema.values || {});
				this.linkLabels = Object.fromEntries(
					(schema.fields || [])
						.filter((field) => field.fieldtype === "Link" && !field.read_only)
						.map((field) => [field.fieldname, String(this.values[field.fieldname] || "")]),
				);
				if (!this.schema.can_save) {
					this.error = __("This record is read-only in Quick Edit. Use Open Full Form if you need to inspect it.");
				}
			} catch (error) {
				this.error = error?.message || __("Quick Edit could not load this record.");
			} finally {
				this.loading = false;
			}
		},
		close() {
			if (this.saving) return;
			this.openState = false;
		},
		normalizeValues(fields, rawValues) {
			const normalized = { ...(rawValues || {}) };
			for (const field of fields || []) {
				const value = normalized[field.fieldname];
				if ((value === undefined || value === null || value === "") && field.default !== undefined && field.default !== null) {
					normalized[field.fieldname] = field.default;
				}
				if (field.fieldtype === "Datetime" && normalized[field.fieldname]) {
					normalized[field.fieldname] = String(normalized[field.fieldname]).replace(" ", "T").slice(0, 16);
				}
			}
			return normalized;
		},
		readOnlyValue(field) {
			const value = this.values[field.fieldname];
			return value === undefined || value === null || value === "" ? "—" : String(value);
		},
		selectOptions(field) {
			return String(field.options || "")
				.split("\n")
				.map((value) => value.trim())
				.filter(Boolean)
				.map((value) => ({ value, label: value }));
		},
		isTextArea(field) {
			return TEXTAREA_TYPES.has(field.fieldtype);
		},
		inputType(field) {
			if (field.fieldtype === "Date") return "date";
			if (field.fieldtype === "Datetime") return "datetime-local";
			if (field.fieldtype === "Time") return "time";
			if (field.fieldtype === "Email") return "email";
			if (field.fieldtype === "Phone") return "tel";
			if (NUMBER_TYPES.has(field.fieldtype)) return "number";
			return "text";
		},
		inputStep(field) {
			if (field.fieldtype === "Int") return "1";
			if (NUMBER_TYPES.has(field.fieldtype)) return "any";
			return undefined;
		},
		async searchLink(field, query) {
			if (!field?.options) return [];
			const response = await frappe.call("frappe.desk.search.search_link", {
				doctype: field.options,
				txt: query || "",
				page_length: 20,
				reference_doctype: this.schema.doctype || undefined,
				ignore_user_permissions: 0,
			});
			return response.message || [];
		},
		async onLinkSelected(field, option) {
			this.values[field.fieldname] = option?.value || "";
			this.linkLabels[field.fieldname] = option?.label || option?.value || "";
			if (this.schema.resource === "appointments" && field.fieldname === "patient") {
				await this.refreshAppointmentOwner(option?.value || "");
			}
		},
		clearLink(field) {
			this.values[field.fieldname] = "";
			this.linkLabels[field.fieldname] = "";
			if (this.schema.resource === "appointments" && field.fieldname === "patient") {
				this.values.primary_owner = "";
			}
		},
		async refreshAppointmentOwner(patient) {
			if (!patient) {
				this.values.primary_owner = "";
				return;
			}
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.search_appointment_link", {
					field: "patient",
					txt: patient,
					page_length: 20,
				});
				const options = response.message || [];
				const exact = options.find((row) => String(row?.value || "") === String(patient)) || null;
				const patientRow = exact?.raw?.raw || exact?.raw || {};
				this.values.primary_owner = patientRow.primary_owner || "";
				if (!this.values.primary_owner) {
					this.error = __("The selected patient does not have a Pet Owner configured.");
				}
			} catch (error) {
				this.values.primary_owner = "";
				this.error = error?.message || __("The Pet Owner could not be verified from the selected patient.");
			}
		},
		handleFieldError(error) {
			this.error = error?.message || __("A linked record could not be loaded.");
		},
		serializedValues() {
			const payload = {};
			for (const field of this.schema.fields || []) {
				if (field.read_only) continue;
				let value = this.values[field.fieldname];
				if (field.fieldtype === "Datetime" && value) {
					value = String(value).replace("T", " ");
					if (value.length === 16) value = `${value}:00`;
				}
				if (field.fieldtype === "Check") value = value ? 1 : 0;
				payload[field.fieldname] = value ?? "";
			}
			return payload;
		},
		validateRequired() {
			const missing = (this.schema.fields || [])
				.filter((field) => field.reqd && !field.read_only)
				.filter((field) => {
					const value = this.values[field.fieldname];
					return value === undefined || value === null || String(value).trim() === "";
				})
				.map((field) => field.label);
			if (!missing.length) return true;
			this.error = __("Complete the required fields: {0}", [missing.join(", ")]);
			return false;
		},
		async save() {
			this.error = "";
			if (!this.schema.can_save || this.saving || !this.validateRequired()) return;
			this.saving = true;
			try {
				const response = await frappe.call("vetedge.services.resource_center.save_resource_record", {
					resource: this.schema.resource,
					name: this.schema.name || null,
					values: this.serializedValues(),
				});
				const saved = response.message || {};
				frappe.show_alert({
					message: this.schema.name ? __("Record updated") : __("Record created"),
					indicator: "green",
				});
				this.$emit("saved", saved);
				this.openState = false;
			} catch (error) {
				this.error = error?.message || __("The record could not be saved.");
			} finally {
				this.saving = false;
			}
		},
	},
};
</script>

<style scoped>
.vetedge-quick-editor-surface,
.vetedge-quick-editor-form {
	display: grid;
	gap: 1rem;
}

.vetedge-quick-editor-form {
	grid-template-columns: repeat(2, minmax(0, 1fr));
}

.vetedge-quick-editor-field--wide {
	grid-column: 1 / -1;
	min-width: 0;
}

.vetedge-quick-editor-error {
	background: color-mix(in srgb, var(--edge-color-danger, #c53a3a) 10%, white);
	border: 1px solid color-mix(in srgb, var(--edge-color-danger, #c53a3a) 25%, white);
	border-radius: .7rem;
	color: var(--edge-color-danger, #a92f2f);
	font-size: .8rem;
	padding: .75rem .85rem;
}

.vetedge-quick-editor-state {
	color: var(--edge-color-ink-500, #6b7d90);
	padding: 2rem;
	text-align: center;
}

@media (max-width: 47.99rem) {
	.vetedge-quick-editor-form {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>
