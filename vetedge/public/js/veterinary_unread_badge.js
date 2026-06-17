(function () {
	const BADGE_ID = "veterinary-unread-bell-badge";
	const API_METHOD = "vetedge.services.notification_api.get_my_veterinary_unread_bell_count";
	const MARK_LOG_METHOD = "vetedge.services.notification_api.mark_my_veterinary_notification_read_for_log";

	function __(text) {
		return window.__ ? window.__(text) : text;
	}

	function getExisting() {
		return document.getElementById(BADGE_ID);
	}

	function findAnchor() {
		const selectors = [
			".standard-items-sections .sidebar-notification",
			".sidebar-notification",
			".notifications-icon",
			".dropdown-notifications",
			".navbar .navbar-nav.ms-auto",
			".navbar .navbar-nav.ml-auto",
			".navbar .navbar-right",
		];
		for (const selector of selectors) {
			const element = document.querySelector(selector);
			if (element) {
				return element;
			}
		}
		return null;
	}

	function createBadge() {
		const badge = document.createElement("button");
		badge.id = BADGE_ID;
		badge.type = "button";
		badge.className = "veterinary-unread-bell-badge hidden";
		badge.title = __("Veterinary notifications");
		badge.setAttribute("aria-label", __("Veterinary unread notifications"));
		badge.innerHTML = `<span class="veterinary-unread-bell-badge-label">${__("Veterinary")}</span><span class="veterinary-unread-bell-badge-count">0</span>`;
		badge.addEventListener("click", openNativeNotifications);
		return badge;
	}

	function ensureBadge() {
		const existingBadges = Array.from(document.querySelectorAll("#" + BADGE_ID));
		if (existingBadges.length > 1) {
			existingBadges.slice(1).forEach((badge) => badge.remove());
		}
		if (existingBadges[0] && document.body.contains(existingBadges[0])) {
			return existingBadges[0];
		}

		const anchor = findAnchor();
		if (!anchor || !anchor.parentNode) {
			return null;
		}

		const badge = createBadge();
		if (anchor.classList.contains("sidebar-notification")) {
			anchor.insertAdjacentElement("afterend", badge);
		} else if (anchor.classList.contains("dropdown-notifications")) {
			anchor.parentNode.insertBefore(badge, anchor);
		} else {
			anchor.insertAdjacentElement("afterend", badge);
		}
		return badge;
	}

	function setCount(count) {
		const badge = ensureBadge();
		if (!badge) {
			return;
		}
		const unreadCount = Number(count || 0);
		const countElement = badge.querySelector(".veterinary-unread-bell-badge-count");
		if (countElement) {
			countElement.textContent = unreadCount > 99 ? "99+" : String(unreadCount);
		}
		badge.classList.toggle("hidden", unreadCount <= 0);
	}

	function refreshCount() {
		if (!window.frappe || !frappe.call) {
			return;
		}
		ensureBadge();
		frappe.call({
			method: API_METHOD,
			callback(response) {
				setCount(response && response.message ? response.message.unread_count : 0);
			},
			error() {
				setCount(0);
			},
		});
	}

	function markNativeNotificationRead(notificationLog) {
		if (!notificationLog || !window.frappe || !frappe.call) {
			return;
		}
		frappe.call({
			method: MARK_LOG_METHOD,
			args: { notification_log: notificationLog },
			callback(response) {
				setCount(response && response.message ? response.message.unread_count : 0);
			},
		});
	}

	function openNativeNotifications() {
		const nativeButton = document.querySelector(".standard-items-sections .sidebar-notification");
		if (nativeButton) {
			nativeButton.click();
			return;
		}
		if (window.frappe && frappe.set_route) {
			frappe.route_options = {
				for_user: frappe.session && frappe.session.user,
				read: 0,
			};
			frappe.set_route("List", "Notification Log");
		}
	}

	function scheduleRefresh(delay) {
		window.setTimeout(refreshCount, delay);
	}

	function bindEvents() {
		if (window.frappe && frappe.router && frappe.router.on) {
			frappe.router.on("change", function () {
				scheduleRefresh(250);
				scheduleRefresh(1000);
			});
		}
		if (window.frappe && frappe.realtime && frappe.realtime.on) {
			frappe.realtime.on("notification", function () {
				scheduleRefresh(250);
			});
		}
		document.addEventListener("visibilitychange", function () {
			if (!document.hidden) {
				refreshCount();
			}
		});
		document.addEventListener(
			"click",
			function (event) {
				const item = event.target.closest(".notification-item[data-name]");
				if (!item) {
					return;
				}
				markNativeNotificationRead(item.getAttribute("data-name"));
				scheduleRefresh(750);
				scheduleRefresh(1500);
			},
			true
		);
	}

	function boot() {
		ensureBadge();
		refreshCount();
		scheduleRefresh(500);
		scheduleRefresh(1500);
		bindEvents();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", boot);
	} else {
		boot();
	}
})();
