import { h } from "vue";

let mounted = null;

function runtime() {
	return window.EdgeSuiteUI || window.EdgeUI || null;
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
		EdgeTextarea,
		EdgeLoadingState,
		EdgeErrorState,
		EdgeEmptyState,
	} = edge.components;

	return {
		name: "VetEdgeEdgeModalPresenter",
		data() {
			return { open: false, spec: {} };
		},
		methods: {
			show(spec = {}) {
				this.spec = { values: {}, ...spec, values: { ...(spec.values || {}) } };
				this.open = true;
			},
			update(patch = {}) {
				this.spec = {
					...this.spec,
					...patch,
					values: patch.values ? { ...patch.values } : { ...(this.spec.values || {}) },
				};
			},
			close() {
				if (this.spec.busy) return;
				this.open = false;
				this.spec.onClose?.();
			},
			setField(field, value) {
				const values = { ...(this.spec.values || {}), [field.fieldname]: value };
				this.spec = { ...this.spec, values };
				field.onChange?.(value, values, this);
			},
			renderField(field, index) {
				const value = this.spec.values?.[field.fieldname] ?? field.default ?? "";
				const common = {
					modelValue: value,
					label: field.label || field.fieldname,
					description: field.description || "",
					disabled: Boolean(field.disabled || field.readOnly || this.spec.busy),
					required: Boolean(field.required),
					"data-edge-autofocus": index === 0 ? "true" : undefined,
					"onUpdate:modelValue": (next) => this.setField(field, next),
				};
				if (field.type === "select") {
					return h(EdgeDropdown, { ...common, options: field.options || [], placeholder: field.placeholder || __("Select") });
				}
				if (field.type === "textarea") {
					return h(EdgeTextarea, { ...common, rows: field.rows || 3, placeholder: field.placeholder || "" });
				}
				return h(EdgeInput, {
					...common,
					type: field.type || "text",
					placeholder: field.placeholder || "",
					min: field.min,
					max: field.max,
					step: field.step,
				});
			},
			renderBody() {
				const spec = this.spec || {};
				if (spec.loading) return h(EdgeLoadingState, { message: spec.loadingMessage || __("Loading…"), skeleton: true });
				if (spec.error) return h(EdgeErrorState, { title: spec.errorTitle || __("Unable to load"), message: spec.error, onRetry: spec.onRetry });
				const blocks = [];
				if (spec.metrics?.length) {
					blocks.push(h(EdgeDashboardLayout, { minColumnWidth: "10rem" }, {
						default: () => spec.metrics.map((metric) => h(EdgeStatCard, {
							label: metric.label,
							value: metric.value,
							helper: metric.helper || "",
							tone: metric.tone || "neutral",
						})),
					}));
				}
				if (spec.badges?.length) {
					blocks.push(h("div", { class: "vetedge-edge-modal-badges" }, spec.badges.map((badge) => h(EdgeStatusBadge, {
						label: badge.label,
						status: badge.status || badge.label,
						tone: badge.tone,
					}))));
				}
				if (spec.message) blocks.push(h("p", { class: "vetedge-edge-modal-message" }, spec.message));
				if (spec.fields?.length) {
					blocks.push(h("div", { class: "vetedge-edge-modal-form" }, spec.fields.map((field, index) => this.renderField(field, index))));
				}
				if (spec.columns?.length) {
					blocks.push(spec.rows?.length
						? h(EdgeDataTable, { columns: spec.columns, rows: spec.rows, rowKey: spec.rowKey || "name", onRowClick: spec.onRowClick })
						: h(EdgeEmptyState, { title: spec.emptyTitle || __("No records"), description: spec.emptyDescription || __("No matching records were found.") }));
				}
				if (spec.sections?.length) {
					for (const section of spec.sections) {
						const sectionBlocks = [h("h3", section.title || "")];
						if (section.message) sectionBlocks.push(h("p", section.message));
						if (section.metrics?.length) {
							sectionBlocks.push(h(EdgeDashboardLayout, { minColumnWidth: "9rem" }, {
								default: () => section.metrics.map((metric) => h(EdgeStatCard, {
									label: metric.label,
									value: metric.value,
									helper: metric.helper || "",
									tone: metric.tone || "neutral",
								})),
							}));
						}
						if (section.columns?.length) {
							sectionBlocks.push(section.rows?.length
								? h(EdgeDataTable, { columns: section.columns, rows: section.rows, rowKey: section.rowKey || "name", onRowClick: section.onRowClick })
								: h(EdgeEmptyState, { title: section.emptyTitle || __("No records"), description: section.emptyDescription || "" }));
						}
						blocks.push(h("section", { class: "vetedge-edge-modal-section" }, sectionBlocks));
					}
				}
				return blocks.length
					? h("div", { class: "vetedge-edge-modal-content" }, blocks)
					: h(EdgeEmptyState, { title: spec.emptyTitle || __("Nothing to display"), description: spec.emptyDescription || "" });
			},
			renderFooter() {
				return h("div", { class: "vetedge-edge-modal-actions" }, [
					...(this.spec.actions || []).map((action) => h("button", {
						type: "button",
						class: ["edge-button", action.primary ? "edge-button--primary" : "", action.danger ? "edge-button--danger" : ""],
						disabled: Boolean(this.spec.busy || action.disabled),
						onClick: () => action.onClick?.(this.spec.values || {}, this),
					}, action.label)),
					h("button", { type: "button", class: "edge-button", disabled: Boolean(this.spec.busy), onClick: this.close }, this.spec.closeLabel || __("Close")),
				]);
			},
		},
		render() {
			return h(EdgeModal, {
				open: this.open,
				title: this.spec.title || __("VetEdge"),
				subtitle: this.spec.subtitle || "",
				size: this.spec.size || "lg",
				busy: Boolean(this.spec.busy),
				onClose: this.close,
			}, { default: this.renderBody, footer: this.renderFooter });
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
	view.show(spec);
	return {
		update(patch) { view.update(patch); },
		close() { view.close(); },
	};
}

export function modalPresenterReady() {
	return Boolean(runtime()?.components?.EdgeModal);
}

if (typeof window !== "undefined") {
	window.VetEdgeEdgeModalPresenter = {
		ready: modalPresenterReady,
		open: openVetEdgeEdgeModal,
	};
}
