<template>
	<EdgeAppShell
		product="veterinary"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="identity.branch_name || ''"
		:user-name="identity.user_name || ''"
		active-route="/app/veterinary-settings-center"
		:hide-native-sidebar="true"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Veterinary Practice Management"
					title="Veterinary Settings"
					subtitle="Configure clinic defaults, clinical workflows, billing, branding, notifications, and access from one guided settings page."
					action-label="Save Settings"
					@action="save"
				/>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading Veterinary Settings..." :skeleton="true" />
			<EdgeErrorState
				v-else-if="error"
				title="Veterinary Settings could not load"
				:message="error"
				action-label="Try again"
				@retry="load"
			/>

			<template v-else>
				<section class="settings-status-bar">
					<div class="settings-status-copy">
						<div class="settings-brand-preview">
							<img v-if="values.portal_logo" :src="values.portal_logo" alt="Clinic logo" />
							<span v-else aria-hidden="true">V</span>
						</div>
						<div>
							<p class="edge-eyebrow">Clinic identity</p>
							<strong>{{ values.portal_brand_name || "Veterinary Clinic" }}</strong>
							<small>Saved branding is used by the Veterinary shell and owner-facing surfaces.</small>
						</div>
					</div>
					<div class="settings-status-actions">
						<EdgeStatusBadge :label="dirty ? 'Unsaved changes' : 'Up to date'" status="default" :tone="dirty ? 'warning' : 'success'" />
						<button type="button" class="edge-button" :disabled="saving" @click="load">Reload</button>
						<button type="button" class="edge-button edge-button--primary" :disabled="saving || !canWrite" @click="save">
							{{ saving ? "Saving..." : "Save Settings" }}
						</button>
					</div>
				</section>

				<nav class="settings-tabs" aria-label="Veterinary Settings sections">
					<button
						v-for="tab in schema"
						:key="tab.fieldname"
						type="button"
						:class="['settings-tab', { 'is-active': activeTab === tab.fieldname }]"
						@click="activeTab = tab.fieldname"
					>
						{{ tab.label }}
					</button>
				</nav>

				<section v-if="activeTabData" class="settings-sections">
					<article v-for="section in activeTabData.sections" :key="section.fieldname" class="settings-section-card">
						<header>
							<h2>{{ section.label }}</h2>
							<p v-if="section.description">{{ section.description }}</p>
						</header>

						<div class="settings-field-grid">
							<template v-for="field in section.fields" :key="field.fieldname">
								<div v-if="isVisible(field)" :class="['settings-field', { 'settings-field--wide': isWide(field) }]">
									<EdgeCheckbox
										v-if="field.fieldtype === 'Check'"
										:model-value="Boolean(Number(values[field.fieldname]))"
										:label="field.label"
										:description="field.description || ''"
										:disabled="isReadOnly(field)"
										@update:model-value="setValue(field.fieldname, $event ? 1 : 0)"
									/>

									<EdgeDropdown
										v-else-if="field.fieldtype === 'Select'"
										:model-value="values[field.fieldname] || ''"
										:label="field.label"
										:options="selectOptions(field).filter(Boolean).map((option) => ({ value: option, label: option }))"
										:description="field.description || ''"
										:required="isRequired(field)"
										:disabled="isReadOnly(field)"
										@update:model-value="setValue(field.fieldname, $event)"
									/>

									<EdgeLinkField
										v-else-if="field.fieldtype === 'Link'"
										:model-value="values[field.fieldname] || ''"
										:selected-label="values[field.fieldname] || ''"
										:label="field.label"
										:placeholder="`Search ${field.options}`"
										:description="field.description || ''"
										:required="isRequired(field)"
										:disabled="isReadOnly(field)"
										:searcher="(term) => searchLink(field, term)"
										@update:model-value="setValue(field.fieldname, $event)"
									/>

									<div v-else-if="field.fieldtype === 'Attach' || field.fieldtype === 'Attach Image'" class="settings-attachment">
										<label class="settings-attachment-label">{{ field.label }}</label>
										<img v-if="field.fieldtype === 'Attach Image' && values[field.fieldname]" :src="values[field.fieldname]" :alt="field.label" />
										<EdgeInput :model-value="values[field.fieldname] || ''" :readonly="true" />
										<button type="button" class="edge-button" :disabled="isReadOnly(field)" @click="upload(field)">Choose File</button>
										<button v-if="values[field.fieldname]" type="button" class="edge-button" :disabled="isReadOnly(field)" @click="setValue(field.fieldname, '')">Clear</button>
									</div>

									<EdgeTextarea
										v-else-if="['Small Text', 'Text', 'Long Text', 'Code'].includes(field.fieldtype)"
										:model-value="values[field.fieldname] || ''"
										:label="field.label"
										:description="field.description || ''"
										:required="isRequired(field)"
										:disabled="isReadOnly(field)"
										:rows="field.fieldtype === 'Long Text' || field.fieldtype === 'Code' ? 6 : 3"
										@update:model-value="setValue(field.fieldname, $event)"
									/>

									<div v-else-if="field.fieldtype === 'Table'" class="settings-table-editor">
										<label class="settings-attachment-label">{{ field.label }}</label>
										<div class="settings-table-scroll">
											<table>
												<thead><tr><th v-for="child in field.child_fields" :key="child.fieldname">{{ child.label }}</th><th></th></tr></thead>
												<tbody>
													<tr v-for="(row, rowIndex) in values[field.fieldname] || []" :key="rowIndex">
														<td v-for="child in field.child_fields" :key="child.fieldname">
															<EdgeCheckbox
																v-if="child.fieldtype === 'Check'"
																:model-value="Boolean(Number(row[child.fieldname]))"
																:label="child.label"
																@update:model-value="setChildValue(field.fieldname, rowIndex, child.fieldname, $event ? 1 : 0)"
															/>
															<EdgeDropdown
																v-else-if="child.fieldtype === 'Select'"
																:model-value="row[child.fieldname] || ''"
																:options="selectOptions(child).filter(Boolean).map((option) => ({ value: option, label: option }))"
																@update:model-value="setChildValue(field.fieldname, rowIndex, child.fieldname, $event)"
															/>
															<EdgeInput
																v-else
																:model-value="row[child.fieldname] || ''"
																:type="inputType(child)"
																@update:model-value="setChildValue(field.fieldname, rowIndex, child.fieldname, $event)"
															/>
														</td>
														<td><button type="button" class="edge-button" @click="removeRow(field.fieldname, rowIndex)">Remove</button></td>
													</tr>
												</tbody>
											</table>
										</div>
										<button type="button" class="edge-button" @click="addRow(field)">Add Row</button>
									</div>

									<EdgeInput
										v-else
										:model-value="values[field.fieldname] || ''"
										:label="field.label"
										:type="inputType(field)"
										:description="field.description || ''"
										:required="isRequired(field)"
										:disabled="isReadOnly(field)"
										@update:model-value="setValue(field.fieldname, $event)"
									/>
								</div>
							</template>
						</div>
					</article>
				</section>
			</template>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
