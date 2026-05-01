frappe.listview_settings["Kennel Availability"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Refresh Availability"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Refresh Kennel Availability"),
				fields: [
					{ fieldtype: "Date", fieldname: "snapshot_date", label: __("Snapshot Date"), default: frappe.datetime.get_today(), reqd: 1 },
					{ fieldtype: "Link", fieldname: "service_branch", label: __("Service Branch"), options: "Branch" },
				],
				primary_action_label: __("Refresh"),
				primary_action(values) {
					frappe.call({
						method: "vetedge.services.boarding.refresh_kennel_availability",
						args: values,
						freeze: true,
						freeze_message: __("Refreshing kennel availability..."),
						callback() {
							dialog.hide();
							listview.refresh();
						},
					});
				},
			});
			dialog.show();
		});
	},
	get_indicator(doc) {
		const map = {
			Available: [__("Available"), "green", "availability_status,=,Available"],
			Limited: [__("Limited"), "orange", "availability_status,=,Limited"],
			Full: [__("Full"), "red", "availability_status,=,Full"],
			Inactive: [__("Inactive"), "gray", "availability_status,=,Inactive"],
		};
		return map[doc.availability_status] || [__(doc.availability_status || "Unknown"), "blue", "availability_status,=," + (doc.availability_status || "")];
	},
};
