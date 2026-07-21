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
									<label v-if="field.fieldtype !== 'Check'" :for="field.fieldname">
										{{ field.label }}<span v-if="isRequired(field)"> *</span>
									</label>

									<label v-if="field.fieldtype === 'Check'" class="settings-check">
										<input
											type="checkbox"
											:checked="Boolean(Number(values[field.fieldname]))"
											:disabled="isReadOnly(field)"
											@change="setValue(field.fieldname, $event.target.checked ? 1 : 0)"
										/>
										<span><strong>{{ field.label }}</strong><small v-if="field.description">{{ field.description }}</small></span>
									</label>

									<select
										v-else-if="field.fieldtype === 'Select'"
										:id="field.fieldname"
										class="edge-input edge-control"
										:value="values[field.fieldname] || ''"
										:disabled="isReadOnly(field)"
										@change="setValue(field.fieldname, $event.target.value)"
									>
										<option v-for="option in selectOptions(field)" :key="option" :value="option">{{ option || "Select" }}</option>
									</select>

									<EdgeLinkField
										v-else-if="field.fieldtype === 'Link'"
										:model-value="values[field.fieldname] || ''"
										:selected-label="values[field.fieldname] || ''"
										:placeholder="`Search ${field.options}`"
										:description="field.description || ''"
										:required="isRequired(field)"
										:disabled="isReadOnly(field)"
										:searcher="(term) => searchLink(field, term)"
										@update:model-value="setValue(field.fieldname, $event)"
									/>

									<div v-else-if="field.fieldtype === 'Attach' || field.fieldtype === 'Attach Image'" class="settings-attachment">
										<img v-if="field.fieldtype === 'Attach Image' && values[field.fieldname]" :src="values[field.fieldname]" :alt="field.label" />
										<input class="edge-input edge-control" type="text" :value="values[field.fieldname] || ''" readonly />
										<button type="button" class="edge-button" :disabled="isReadOnly(field)" @click="upload(field)">Choose File</button>
										<button v-if="values[field.fieldname]" type="button" class="edge-button" :disabled="isReadOnly(field)" @click="setValue(field.fieldname, '')">Clear</button>
									</div>

									<textarea
										v-else-if="['Small Text', 'Text', 'Long Text', 'Code'].includes(field.fieldtype)"
										:id="field.fieldname"
										class="edge-input edge-control settings-textarea"
										:value="values[field.fieldname] || ''"
										:disabled="isReadOnly(field)"
										@input="setValue(field.fieldname, $event.target.value)"
									></textarea>

									<div v-else-if="field.fieldtype === 'Table'" class="settings-table-editor">
										<div class="settings-table-scroll">
											<table>
												<thead><tr><th v-for="child in field.child_fields" :key="child.fieldname">{{ child.label }}</th><th></th></tr></thead>
												<tbody>
													<tr v-for="(row, rowIndex) in values[field.fieldname] || []" :key="rowIndex">
														<td v-for="child in field.child_fields" :key="child.fieldname">
															<input
																v-if="child.fieldtype !== 'Check' && child.fieldtype !== 'Select'"
																class="edge-input edge-control"
																:type="inputType(child)"
																:value="row[child.fieldname] || ''"
																@input="setChildValue(field.fieldname, rowIndex, child.fieldname, $event.target.value)"
															/>
															<input
																v-else-if="child.fieldtype === 'Check'"
																type="checkbox"
																:checked="Boolean(Number(row[child.fieldname]))"
																@change="setChildValue(field.fieldname, rowIndex, child.fieldname, $event.target.checked ? 1 : 0)"
															/>
															<select
																v-else
																class="edge-input edge-control"
																:value="row[child.fieldname] || ''"
																@change="setChildValue(field.fieldname, rowIndex, child.fieldname, $event.target.value)"
															>
																<option v-for="option in selectOptions(child)" :key="option" :value="option">{{ option }}</option>
															</select>
														</td>
														<td><button type="button" class="edge-button" @click="removeRow(field.fieldname, rowIndex)">Remove</button></td>
													</tr>
												</tbody>
											</table>
										</div>
										<button type="button" class="edge-button" @click="addRow(field)">Add Row</button>
									</div>

									<input
										v-else
										:id="field.fieldname"
										class="edge-input edge-control"
										:type="inputType(field)"
										:value="values[field.fieldname] || ''"
										:disabled="isReadOnly(field)"
										@input="setValue(field.fieldname, $event.target.value)"
									/>

									<small v-if="field.fieldtype !== 'Check' && field.description" class="settings-help">{{ field.description }}</small>
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
			} catch (error) {
				frappe.msgprint({ title: __("Unable to save Veterinary Settings"), message: error?.message || __("The settings could not be saved."), indicator: "red" });
			} finally { this.saving = false; }
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
.settings-status-bar,.settings-section-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--edge-radius-lg,12px)}.settings-status-bar{align-items:center;display:flex;gap:1rem;justify-content:space-between;padding:1rem}.settings-status-copy,.settings-status-actions{align-items:center;display:flex;gap:.75rem}.settings-status-copy>div:last-child{display:grid;gap:.15rem}.settings-status-copy small,.settings-section-card header p,.settings-help{color:var(--text-muted)}.settings-brand-preview{align-items:center;background:var(--subtle-fg);border:1px solid var(--border-color);border-radius:.7rem;display:flex;font-weight:800;height:3rem;justify-content:center;overflow:hidden;width:3rem}.settings-brand-preview img{height:100%;object-fit:contain;width:100%}.settings-tabs{display:flex;gap:.4rem;margin:1rem 0;overflow-x:auto;padding-bottom:.25rem}.settings-tab{background:var(--card-bg);border:1px solid var(--border-color);border-radius:999px;cursor:pointer;padding:.5rem .9rem;white-space:nowrap}.settings-tab.is-active{background:var(--edge-primary-soft,#eef7ff);border-color:var(--edge-primary,#1677ff);color:var(--edge-primary,#1677ff);font-weight:700}.settings-sections{display:grid;gap:1rem}.settings-section-card{padding:1.1rem}.settings-section-card header{margin-bottom:1rem}.settings-section-card h2{font-size:1.05rem;margin:0 0 .25rem}.settings-section-card p{margin:0}.settings-field-grid{display:grid;gap:1rem;grid-template-columns:repeat(2,minmax(0,1fr))}.settings-field{display:grid;gap:.35rem;min-width:0}.settings-field--wide{grid-column:1/-1}.settings-field>label{font-weight:650}.settings-check{align-items:flex-start;background:var(--subtle-fg);border:1px solid var(--border-color);border-radius:.65rem;display:flex;gap:.7rem;padding:.75rem}.settings-check span{display:grid;gap:.15rem}.settings-check small{color:var(--text-muted);font-weight:400}.settings-textarea{min-height:7rem;resize:vertical}.settings-attachment{align-items:center;display:flex;flex-wrap:wrap;gap:.5rem}.settings-attachment img{border:1px solid var(--border-color);border-radius:.5rem;height:4rem;object-fit:contain;width:4rem}.settings-table-editor{display:grid;gap:.65rem}.settings-table-scroll{overflow-x:auto}.settings-table-editor table{border-collapse:collapse;min-width:100%;width:max-content}.settings-table-editor th,.settings-table-editor td{border:1px solid var(--border-color);padding:.45rem;vertical-align:top}.settings-table-editor th{background:var(--subtle-fg);font-size:.75rem;text-align:left}.settings-table-editor td .edge-control{min-width:9rem}@media(max-width:48rem){.settings-status-bar,.settings-status-actions{align-items:flex-start;flex-direction:column}.settings-field-grid{grid-template-columns:1fr}.settings-field--wide{grid-column:auto}}
</style>
