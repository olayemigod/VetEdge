import { h } from "vue";

let mounted = null;
let modalSequence = 0;

function runtime() {
	return window.EdgeSuiteUI || window.EdgeUI || null;
}

function nextModalId() {
	modalSequence += 1;
	return `vetedge-edge-modal-${modalSequence}`;
}

function normalizedOptions(options = []) {
	return (Array.isArray(options) ? options : [])
		.map((option) => {
			if (typeof option === "object") {
				return {
					value: String(option.value ?? option.name ?? ""),
					label: String(option.label ?? option.title ?? option.value ?? option.name ?? ""),
					description: String(option.description ?? ""),
				};
			}
			return { value: String(option), label: String(option), description: "" };
		})
		.filter((option) => option.value);
}

function normalizedMultiValue(value) {
	if (Array.isArray(value)) return [...new Set(value.map(String).filter(Boolean))];
	if (value === undefined || value === null || value === "") return [];
	return [...new Set(String(value).split(",").map((item) => item.trim()).filter(Boolean))];
}

function createPresenter(edge) {
	const {
		EdgeModal,
		EdgeDataTable,
		EdgeStatCard,
		EdgeDashboardLayout,
		EdgeStatusBadge,
		EdgeInput,
		EdgeDropdown,
		EdgeLinkField,
		EdgeTextarea,
		EdgeLoadingState,
		EdgeErrorState,
		EdgeEmptyState,
	} = edge.components;

	return {
		name: "VetEdgeEdgeModalPresenter",
		data() {
			return { open: false, spec: {}, stack: [] };
		},
		methods: {
			normalizeSpec(spec = {}, id = "") {
				return { ...spec, __modalId: id || spec.__modalId || nextModalId(), values: { ...(spec.values || {}) } };
			},
			show(spec = {}, id = "") {
				if (this.open && this.spec?.__modalId) this.stack = [...this.stack, this.spec];
				this.spec = this.normalizeSpec(spec, id);
				this.open = true;
				return this.spec.__modalId;
			},
			update(id, patch = {}) {
				if (!id) return;
				if (this.spec?.__modalId === id) {
					this.spec = { ...this.spec, ...patch, values: patch.values ? { ...patch.values } : { ...(this.spec.values || {}) } };
					return;
				}
				const index = this.stack.findIndex((entry) => entry?.__modalId === id);
				if (index < 0) return;
				const next = [...this.stack];
				const current = next[index];
				next[index] = { ...current, ...patch, values: patch.values ? { ...patch.values } : { ...(current.values || {}) } };
				this.stack = next;
			},
			close(id = this.spec?.__modalId) {
				if (!id) return;
				if (this.spec?.__modalId !== id) {
					this.stack = this.stack.filter((entry) => entry?.__modalId !== id);
					return;
				}
				if (this.spec.busy) return;
				const closing = this.spec;
				if (this.stack.length) {
					const next = [...this.stack];
					this.spec = next.pop();
					this.stack = next;
					this.open = true;
				} else {
					this.open = false;
					this.spec = {};
				}
				closing.onClose?.();
			},
			async runFooterAction(action, id) {
				const nested = this.stack.length > 0;
				let succeeded = false;
				try {
					await action.onClick?.(this.spec.values || {}, this);
					succeeded = true;
				} catch (error) {
					console.error("VetEdge EdgeSuite modal action failed", error);
					if (this.spec?.__modalId === id && !this.spec.error) {
						this.spec = { ...this.spec, busy: false, error: error?.message || __("The action could not be completed."), errorTitle: __("Action failed") };
					}
				}
				if (succeeded && nested && action.closeOnSuccess !== false && this.spec?.__modalId === id && !this.spec.error) {
					this.spec = { ...this.spec, busy: false };
					this.close(id);
				}
			},
			setField(field, value) {
				const values = { ...(this.spec.values || {}), [field.fieldname]: value };
				this.spec = { ...this.spec, values };
				field.onChange?.(value, values, this);
			},
			renderMultiSelect(field, value, index) {
				const selected = normalizedMultiValue(value);
				const options = normalizedOptions(field.options);
				const disabled = Boolean(field.disabled || field.readOnly || this.spec.busy);
				const toggle = (optionValue, checked) => {
					const next = checked ? [...new Set([...selected, optionValue])] : selected.filter((item) => item !== optionValue);
					this.setField(field, next);
				};
				return h("div", { class: ["edge-form-field", "edge-form-field--multiselect"] }, [
					h("span", { class: "edge-form-field__label" }, [field.label || field.fieldname, field.required ? h("span", { class: "edge-form-required", "aria-hidden": "true" }, " *") : null]),
					h("div", { class: "edge-multiselect", role: "group", "data-edge-autofocus": index === 0 ? "true" : undefined }, options.length ? options.map((option) => h("label", { class: "edge-multiselect__option", key: option.value }, [
						h("input", { type: "checkbox", checked: selected.includes(option.value), disabled, onChange: (event) => toggle(option.value, event.target.checked) }),
						h("span", { class: "edge-multiselect__copy" }, [h("strong", option.label), option.description ? h("small", option.description) : null]),
					])) : [h("div", { class: "edge-multiselect__empty" }, field.emptyMessage || __("No options are available."))]),
					field.description ? h("small", field.description) : null,
				]);
			},
			renderCheckbox(field, value, index) {
				return h("div", { class: ["edge-form-field", "edge-form-field--check"] }, [
					h("label", { class: "edge-checkbox" }, [
						h("input", { type: "checkbox", checked: Boolean(Number(value) || value === true), disabled: Boolean(field.disabled || field.readOnly || this.spec.busy), "data-edge-autofocus": index === 0 ? "true" : undefined, onChange: (event) => this.setField(field, event.target.checked ? 1 : 0) }),
						h("span", field.label || field.fieldname),
					]),
					field.description ? h("small", field.description) : null,
				]);
			},
			renderField(field, index) {
				const value = this.spec.values?.[field.fieldname] ?? field.default ?? "";
				if (["multiselect", "multi-select", "multicheck"].includes(field.type)) return this.renderMultiSelect(field, value, index);
				if (["checkbox", "check"].includes(field.type)) return this.renderCheckbox(field, value, index);
				const common = {
					modelValue: value,
					label: field.label || field.fieldname,
					description: field.description || "",
					disabled: Boolean(field.disabled || this.spec.busy),
					readonly: Boolean(field.readOnly),
					required: Boolean(field.required),
					"data-edge-autofocus": index === 0 ? "true" : undefined,
					"onUpdate:modelValue": (next) => this.setField(field, next),
				};
				if (field.type === "select") return h(EdgeDropdown, { ...common, options: field.options || [], placeholder: field.placeholder || __("Select") });
				if (field.type === "link") return h(EdgeLinkField, { ...common, selectedLabel: field.selectedLabel || "", options: field.options || [], searcher: field.searcher || null, minChars: field.minChars ?? 0, debounceMs: field.debounceMs ?? 220, placeholder: field.placeholder || __("Search records") });
				if (field.type === "textarea") return h(EdgeTextarea, { ...common, rows: field.rows || 3, placeholder: field.placeholder || "" });
				return h(EdgeInput, { ...common, type: field.type || "text", placeholder: field.placeholder || "", min: field.min, max: field.max, step: field.step });
			},
			renderBody() {
				const spec = this.spec || {};
				if (spec.loading) return h(EdgeLoadingState, { message: spec.loadingMessage || __("Loading…"), skeleton: true });
				if (spec.error) return h(EdgeErrorState, { title: spec.errorTitle || __("Unable to load"), message: spec.error, onRetry: spec.onRetry });
				const blocks = [];
				if (spec.metrics?.length) blocks.push(h(EdgeDashboardLayout, { minColumnWidth: "10rem" }, { default: () => spec.metrics.map((metric) => h(EdgeStatCard, { label: metric.label, value: metric.value, helper: metric.helper || "", tone: metric.tone || "neutral" })) }));
				if (spec.badges?.length) blocks.push(h("div", { class: "vetedge-edge-modal-badges", style: { display: "flex", flexWrap: "wrap", gap: ".55rem" } }, spec.badges.map((badge) => h(EdgeStatusBadge, { label: badge.label, status: badge.status || badge.label, tone: badge.tone }))));
				if (spec.message) blocks.push(h("p", { class: "vetedge-edge-modal-message", style: { whiteSpace: "pre-line" } }, spec.message));
				if (spec.fields?.length) {
					const fields = spec.fields.filter((field) => field && field.visible !== false);
					blocks.push(h("div", { class: "vetedge-edge-modal-form", style: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,16rem),1fr))", gap: ".9rem 1rem" } }, fields.map((field, index) => this.renderField(field, index))));
				}
				if (spec.columns?.length) blocks.push(spec.rows?.length ? h(EdgeDataTable, { columns: spec.columns, rows: spec.rows, rowKey: spec.rowKey || "name", onRowClick: spec.onRowClick }) : h(EdgeEmptyState, { title: spec.emptyTitle || __("No records"), description: spec.emptyDescription || __("No matching records were found.") }));
				if (spec.sections?.length) {
					for (const section of spec.sections) {
						const sectionBlocks = [h("h3", { style: { margin: "0" } }, section.title || "")];
						if (section.message) sectionBlocks.push(h("p", { style: { whiteSpace: "pre-line" } }, section.message));
						if (section.metrics?.length) sectionBlocks.push(h(EdgeDashboardLayout, { minColumnWidth: "9rem" }, { default: () => section.metrics.map((metric) => h(EdgeStatCard, { label: metric.label, value: metric.value, helper: metric.helper || "", tone: metric.tone || "neutral" })) }));
						if (section.columns?.length) sectionBlocks.push(section.rows?.length ? h(EdgeDataTable, { columns: section.columns, rows: section.rows, rowKey: section.rowKey || "name", onRowClick: section.onRowClick }) : h(EdgeEmptyState, { title: section.emptyTitle || __("No records"), description: section.emptyDescription || "" }));
						blocks.push(h("section", { class: "vetedge-edge-modal-section", style: { display: "grid", gap: ".8rem", paddingTop: ".85rem", borderTop: "1px solid var(--edge-color-border)" } }, sectionBlocks));
					}
				}
				return blocks.length ? h("div", { class: "vetedge-edge-modal-content", style: { display: "grid", gap: "1rem" } }, blocks) : h(EdgeEmptyState, { title: spec.emptyTitle || __("Nothing to display"), description: spec.emptyDescription || "" });
			},
			renderFooter() {
				const id = this.spec.__modalId;
				return h("div", { class: "vetedge-edge-modal-actions", style: { display: "flex", flexWrap: "wrap", gap: ".65rem", justifyContent: "flex-end", width: "100%" } }, [
					...(this.spec.actions || []).map((action) => h("button", { type: "button", class: ["edge-button", action.primary ? "edge-button--primary" : "", action.danger ? "edge-button--danger" : ""], disabled: Boolean(this.spec.busy || action.disabled), onClick: () => this.runFooterAction(action, id) }, action.label)),
					h("button", { type: "button", class: "edge-button", disabled: Boolean(this.spec.busy), onClick: () => this.close(id) }, this.spec.closeLabel || __("Close")),
				]);
			},
		},
		render() {
			const id = this.spec.__modalId;
			return h(EdgeModal, { open: this.open, title: this.spec.title || __("VetEdge"), subtitle: this.spec.subtitle || "", size: this.spec.size || "lg", busy: Boolean(this.spec.busy), onClose: () => this.close(id) }, { default: this.renderBody, footer: this.renderFooter });
		},
	};
}

function ensureMounted() {
	if (mounted?.view) return mounted.view;
	const edge = runtime();
	if (!edge?.createEdgeApp || !edge?.components?.EdgeModal) throw new Error("EdgeSuite modal runtime is unavailable.");
	const host = document.createElement("div");
	host.className = "vetedge-edge-modal-presenter-host";
	host.dataset.edgeProduct = "vetedge";
	document.body.appendChild(host);
	const app = edge.createEdgeApp(createPresenter(edge));
	const view = app.mount(host);
	mounted = { app, view, host };
	return view;
}

export function openVetEdgeEdgeModal(spec = {}) {
	const view = ensureMounted();
	const id = nextModalId();
	view.show(spec, id);
	return { id, update(patch) { view.update(id, patch); }, close() { view.close(id); } };
}

export function modalPresenterReady() {
	const edge = runtime();
	return Boolean(edge?.createEdgeApp && edge?.components?.EdgeModal && edge?.components?.EdgeLinkField);
}

if (typeof window !== "undefined") window.VetEdgeEdgeModalPresenter = { ready: modalPresenterReady, open: openVetEdgeEdgeModal };