function parseConditionAtom(atom, doc) {
	const text = String(atom || "").trim();
	let match = text.match(/^!doc\.([a-zA-Z0-9_]+)$/);
	if (match) return !Boolean(doc[match[1]]);
	match = text.match(/^doc\.([a-zA-Z0-9_]+)$/);
	if (match) return Boolean(doc[match[1]]);
	match = text.match(/^doc\.([a-zA-Z0-9_]+)\s*(==|!=)\s*["']([^"']*)["']$/);
	if (match) return match[2] === "==" ? String(doc[match[1]] ?? "") === match[3] : String(doc[match[1]] ?? "") !== match[3];
	return true;
}

function evaluateCondition(expression, doc) {
	const value = String(expression || "").trim();
	if (!value) return true;
	if (!value.startsWith("eval:")) return Boolean(doc[value]);
	return value.slice(5).split("||").some((group) => group.split("&&").every((atom) => parseConditionAtom(atom, doc)));
}

export default {
	name: "VeterinarySettingsCenter",
	data() {
		return {
			loading: true, saving: false, error: "", schema: [], values: {}, original: {}, modified: "",
			activeTab: "", canWrite: false,
			identity: {
				tenant_name: window.frappe?.boot?.vetedge_ui_identity?.tenant_name || "Veterinary Clinic",
				branch_name: window.frappe?.boot?.edgesuite_product_menu?.branch || "",
				user_name: window.frappe?.boot?.user?.full_name || window.frappe?.session?.user || "",
			},
		};
	},
	computed: {
		activeTabData() { return this.schema.find((tab) => tab.fieldname === this.activeTab) || this.schema[0] || null; },
		dirty() { return JSON.stringify(this.values) !== JSON.stringify(this.original); },
	},
	mounted() { this.load(); },
	methods: {
		async load() {
			this.loading = true; this.error = "";
			try {
				const response = await frappe.call("vetedge.services.settings_page.get_veterinary_settings_page");
				const payload = response.message || {};
				this.schema = payload.schema || [];
				this.values = JSON.parse(JSON.stringify(payload.values || {}));
				this.original = JSON.parse(JSON.stringify(this.values));
				this.modified = payload.modified || "";
				this.canWrite = Boolean(payload.can_write);
				if (!this.activeTab || !this.schema.some((tab) => tab.fieldname === this.activeTab)) this.activeTab = this.schema[0]?.fieldname || "";
			} catch (error) { this.error = error?.message || __("Veterinary Settings could not be loaded."); }
			finally { this.loading = false; }
		},
		async save() {
			if (!this.canWrite || this.saving) return;
			this.saving = true;
			try {
				const response = await frappe.call("vetedge.services.settings_page.save_veterinary_settings_page", {
					values: this.values,
					expected_modified: this.modified,
				});
				const payload = response.message || {};
				this.values = JSON.parse(JSON.stringify(payload.values || this.values));
				this.original = JSON.parse(JSON.stringify(this.values));
				this.modified = payload.modified || this.modified;
				frappe.show_alert({ message: payload.message || __("Veterinary Settings saved."), indicator: "green" });
				await this.refreshIdentity();
			} catch (error) {
				this.error = error?.message || __("The settings could not be saved.");
			} finally { this.saving = false; }
		},
		async refreshIdentity() {
			try {
				const response = await frappe.call("vetedge.services.settings_page.get_veterinary_settings_page");
				const payload = response.message || {};
				const identity = window.frappe?.boot?.vetedge_ui_identity;
				if (identity) {
					identity.tenant_name = payload.values?.portal_brand_name || identity.tenant_name;
					identity.tenant_logo = payload.values?.portal_logo || "";
				}
				document.dispatchEvent(new CustomEvent("edgesuite:identity-change", { detail: identity || {} }));
			} catch (_error) {}
		},
		setValue(fieldname, value) { this.values = { ...this.values, [fieldname]: value }; },
		setChildValue(fieldname, rowIndex, childField, value) {
			const rows = JSON.parse(JSON.stringify(this.values[fieldname] || []));
			rows[rowIndex] = { ...(rows[rowIndex] || {}), [childField]: value };
			this.setValue(fieldname, rows);
		},
		addRow(field) {
			const row = {};
			(field.child_fields || []).forEach((child) => { row[child.fieldname] = child.fieldtype === "Check" ? 0 : ""; });
			this.setValue(field.fieldname, [...(this.values[field.fieldname] || []), row]);
		},
		removeRow(fieldname, index) { this.setValue(fieldname, (this.values[fieldname] || []).filter((_, rowIndex) => rowIndex !== index)); },
		selectOptions(field) { return String(field.options || "").split("\n"); },
		inputType(field) {
			if (["Int", "Float", "Currency", "Percent"].includes(field.fieldtype)) return "number";
			if (field.fieldtype === "Password") return "password";
			if (field.fieldtype === "Color") return "color";
			return "text";
		},
		isWide(field) { return ["Table", "Small Text", "Text", "Long Text", "Code", "Attach", "Attach Image"].includes(field.fieldtype); },
		isVisible(field) { return evaluateCondition(field.depends_on, this.values); },
		isRequired(field) { return Boolean(field.reqd) || (field.mandatory_depends_on && evaluateCondition(field.mandatory_depends_on, this.values)); },
		isReadOnly(field) { return !this.canWrite || Boolean(field.read_only) || (field.read_only_depends_on && evaluateCondition(field.read_only_depends_on, this.values)); },
		async searchLink(field, term) {
			const response = await frappe.call("vetedge.services.settings_page.search_veterinary_settings_link", { fieldname: field.fieldname, txt: term });
			return response.message || [];
		},
		upload(field) {
			new frappe.ui.FileUploader({
				allow_multiple: false,
				restrictions: field.fieldtype === "Attach Image" ? { allowed_file_types: ["image/*"] } : {},
				on_success: (file) => this.setValue(field.fieldname, file.file_url || file.file_name || ""),
			});
		},
		reload() { return this.load(); },
	},
};
</script>

