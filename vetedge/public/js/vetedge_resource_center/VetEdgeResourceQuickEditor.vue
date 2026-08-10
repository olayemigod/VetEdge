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
					<EdgeLinkField
						v-if="field.fieldtype === 'Link'"
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

					<label v-else-if="field.fieldtype === 'Check'" class="vetedge-quick-editor-check">
						<input
							type="checkbox"
							:checked="Boolean(Number(values[field.fieldname]) || values[field.fieldname] === true)"
							@change="values[field.fieldname] = $event.target.checked ? 1 : 0"
						/>
						<span>
							<strong>{{ field.label }}</strong>
							<small v-if="field.description">{{ field.description }}</small>
						</span>
					</label>

					<label v-else-if="isTextArea(field)" class="vetedge-quick-editor-field vetedge-quick-editor-field--wide">
						<span class="vetedge-quick-editor-label">
							{{ field.label }}<b v-if="field.reqd"> *</b>
						</span>
						<textarea
							v-model="values[field.fieldname]"
							class="vetedge-quick-editor-control vetedge-quick-editor-textarea"
							:rows="field.fieldtype === 'Long Text' ? 5 : 3"
							:required="Boolean(field.reqd)"
						></textarea>
						<small v-if="field.description" class="vetedge-quick-editor-helper">{{ field.description }}</small>
					</label>

					<label v-else class="vetedge-quick-editor-field">
						<span class="vetedge-quick-editor-label">
							{{ field.label }}<b v-if="field.reqd"> *</b>
						</span>
						<input
							:value="values[field.fieldname] ?? ''"
							:type="inputType(field)"
							class="vetedge-quick-editor-control"
							:step="inputStep(field)"
							:required="Boolean(field.reqd)"
							@input="values[field.fieldname] = $event.target.value"
						/>
						<small v-if="field.description" class="vetedge-quick-editor-helper">{{ field.description }}</small>
					</label>
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
						.filter((field) => field.fieldtype === "Link")
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
		onLinkSelected(field, option) {
			this.values[field.fieldname] = option?.value || "";
			this.linkLabels[field.fieldname] = option?.label || option?.value || "";
		},
		clearLink(field) {
			this.values[field.fieldname] = "";
			this.linkLabels[field.fieldname] = "";
		},
		handleFieldError(error) {
			this.error = error?.message || __("A linked record could not be loaded.");
		},
		serializedValues() {
			const payload = {};
			for (const field of this.schema.fields || []) {
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
				.filter((field) => field.reqd)
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

.vetedge-quick-editor-field {
	display: grid;
	gap: .4rem;
	min-width: 0;
}

.vetedge-quick-editor-field--wide {
	grid-column: 1 / -1;
}

.vetedge-quick-editor-label {
	color: var(--edge-color-ink-700, #415469);
	font-size: .75rem;
	font-weight: 700;
}

.vetedge-quick-editor-label b {
	color: var(--edge-color-danger, #c53a3a);
}

.vetedge-quick-editor-control {
	background: var(--edge-color-surface, #fff);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: var(--edge-radius-md, .75rem);
	box-sizing: border-box;
	color: var(--edge-color-ink-950, #122033);
	font: inherit;
	min-height: 2.55rem;
	outline: none;
	padding: .65rem .75rem;
	transition: border-color .15s ease, box-shadow .15s ease;
	width: 100%;
}

.vetedge-quick-editor-control:focus {
	border-color: var(--edge-color-brand-500, #2d79c7);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--edge-color-brand-500, #2d79c7) 14%, transparent);
}

.vetedge-quick-editor-textarea {
	min-height: 5.5rem;
	resize: vertical;
}

.vetedge-quick-editor-helper {
	color: var(--edge-color-ink-500, #6b7d90);
	font-size: .7rem;
}

.vetedge-quick-editor-check {
	align-items: flex-start;
	background: var(--edge-color-surface-soft, #f9fbfd);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: var(--edge-radius-md, .75rem);
	display: flex;
	gap: .65rem;
	min-height: 2.55rem;
	padding: .7rem .75rem;
}

.vetedge-quick-editor-check input {
	accent-color: var(--edge-color-brand-500, #2d79c7);
	margin-top: .15rem;
}

.vetedge-quick-editor-check span {
	display: grid;
	gap: .2rem;
}

.vetedge-quick-editor-check strong {
	color: var(--edge-color-ink-800, #2a3c50);
	font-size: .75rem;
}

.vetedge-quick-editor-check small {
	color: var(--edge-color-ink-500, #6b7d90);
	font-size: .7rem;
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
