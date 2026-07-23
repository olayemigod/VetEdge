// VetEdge branding adapter for the EdgeSuite shell and Veterinary Settings.
// Owner/tenant branding remains portal-scoped. Operational pages use only the
// product-app identity supplied by VetEdge/CoreEdge.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const STYLE_ID = "vetedge-branding-ui-style";
	const STYLE_TEXT = `
		.edge-app-shell.vetedge-shell-has-product-logo .edge-topbar__mark {
			background-color: var(--edge-color-surface, #fff);
			background-image: var(--vetedge-shell-product-logo-image);
			background-position: center;
			background-repeat: no-repeat;
			background-size: contain;
			border: 1px solid var(--edge-color-border, #dce5ef);
			border-radius: .6rem;
			min-height: 2rem;
			min-width: 2rem;
			padding: .16rem;
		}

		.edge-app-shell.vetedge-shell-has-product-logo .edge-topbar__mark > * {
			visibility: hidden;
		}

		.vetedge-shell-product-logo-mark,
		.vetedge-shell-generic-mark {
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

		.vetedge-shell-product-logo-mark img {
			display: block;
			max-height: 100%;
			max-width: 100%;
			object-fit: contain;
		}

		.vetedge-owner-branding-card {
			background: var(--edge-color-surface, var(--card-bg, #fff));
			border: 1px solid var(--edge-color-border, var(--border-color, #dce5ef));
			border-radius: var(--edge-radius-lg, 1rem);
			display: grid;
			gap: 1rem;
			grid-template-columns: minmax(0, 1fr) auto;
			margin-bottom: var(--edge-section-gap, 1rem);
			padding: 1rem;
		}

		.vetedge-owner-branding-card__copy {
			display: grid;
			gap: .3rem;
		}

		.vetedge-owner-branding-card__copy h3 {
			color: var(--edge-color-ink-900, #1c2b3b);
			font-size: .88rem;
			margin: 0;
		}

		.vetedge-owner-branding-card__copy p,
		.vetedge-owner-branding-card__copy small {
			color: var(--edge-color-ink-500, #6b7d90);
			font-size: .72rem;
			line-height: 1.45;
			margin: 0;
		}

		.vetedge-owner-branding-card__control {
			align-items: center;
			display: flex;
			flex-wrap: wrap;
			gap: .55rem;
			justify-content: flex-end;
		}

		.vetedge-owner-branding-card__preview {
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

		.vetedge-owner-branding-card__preview img {
			max-height: 100%;
			max-width: 100%;
			object-fit: contain;
		}

		.vetedge-owner-branding-card__placeholder {
			color: var(--edge-color-ink-500, #6b7d90);
			font-size: .7rem;
			text-align: center;
		}

		@media (max-width: 47.99rem) {
			.vetedge-owner-branding-card {
				grid-template-columns: minmax(0, 1fr);
			}

			.vetedge-owner-branding-card__control {
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

	function callListener(listener, value) {
		const listeners = Array.isArray(listener) ? listener : [listener];
		listeners.forEach((entry) => {
			if (typeof entry === "function") entry(value);
		});
	}

	function openOwnerLogoUploader(onUploaded) {
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
			is_private: 0,
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

	function isPortalBrandingSchema(schema) {
		return (schema?.tabs || []).some((tab) => tab?.key === "portal_branding_tab");
	}

	function withoutPortalLogoField(schema) {
		return {
			...(schema || {}),
			tabs: (schema?.tabs || []).map((tab) => ({
				...tab,
				sections: (tab.sections || []).map((section) => ({
					...section,
					fields: (section.fields || []).filter((field) => field?.fieldname !== "portal_logo"),
				})),
			})),
		};
	}

	function renderOwnerPortalLogoCard(Vue, attrs) {
		const model = attrs.modelValue || {};
		const updateModel = attrs["onUpdate:modelValue"];
		const currentLogo = safeLogoUrl(model.portal_logo || "");
		const setLogo = (url) => {
			const next = { ...model, portal_logo: safeLogoUrl(url) };
			callListener(updateModel, next);
		};

		return Vue.h("section", { class: "vetedge-owner-branding-card", "aria-label": "Owner Portal Logo" }, [
			Vue.h("div", { class: "vetedge-owner-branding-card__copy" }, [
				Vue.h("h3", "Owner Portal Logo"),
				Vue.h("p", "Upload the tenant-owned logo shown on owner-facing portal and guest-booking surfaces."),
				Vue.h("small", "This logo does not change the VetEdge operational shell. Click Save Settings to keep the change."),
			]),
			Vue.h("div", { class: "vetedge-owner-branding-card__control" }, [
				Vue.h("span", { class: "vetedge-owner-branding-card__preview" }, [
					currentLogo
						? Vue.h("img", { src: currentLogo, alt: "Current owner portal logo", loading: "eager", decoding: "async" })
						: Vue.h("span", { class: "vetedge-owner-branding-card__placeholder" }, "No owner portal logo uploaded"),
				]),
				Vue.h(
					"button",
					{
						type: "button",
						class: "edge-button edge-button--primary",
						disabled: Boolean(attrs.readonly),
						onClick: () => openOwnerLogoUploader(setLogo),
					},
					currentLogo ? "Replace Logo" : "Upload Logo",
				),
				currentLogo
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
		const EdgeIcon = edgeUI.components?.EdgeIcon;
		const Vue = edgeUI.Vue;
		if (!CurrentShell || !Vue?.defineComponent || !Vue?.h || !edgeUI.registerComponent) return false;
		if (CurrentShell.__vetedgeProductBrandingShellWrapper) return true;

		const ProductBrandedVetEdgeShell = Vue.defineComponent({
			name: "ProductBrandedVetEdgeShell",
			inheritAttrs: false,
			setup(_props, context) {
				return () => {
					const attrs = context.attrs || {};
					const identity = bootIdentity();
					const productLogo = safeLogoUrl(identity.product_logo || "");
					const slots = { ...(context.slots || {}) };
					if (!slots.brand) {
						slots.brand = productLogo
							? () =>
								Vue.h("span", { class: "vetedge-shell-product-logo-mark" }, [
									Vue.h("img", { src: productLogo, alt: "", loading: "eager", decoding: "async" }),
								])
							: () =>
								Vue.h("span", { class: "vetedge-shell-generic-mark", "aria-hidden": "true" }, [
									EdgeIcon ? Vue.h(EdgeIcon, { name: identity.product_icon || "stethoscope", size: "md" }) : null,
								]);
					}
					return Vue.h(
						CurrentShell,
						{
							...attrs,
							class: [attrs.class, productLogo ? "vetedge-shell-has-product-logo" : "vetedge-shell-generic-product"],
							style: [attrs.style, productLogo ? { "--vetedge-shell-product-logo-image": cssUrl(productLogo) } : null],
						},
						slots,
					);
				};
			},
		});
		ProductBrandedVetEdgeShell.__vetedgeProductBrandingShellWrapper = true;
		edgeUI.registerComponent("EdgeAppShell", ProductBrandedVetEdgeShell, { replace: true });
		return true;
	}

	function installSettingsFormAdapter(edgeUI) {
		const CurrentForm = edgeUI.components?.EdgeDocumentForm;
		const Vue = edgeUI.Vue;
		if (!CurrentForm || !Vue?.defineComponent || !Vue?.h || !edgeUI.registerComponent) return false;
		if (CurrentForm.__vetedgeOwnerPortalBrandingFormWrapper) return true;

		const OwnerPortalBrandedDocumentForm = Vue.defineComponent({
			name: "OwnerPortalBrandedDocumentForm",
			inheritAttrs: false,
			setup(_props, context) {
				return () => {
					const attrs = context.attrs || {};
					const isPortalBranding = isPortalBrandingSchema(attrs.schema);
					const formAttrs = isPortalBranding
						? { ...attrs, schema: withoutPortalLogoField(attrs.schema) }
						: attrs;
					const children = [];
					if (isPortalBranding) children.push(renderOwnerPortalLogoCard(Vue, attrs));
					children.push(Vue.h(CurrentForm, formAttrs, context.slots || {}));
					return Vue.h("div", { class: "vetedge-branded-document-form" }, children);
				};
			},
		});
		OwnerPortalBrandedDocumentForm.__vetedgeOwnerPortalBrandingFormWrapper = true;
		edgeUI.registerComponent("EdgeDocumentForm", OwnerPortalBrandedDocumentForm, { replace: true });
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
			if (!state.shellInstalled) throw new Error("EdgeAppShell product-branding adapter could not be installed.");
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
		const identity = bootIdentity();
		return {
			...state,
			deploymentMode: identity.deployment_mode || "",
			productLogo: safeLogoUrl(identity.product_logo || ""),
			productLogoSource: identity.product_logo_source || "generic",
			ownerPortalLogo: safeLogoUrl(identity.owner_portal_logo || identity.tenant_logo || ""),
		};
	}

	window.VetEdgeBrandingUI = Object.assign(window.VetEdgeBrandingUI || {}, {
		install,
		diagnose,
	});
})();
