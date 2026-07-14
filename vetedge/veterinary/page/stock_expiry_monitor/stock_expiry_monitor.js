// stock_expiry_monitor.js
console.log("[BOOT] TRACE 1 - page JS evaluated");

try {
	frappe.pages['stock-expiry-monitor'].on_page_load = async function(wrapper) {
		console.log("[BOOT] TRACE 2 - on_page_load");
		try {
			// Immediate visible loading state rendered into wrapper before any assets load (Step 1 Invariant)
			const $bootLoading = $('<div class="edge-boot-loading p-6 text-center text-muted" style="padding: 20px; font-size: 16px;">' + __('Loading EdgeSuite UI...') + '</div>')
				.appendTo(wrapper);

			function requireAsync(asset) {
				return new Promise((resolve, reject) => {
					let completed = false;

					frappe.require(asset, () => {
						completed = true;
						console.log("[BOOT] Loaded:", asset);
						resolve();
					});

					setTimeout(() => {
						if (!completed) {
							reject(new Error("Timed out loading " + asset));
						}
					}, 5000);
				});
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
			await requireAsync('edgeui.bundle.js');
			console.log("[BOOT] TRACE 5 - EdgeUI loaded");

			// Verify Global Objects (Step 2)
			console.log("Verify Global Objects - EdgeUI:", window.EdgeUI);
			console.log("Verify Global Objects - EdgeUI.components:", window.EdgeUI?.components);
			console.log("Verify Global Objects - components keys:", Object.keys(window.EdgeUI?.components || {}));

			console.log("[BOOT] TRACE 6 - loading product bundle");
			await requireAsync('vetedge_stock_expiry_monitor.bundle.js');
			console.log("[BOOT] TRACE 7 - product bundle loaded");

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
				
				await window.mountVetedgeStockExpiryMonitor(root[0]);
				console.log("Vue mounted successfully");
				console.log("[BOOT] TRACE 9 - mount complete");
			} catch (e) {
				console.error("Vue mount failed:", e.message);
				console.error("Stack trace:\n", e.stack);
			}

		} catch (err) {
			console.error("[BOOT] TRACE ERROR - Exception caught in on_page_load flow:", err);
			var $errDiv = document.createElement('div');
			$errDiv.className = 'alert alert-danger p-6 text-center';
			$errDiv.innerHTML = '<strong>' + __('EdgeSuite page controller failed') + '</strong><div>' + err.message + '</div>';
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
