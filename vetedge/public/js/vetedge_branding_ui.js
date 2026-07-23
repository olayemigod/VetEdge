// VetEdge clinic-branding adapter for EdgeSuite shell and document settings.
// The adapter stays product-owned: EdgeSuite UI provides the shell/form primitives,
// while VetEdge supplies Frappe upload behaviour and clinic identity resolution.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const BRANDING_EVENT = "vetedge:branding-updated";
	const STYLE_ID = "vetedge-branding-ui-style";
	const STYLE_TEXT = `
		.edge-app-shell.vetedge-shell-has-logo .edge-topbar__mark {
			background-color: var(--edge-color-surface, #fff);
			background-image: var(--vetedge-shell-logo-image);
			background-position: center;
			background-repeat: no-repeat;
			background-size: contain;
			border: 1px solid var(--edge-color-border, #dce5ef);
			border-radius: .6rem;
			min-height: 2rem;
			min-width: 2rem;
			padding: .16rem;
		}

		.edge-app-shell.vetedge-shell-has-logo .edge-topbar__mark > * {
			visibility: hidden;
		}

		.vetedge-shell-logo-mark {
			align-items: center;
			background: var(--edge-color-surface, #fff);
			border: 1px solid var(--edge-color-border, #dce5ef);
			border-radius: .7rem;
			display: inline-flex;
			height: 2.35rem;
			justify-content: center;
			overflow: hidden;
			padding: .2rem;
			width: 2.35rem;
		}

		.vetedge-shell-logo-mark img {
			display: block;
			max-height: 100%;
			max-width: 100%;
			object-fit: contain;
		}

		.vetedge-branding-card {
			background: var(--edge-color-surface, var(--card-bg, #fff));
			border: 1px solid var(--edge-color-border, var(--border-color, #dce5ef));
			border-radius: var(--edge-radius-lg, 1rem);
			display: grid;
			gap: 1rem;
			grid-template-columns: minmax(0, 1fr) auto;
			margin-bottom: var(--edge-section-gap, 1rem);
			padding: 1rem;
		}

		.vetedge-branding-card__copy {
			display: grid;
			gap: .3rem;
		}

		.vetedge-branding-card__copy h3 {
			color: var(--edge-color-ink-900, #1c2b3b);
			font-size: .88rem;
			margin: 0;
		}

		.vetedge-branding-card__copy p,
		.vetedge-branding-card__copy small {
			color: var(--edge-color-ink-500, #6b7d90);
			font-size: .72rem;
			line-height: 1.45;
			margin: 0;
		}

		.vetedge-branding-card__control {
			align-items: center;
			display: flex;
			flex-wrap: wrap;
			gap: .55rem;
			justify-content: flex-end;
		}

		.vetedge-branding-card__preview {
			align-items: center;
			background: var(--edge-color-surface-soft, #f8fafc);
			border: 1px solid var(--edge-color-border, #dce5ef);
			border-radius: .75rem;
			display: inline-flex;
			height: 4.25rem;
			justify-content: center;
			overflow: hidden;
			padding: .35rem;
			width: 7rem;
		}

		.vetedge-branding-card__preview img {
			max-height: 100%;
			max-width: 100%;
			object-fit: contain;
		}

		.vetedge-branding-card__placeholder {
			color: var(--edge-color-ink-500, #6b7d90);
			font-size: .7rem;
			text-align: center;
		}

		@media (max-width: 47.99rem) {
			.vetedge-branding-card {
				grid-template-columns: minmax(0, 1fr);
			}

			.vetedge-branding-card__control {
				justify-content: flex-start;
			}
		}
	`;

	const state = {
		shellInstalled: false,
		formInstalled: false,
		lastError: null,
	};

	function runtime() {
		return window.EdgeSuiteUI || window.EdgeUI || null;
	}

	function injectStyles() {
		if (document.getElementById(STYLE_ID)) return;
		const style = document.createElement("style");
		style.id = STYLE_ID;
		style.textContent = STYLE_TEXT;
		document.head.appendChild(style);
	}

	function bootIdentity() {
		const boot = window.frappe?.boot || {};
		return boot.edgesuite_ui_identity?.vetedge || boot.vetedge_ui_identity || {};
	}

	function safeLogoUrl(value) {
		const url = String(value || "").trim();
		if (!url) return "";
		if (url.startsWith("/") || url.startsWith("https://") || url.startsWith("http://")) return url;
		return "";
	}

	function cssUrl(value) {
		return `url("${String(value || "").replace(/[\\"\n\r]/g, (match) => `\\${match}`)}")`;
	}

	function updateBootIdentityLogo(value) {
		const logo = safeLogoUrl(value);
		const boot = window.frappe?.boot;
		if (boot) {
			boot.edgesuite_ui_identity = boot.edgesuite_ui_identity || {};
			for (const key of ["vetedge", "veterinary"]) {
				boot.edgesuite_ui_identity[key] = {
					...(boot.edgesuite_ui_identity[key] || {}),
					tenant_logo: logo,
				};
			}
			boot.vetedge_ui_identity = {
				...(boot.vetedge_ui_identity || {}),
				tenant_logo: logo,
			};
		}
		window.dispatchEvent(new CustomEvent(BRANDING_EVENT, { detail: { tenant_logo: logo } }));
	}

	function callListener(listener, value) {
		const listeners = Array.isArray(listener) ? listener : [listener];
		listeners.forEach((entry) => {
			if (typeof entry === "function") entry(value);
		});
	}

	function openLogoUploader(onUploaded) {
		const FileUploader = window.frappe?.ui?.FileUploader;
		if (typeof FileUploader !== "function") {
			window.frappe?.msgprint?.({
				title: __("Logo upload unavailable"),
				message: __("The Frappe file uploader is not available on this page. Reload and try again."),
				indicator: "red",
			});
			return;
		}

		new FileUploader({
			doctype: "Veterinary Settings",
			docname: "Veterinary Settings",
			allow_multiple: false,
			restrictions: {
				allowed_file_types: ["image/*"],
			},
			on_success(file) {
				const url = safeLogoUrl(file?.file_url || file?.file_name || "");
				if (!url) {
					window.frappe?.msgprint?.({
						title: __("Logo upload incomplete"),
						message: __("The uploaded file did not return a usable file URL."),
						indicator: "red",
					});
					return;
				}
				onUploaded(url);
			},
		});
	}

	function isSettingsSetupSchema(schema) {
		return (schema?.tabs || []).some((tab) => tab?.key === "general_tab");
	}

	function renderBrandingCard(Vue, attrs) {
		const model = attrs.modelValue || {};
		const updateModel = attrs["onUpdate:modelValue"];
		const savedOrCurrent = safeLogoUrl(model.portal_logo || bootIdentity().tenant_logo || "");
		const setLogo = (url) => {
			const next = { ...model, portal_logo: safeLogoUrl(url) };
			callListener(updateModel, next);
			updateBootIdentityLogo(next.portal_logo);
		};

		return Vue.h("section", { class: "vetedge-branding-card", "aria-label": "Clinic logo" }, [
			Vue.h("div", { class: "vetedge-branding-card__copy" }, [
				Vue.h("h3", "Clinic Logo"),
				Vue.h("p", "Upload the clinic logo used in the VetEdge operational shell and as the owner portal logo fallback."),
				Vue.h("small", "The shell preview updates immediately. Click Save Settings to keep the change."),
			]),
			Vue.h("div", { class: "vetedge-branding-card__control" }, [
				Vue.h("span", { class: "vetedge-branding-card__preview" }, [
					savedOrCurrent
						? Vue.h("img", { src: savedOrCurrent, alt: "Current clinic logo", loading: "eager", decoding: "async" })
						: Vue.h("span", { class: "vetedge-branding-card__placeholder" }, "No clinic logo uploaded"),
				]),
				Vue.h(
					"button",
					{
						type: "button",
						class: "edge-button edge-button--primary",
						disabled: Boolean(attrs.readonly),
						onClick: () => openLogoUploader(setLogo),
					},
					savedOrCurrent ? "Replace Logo" : "Upload Logo",
				),
				savedOrCurrent
					? Vue.h(
							"button",
							{
								type: "button",
								class: "edge-button",
								disabled: Boolean(attrs.readonly),
								onClick: () => setLogo(""),
							},
							"Clear",
						)
					: null,
			]),
		]);
	}

	function installShellAdapter(edgeUI) {
		const CurrentShell = edgeUI.components?.EdgeAppShell;
		const Vue = edgeUI.Vue;
		if (!CurrentShell || !Vue?.defineComponent || !Vue?.h || !edgeUI.registerComponent) return false;
		if (CurrentShell.__vetedgeBrandingShellWrapper) return true;

		const BrandedVetEdgeShell = Vue.defineComponent({
			name: "BrandedVetEdgeShell",
			inheritAttrs: false,
			setup(_props, context) {
				const revision = Vue.ref(0);
				const refresh = () => {
					revision.value += 1;
				};
				Vue.onMounted?.(() => window.addEventListener(BRANDING_EVENT, refresh));
				Vue.onBeforeUnmount?.(() => window.removeEventListener(BRANDING_EVENT, refresh));

				return () => {
					revision.value;
					const attrs = context.attrs || {};
					const logo = safeLogoUrl(bootIdentity().tenant_logo || bootIdentity().product_logo || "");
					const slots = { ...(context.slots || {}) };
					if (logo && !slots.brand) {
						slots.brand = () =>
							Vue.h("span", { class: "vetedge-shell-logo-mark" }, [
								Vue.h("img", { src: logo, alt: "", loading: "eager", decoding: "async" }),
							]);
					}
					return Vue.h(
						CurrentShell,
						{
							...attrs,
							class: [attrs.class, logo ? "vetedge-shell-has-logo" : ""],
							style: [attrs.style, logo ? { "--vetedge-shell-logo-image": cssUrl(logo) } : null],
						},
						slots,
					);
				};
			},
		});
		BrandedVetEdgeShell.__vetedgeBrandingShellWrapper = true;
		edgeUI.registerComponent("EdgeAppShell", BrandedVetEdgeShell, { replace: true });
		return true;
	}

	function installSettingsFormAdapter(edgeUI) {
		const CurrentForm = edgeUI.components?.EdgeDocumentForm;
		const Vue = edgeUI.Vue;
		if (!CurrentForm || !Vue?.defineComponent || !Vue?.h || !edgeUI.registerComponent) return false;
		if (CurrentForm.__vetedgeBrandingFormWrapper) return true;

		const BrandedVetEdgeDocumentForm = Vue.defineComponent({
			name: "BrandedVetEdgeDocumentForm",
			inheritAttrs: false,
			setup(_props, context) {
				return () => {
					const attrs = context.attrs || {};
					const children = [];
					if (isSettingsSetupSchema(attrs.schema)) children.push(renderBrandingCard(Vue, attrs));
					children.push(Vue.h(CurrentForm, attrs, context.slots || {}));
					return Vue.h("div", { class: "vetedge-branded-document-form" }, children);
				};
			},
		});
		BrandedVetEdgeDocumentForm.__vetedgeBrandingFormWrapper = true;
		edgeUI.registerComponent("EdgeDocumentForm", BrandedVetEdgeDocumentForm, { replace: true });
		return true;
	}

	function install() {
		state.lastError = null;
		injectStyles();
		window.VetEdgeProfessionalUI?.install?.();
		const edgeUI = runtime();
		if (!edgeUI) return { installed: false, reason: "runtime-unavailable" };

		try {
			state.shellInstalled = installShellAdapter(edgeUI);
			state.formInstalled = installSettingsFormAdapter(edgeUI);
			if (!state.shellInstalled) throw new Error("EdgeAppShell branding adapter could not be installed.");
			return {
				installed: true,
				shellInstalled: state.shellInstalled,
				formInstalled: state.formInstalled,
			};
		} catch (error) {
			state.lastError = error?.message || String(error);
			return { installed: false, reason: "installation-failed", message: state.lastError };
		}
	}

	function diagnose() {
		return { ...state, tenantLogo: safeLogoUrl(bootIdentity().tenant_logo || "") };
	}

	window.VetEdgeBrandingUI = Object.assign(window.VetEdgeBrandingUI || {}, {
		install,
		diagnose,
		updateLogo: updateBootIdentityLogo,
	});
})();
