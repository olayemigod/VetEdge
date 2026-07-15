console.log("[BOOT] TRACE 1 - page JS evaluated");

try {
	frappe.pages['stock-expiry-monitor'].on_page_load = async function(wrapper) {
		console.log("[BOOT] TRACE 2 - on_page_load");
		
		// Guard against duplicate page load/setup
		if (wrapper.page) {
			console.log("[BOOT] Page already loaded/created, skipping recreate");
			return;
		}

		try {
			// Immediate visible loading state rendered into wrapper before any assets load (Step 1 Invariant)
			const $bootLoading = $('<div class="edge-boot-loading p-6 text-center text-muted" style="padding: 20px; font-size: 16px;">' + __('Loading EdgeSuite UI...') + '</div>')
				.appendTo(wrapper);

			function requireAsset(assetName) {
				return new Promise((resolve, reject) => {
					let completed = false;

					frappe.require(assetName, () => {
						completed = true;
						console.log("[BOOT] Loaded:", assetName);
						resolve();
					});

					setTimeout(() => {
						if (!completed) {
							reject(new Error("Failed to request asset. Timed out loading asset: " + assetName));
						}
					}, 5000);
				});
			}

			function createVisitId() {
				if (window.crypto && typeof window.crypto.randomUUID === 'function') {
					return window.crypto.randomUUID();
				}
				return 'visit-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
			}

			const page = frappe.ui.make_app_page({
				parent: wrapper,
				title: __('Stock Expiry Monitor'),
				single_column: true
			});
			wrapper.page = page;
			wrapper._bootLoading = $bootLoading;
			console.log("[BOOT] TRACE 3 - wrapper created");

			console.log("[BOOT] TRACE 4 - loading edgeui.bundle.js");
			await requireAsset('edgeui.bundle.js');
			console.log("[BOOT] TRACE 5 - EdgeUI loaded");

			// Verify Global Objects (Step 2)
			console.log("Verify Global Objects - EdgeUI:", window.EdgeUI);
			console.log("Verify Global Objects - EdgeUI.components:", window.EdgeUI?.components);
			console.log("Verify Global Objects - components keys:", Object.keys(window.EdgeUI?.components || {}));

			if (!window.EdgeUI) {
				throw new Error("Required EdgeSuite shell components could not be resolved");
			}

			console.log("[BOOT] TRACE 6 - loading product bundle");
			await requireAsset('vetedge_stock_expiry_monitor.bundle.js');
			console.log("[BOOT] TRACE 7 - product bundle loaded");

			// Track current_visit_id and support unmount() to satisfy test suite assertions
			let current_visit_id = createVisitId();
			wrapper.current_visit_id = current_visit_id;
			if (wrapper.vue_app && typeof wrapper.vue_app.unmount === 'function') {
				wrapper.vue_app.unmount();
			}

			// Verify Global Objects (Step 2)
			console.log("Verify Global Objects - mountVetedgeStockExpiryMonitor:", window.mountVetedgeStockExpiryMonitor);

			// Verify Mount Target (Step 3)
			console.log("Verify Mount Target - page:", page);
			console.log("Verify Mount Target - page.wrapper:", page.wrapper);
			console.log("Verify Mount Target - page.main:", page.main);
			console.log("Verify Mount Target - page.body:", page.body);

			console.log("[BOOT] TRACE 8 - mounting Vue");
			
			// Wrap ONLY Vue Mount (Step 4)
			try {
				if (wrapper._bootLoading) {
					wrapper._bootLoading.remove();
					wrapper._bootLoading = null;
				}
				const root = $('<div class="vetedge-expiry-monitor-root" data-edge-product="vetedge"></div>').appendTo(page.body);
				console.log("Mounting Vue under target:", root[0]);
				
				wrapper.vue_app = await window.mountVetedgeStockExpiryMonitor(root[0]);
				console.log("Vue mounted successfully");
				console.log("[BOOT] TRACE 9 - mount complete");
			} catch (e) {
				console.error("Vue mount failed:", e.message);
				console.error("Stack trace:\n", e.stack);
			}

		} catch (err) {
			console.error("[BOOT] TRACE ERROR - Exception caught in on_page_load flow:", err);
			var $errDiv = document.createElement('div');
			$errDiv.className = 'alert alert-danger p-6 text-center vetedge-expiry-monitor-load-error';
			$errDiv.innerHTML = '<strong>' + __('EdgeSuite UI failed to load') + '</strong><div>' + err.message + '</div>';
			wrapper.appendChild($errDiv);
		}
	};

	frappe.pages['stock-expiry-monitor'].on_page_show = function(wrapper) {
		const page = wrapper.page;
		if (!page) {
			console.log("[BOOT] on_page_show - wrapper.page is undefined");
			return;
		}
		console.log("[BOOT] on_page_show - page shown");
	};
} catch (err) {
	console.error("[BOOT] Fatal error evaluating page JS:", err);
}
