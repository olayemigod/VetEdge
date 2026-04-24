window.vetedgeListIndicators = window.vetedgeListIndicators || {
	color(status, palette) {
		return (palette || {})[status] || "gray";
	},

	buildStatusIndicator(doc, filters, statusField = "status") {
		const status = doc[statusField];
		const color = this.color(status, filters || {});
		return [__(status || "Unknown"), color, `${statusField},=,${status}`];
	},
};
