(function () {
	if (window.__vetedgeMedicalHistoryQaPatchInstalled) return;
	window.__vetedgeMedicalHistoryQaPatchInstalled = true;

	function scheduleChart(view) {
		const run = () => {
			if (!view || view.loading) return;
			const target = view.$refs?.trendChart;
			if (!target || !view.activeTrendRows?.length) return;
			view.renderTrendChart?.();
		};
		requestAnimationFrame(() => requestAnimationFrame(run));
		window.setTimeout(run, 80);
	}

	function patchComponent() {
		const component = window.VeterinaryMedicalHistory;
		if (!component || component.__vetedgeQaReadabilityPatched) return false;
		const methods = component.methods || {};
		const originalLoad = methods.load;
		const originalOpenRow = methods.openHistoryRow;
		component.methods = {
			...methods,
			async load(...args) {
				const result = await originalLoad?.apply(this, args);
				await this.$nextTick?.();
				scheduleChart(this);
				return result;
			},
			openHistoryRow(row) {
				if (!row) return;
				const mapping = {
					labs: ["Veterinary Lab Order", row.name],
					vaccinations: ["Veterinary Vaccination Record", row.name || row.vaccination],
					vitals: ["Veterinary Vital Signs", row.name || row.vitals],
				};
				const target = mapping[this.activeHistory];
				if (target?.[1] && window.VetEdgeClinicalRecordEditor?.open) {
					window.VetEdgeClinicalRecordEditor.open({
						doctype: target[0],
						name: target[1],
						onSaved: () => this.ensureHistorySection?.(this.activeHistory, { force: true }),
					});
					return;
				}
				return originalOpenRow?.call(this, row);
			},
		};
		const previousWatch = component.watch || {};
		const originalTrendWatch = previousWatch.activeTrend;
		component.watch = {
			...previousWatch,
			async activeTrend(value, oldValue) {
				if (typeof originalTrendWatch === "function") await originalTrendWatch.call(this, value, oldValue);
				await this.$nextTick?.();
				scheduleChart(this);
			},
		};
		component.__vetedgeQaReadabilityPatched = true;
		return true;
	}

	window.VetEdgeMedicalHistoryQaPatch = { install: patchComponent };
	patchComponent();
})();