<style scoped>
.settings-status-bar,.settings-section-card{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-lg,1rem)}.settings-status-bar{align-items:center;display:flex;gap:1rem;justify-content:space-between;padding:1rem}.settings-status-copy,.settings-status-actions{align-items:center;display:flex;gap:.75rem}.settings-status-copy>div:last-child{display:grid;gap:.15rem}.settings-status-copy small,.settings-section-card header p{color:var(--edge-color-ink-500,#617589)}.settings-brand-preview{align-items:center;background:var(--edge-color-surface-muted,#f6f8fa);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:.7rem;display:flex;font-weight:800;height:3rem;justify-content:center;overflow:hidden;width:3rem}.settings-brand-preview img{height:100%;object-fit:contain;width:100%}.settings-tabs{display:flex;gap:.4rem;margin:1rem 0;overflow-x:auto;padding-bottom:.25rem}.settings-tab{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:999px;cursor:pointer;padding:.5rem .9rem;white-space:nowrap}.settings-tab.is-active{background:var(--edge-color-brand-50,#eef7ff);border-color:var(--edge-color-brand-500,#1677c8);color:var(--edge-color-brand-700,#0c4f87);font-weight:700}.settings-sections{display:grid;gap:1rem}.settings-section-card{padding:1.1rem}.settings-section-card header{margin-bottom:1rem}.settings-section-card h2{font-size:1.05rem;margin:0 0 .25rem}.settings-section-card p{margin:0}.settings-field-grid{display:grid;gap:1rem;grid-template-columns:repeat(2,minmax(0,1fr))}.settings-field{display:grid;gap:.35rem;min-width:0}.settings-field--wide{grid-column:1/-1}.settings-attachment{align-items:center;display:flex;flex-wrap:wrap;gap:.5rem}.settings-attachment-label{color:var(--edge-color-ink-700,#334b61);font-size:.75rem;font-weight:700;width:100%}.settings-attachment img{border:1px solid var(--edge-color-border,#dfe6ec);border-radius:.5rem;height:4rem;object-fit:contain;width:4rem}.settings-table-editor{display:grid;gap:.65rem}.settings-table-scroll{overflow-x:auto}.settings-table-editor table{border-collapse:collapse;min-width:100%;width:max-content}.settings-table-editor th,.settings-table-editor td{border:1px solid var(--edge-color-border,#dfe6ec);padding:.45rem;vertical-align:top}.settings-table-editor th{background:var(--edge-color-surface-muted,#f6f8fa);font-size:.75rem;text-align:left}.settings-table-editor td{min-width:10rem}@media(max-width:48rem){.settings-status-bar,.settings-status-actions{align-items:flex-start;flex-direction:column}.settings-field-grid{grid-template-columns:1fr}.settings-field--wide{grid-column:auto}}
</style>
