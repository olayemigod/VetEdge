(() => {
	if (window.VetEdgeMedicalHistoryUI?.version) return;

	const METRICS = [
		{ fieldname: 'temperature', label: __('Temperature'), unit: '°C' },
		{ fieldname: 'weight', label: __('Weight'), unit: 'kg' },
		{ fieldname: 'heart_rate', label: __('Heart Rate'), unit: 'bpm' },
		{ fieldname: 'respiratory_rate', label: __('Respiratory Rate'), unit: 'breaths/min' },
	];

	const escapeHtml = (value) => frappe.utils.escape_html(String(value ?? ''));
	const formatDateTime = (value) => value ? frappe.datetime.str_to_user(value) : '';
	const dateKey = (value) => String(value || '').slice(0, 10) || __('Unknown Date');
	const formatDateHeading = (value) => {
		if (!value || value === __('Unknown Date')) return value;
		try {
			return frappe.datetime.str_to_user(`${value} 00:00:00`).split(' ')[0];
		} catch (error) {
			return value;
		}
	};
	const sanitizeRichText = (value) => {
		if (!value) return '';
		const container = document.createElement('div');
		container.innerHTML = String(value);
		container.querySelectorAll('script, style, iframe, object, embed, link, meta').forEach((node) => node.remove());
		container.querySelectorAll('*').forEach((node) => {
			[...node.attributes].forEach((attribute) => {
				const name = attribute.name.toLowerCase();
				const attributeValue = attribute.value || '';
				if (name.startsWith('on') || (['href', 'src', 'xlink:href'].includes(name) && /^\s*javascript:/i.test(attributeValue))) {
					node.removeAttribute(attribute.name);
				}
			});
		});
		return container.innerHTML;
	};

	function summaryItem(label, value) {
		return `
			<div class="vetedge-history-summary-item">
				<small>${escapeHtml(label)}</small>
				<strong>${escapeHtml(value || __('Not Set'))}</strong>
			</div>
		`;
	}

	function renderSummary(summary = {}, fromDate = '', toDate = '') {
		return `
			<section class="vetedge-history-summary-card">
				<div class="vetedge-history-summary-heading">
					<div>
						<h4>${escapeHtml(summary.patient_name || summary.patient || __('Patient Medical History'))}</h4>
						<p>${escapeHtml(fromDate)} – ${escapeHtml(toDate)}</p>
					</div>
				</div>
				<div class="vetedge-history-summary-grid">
					${summaryItem(__('Species'), summary.species)}
					${summaryItem(__('Breed'), summary.breed)}
					${summaryItem(__('Owner'), summary.primary_owner)}
					${summaryItem(__('Default Branch'), summary.default_branch)}
					${summaryItem(__('Latest Consultation'), formatDateTime(summary.latest_consultation_date))}
					${summaryItem(__('Latest Weight'), summary.latest_weight)}
					${summaryItem(__('Latest Temperature'), summary.latest_temperature)}
				</div>
			</section>
		`;
	}

	function consultationEvent(row) {
		const symptoms = (row.symptoms || []).filter((entry) => entry?.value);
		const diagnoses = (row.diagnoses || []).filter((entry) => entry?.value);
		const treatments = row.treatment_plan || [];
		return {
			type: 'Consultation',
			doctype: 'Veterinary Consultation',
			name: row.name,
			timestamp: row.timestamp,
			title: row.title || row.name,
			meta: [row.practitioner, row.service_branch, row.status].filter(Boolean),
			body: `
				${row.presenting_complaint ? `<div><strong>${__('Complaint')}:</strong> ${escapeHtml(row.presenting_complaint)}</div>` : ''}
				${row.assessment_notes ? `<div class="vetedge-history-rich"><strong>${__('Assessment')}:</strong>${sanitizeRichText(row.assessment_notes)}</div>` : ''}
				${symptoms.length ? `<div><strong>${__('Symptoms')}:</strong> ${symptoms.map((entry) => escapeHtml(entry.value)).join(', ')}</div>` : ''}
				${diagnoses.length ? `<div><strong>${__('Diagnoses')}:</strong> ${diagnoses.map((entry) => escapeHtml(entry.value)).join(', ')}</div>` : ''}
				${row.treatment_plan_summary ? `<div class="vetedge-history-rich"><strong>${__('Treatment Plan')}:</strong>${sanitizeRichText(row.treatment_plan_summary)}</div>` : ''}
				${treatments.length ? `
					<div class="vetedge-history-treatment-list">
						<strong>${__('Treatment Items')}:</strong>
						${treatments.map((item) => `<span>${escapeHtml(item.item)} · ${escapeHtml(item.qty)} ${escapeHtml(item.uom || '')}</span>`).join('')}
					</div>
				` : ''}
			`,
		};
	}

	function vitalsEvent(row) {
		const values = METRICS
			.filter((metric) => row[metric.fieldname] !== null && row[metric.fieldname] !== undefined && row[metric.fieldname] !== '')
			.map((metric) => `<span><strong>${escapeHtml(metric.label)}:</strong> ${escapeHtml(row[metric.fieldname])} ${escapeHtml(metric.unit)}</span>`)
			.join('');
		return {
			type: 'Vitals',
			doctype: 'Veterinary Vital Signs',
			name: row.name,
			timestamp: row.timestamp,
			title: row.title || __('Vitals Recorded'),
			meta: [row.recorded_by, row.service_branch, row.consultation].filter(Boolean),
			body: `<div class="vetedge-history-vital-values">${values || `<span>${__('No chartable vital values recorded.')}</span>`}</div>${row.notes ? `<p>${escapeHtml(row.notes)}</p>` : ''}`,
		};
	}

	function labEvent(row) {
		return {
			type: 'Laboratory',
			doctype: 'Veterinary Lab Order',
			name: row.name,
			timestamp: row.timestamp,
			title: row.title || row.name || __('Laboratory Order'),
			meta: [row.status, row.service_branch, row.consultation].filter(Boolean),
			body: `
				${row.tests_summary ? `<div><strong>${__('Tests')}:</strong> ${escapeHtml(row.tests_summary)}</div>` : ''}
				${row.results_summary ? `<div><strong>${__('Results')}:</strong> ${escapeHtml(row.results_summary)}</div>` : ''}
			`,
		};
	}

	function vaccinationEvent(row) {
		return {
			type: 'Vaccination',
			doctype: 'Veterinary Vaccination Record',
			name: row.name,
			timestamp: row.timestamp,
			title: row.vaccine || row.title || row.name || __('Vaccination'),
			meta: [row.status, row.administered_by_name, row.service_branch].filter(Boolean),
			body: `
				${row.next_due_date ? `<div><strong>${__('Next Due')}:</strong> ${escapeHtml(row.next_due_date)}</div>` : ''}
				${row.linked_consultation ? `<div><strong>${__('Consultation')}:</strong> ${escapeHtml(row.linked_consultation)}</div>` : ''}
			`,
		};
	}

	function buildEvents(data = {}) {
		return [
			...(data.consultations || []).map(consultationEvent),
			...(data.vitals || []).map(vitalsEvent),
			...(data.labs || []).map(labEvent),
			...(data.vaccinations || []).map(vaccinationEvent),
		].sort((left, right) => String(right.timestamp || '').localeCompare(String(left.timestamp || '')));
	}

	function groupTimelineByDate(data = {}) {
		const grouped = new Map();
		for (const event of buildEvents(data)) {
			const key = dateKey(event.timestamp);
			if (!grouped.has(key)) grouped.set(key, []);
			grouped.get(key).push(event);
		}
		return [...grouped.entries()];
	}

	function renderTimeline(data = {}) {
		const groups = groupTimelineByDate(data);
		if (!groups.length) {
			return `<section class="vetedge-history-empty">${__('No medical history records in this date range.')}</section>`;
		}
		return groups.map(([date, events]) => `
			<section class="vetedge-history-day">
				<header>
					<h5>${escapeHtml(formatDateHeading(date))}</h5>
					<span>${events.length} ${events.length === 1 ? __('record') : __('records')}</span>
				</header>
				<div class="vetedge-history-day-events">
					${events.map((event) => `
						<article class="vetedge-history-event">
							<div class="vetedge-history-event-marker"></div>
							<div class="vetedge-history-event-card">
								<div class="vetedge-history-event-heading">
									<div>
										<span class="vetedge-history-event-type">${escapeHtml(event.type)}</span>
										<h6>${escapeHtml(event.title)}</h6>
										<small>${escapeHtml(formatDateTime(event.timestamp))}</small>
									</div>
									${event.name ? `<button type="button" class="btn btn-default btn-xs" data-history-doctype="${escapeHtml(event.doctype)}" data-history-name="${escapeHtml(event.name)}">${__('Open')}</button>` : ''}
								</div>
								${event.meta.length ? `<div class="vetedge-history-event-meta">${event.meta.map((value) => `<span>${escapeHtml(value)}</span>`).join('')}</div>` : ''}
								<div class="vetedge-history-event-body">${event.body || ''}</div>
							</div>
						</article>
					`).join('')}
				</div>
			</section>
		`).join('');
	}

	function styles() {
		return `
			<style>
				.vetedge-history-shell { display: grid; gap: 16px; }
				.vetedge-history-summary-card, .vetedge-history-chart-card, .vetedge-history-day { border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-bg); }
				.vetedge-history-summary-card, .vetedge-history-chart-card { padding: 16px; }
				.vetedge-history-summary-heading h4 { margin: 0; }
				.vetedge-history-summary-heading p { margin: 4px 0 0; color: var(--text-muted); }
				.vetedge-history-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
				.vetedge-history-summary-item { padding: 10px; border-radius: 8px; background: var(--subtle-fg); }
				.vetedge-history-summary-item small, .vetedge-history-summary-item strong { display: block; }
				.vetedge-history-summary-item small { color: var(--text-muted); margin-bottom: 3px; }
				.vetedge-history-chart-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
				.vetedge-history-chart-tabs button.is-active { background: var(--primary); color: var(--fg-color); border-color: var(--primary); }
				.vetedge-history-chart-canvas { min-height: 240px; }
				.vetedge-history-day { overflow: hidden; }
				.vetedge-history-day > header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: var(--subtle-fg); }
				.vetedge-history-day > header h5 { margin: 0; }
				.vetedge-history-day > header span { color: var(--text-muted); }
				.vetedge-history-day-events { padding: 14px 16px; }
				.vetedge-history-event { display: grid; grid-template-columns: 14px minmax(0, 1fr); gap: 10px; position: relative; }
				.vetedge-history-event:not(:last-child)::before { content: ''; position: absolute; left: 6px; top: 18px; bottom: -12px; border-left: 1px solid var(--border-color); }
				.vetedge-history-event-marker { width: 12px; height: 12px; border-radius: 50%; background: var(--primary); margin-top: 10px; z-index: 1; }
				.vetedge-history-event-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 12px; margin-bottom: 12px; }
				.vetedge-history-event-heading { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
				.vetedge-history-event-heading h6 { margin: 2px 0; }
				.vetedge-history-event-heading small, .vetedge-history-event-meta { color: var(--text-muted); }
				.vetedge-history-event-type { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
				.vetedge-history-event-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; font-size: 12px; }
				.vetedge-history-event-meta span:not(:last-child)::after { content: '•'; margin-left: 8px; }
				.vetedge-history-event-body { display: grid; gap: 7px; margin-top: 10px; }
				.vetedge-history-vital-values { display: flex; flex-wrap: wrap; gap: 10px; }
				.vetedge-history-treatment-list { display: flex; flex-wrap: wrap; gap: 6px; }
				.vetedge-history-treatment-list strong { width: 100%; }
				.vetedge-history-treatment-list span { padding: 4px 8px; border-radius: 999px; background: var(--subtle-fg); }
				.vetedge-history-rich p:last-child { margin-bottom: 0; }
				.vetedge-history-empty { padding: 28px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: 10px; }
				@media (max-width: 992px) { .vetedge-history-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
				@media (max-width: 576px) { .vetedge-history-summary-grid { grid-template-columns: 1fr; } .vetedge-history-event-heading { flex-direction: column; } }
			</style>
		`;
	}

	function renderChart(wrapper, trends = {}, metric = METRICS[0]) {
		const element = wrapper.querySelector('.vetedge-history-chart-canvas');
		if (!element) return;
		element.innerHTML = '';
		const rows = trends[metric.fieldname] || [];
		if (!rows.length) {
			element.innerHTML = `<div class="vetedge-history-empty">${__('No {0} readings in this date range.', [metric.label])}</div>`;
			return;
		}
		new frappe.Chart(element, {
			title: `${metric.label} ${__('Trend')}`,
			data: {
				labels: rows.map((row) => formatDateTime(row.timestamp)),
				datasets: [{ name: metric.label, values: rows.map((row) => row.value) }],
			},
			type: 'line',
			height: 240,
			lineOptions: { hideDots: 0, regionFill: 0 },
			axisOptions: { xIsSeries: 1 },
			tooltipOptions: { formatTooltipY: (value) => `${value} ${metric.unit}` },
		});
	}

	function render(target, data = {}) {
		const wrapper = target instanceof HTMLElement ? target : target?.[0];
		if (!wrapper) return;
		wrapper.innerHTML = `
			${styles()}
			<div class="vetedge-history-shell">
				${renderSummary(data.summary || {}, data.from_date || '', data.to_date || '')}
				<section class="vetedge-history-chart-card">
					<div class="vetedge-history-chart-tabs">
						${METRICS.map((metric, index) => `<button type="button" class="btn btn-default btn-sm ${index === 0 ? 'is-active' : ''}" data-vital-metric="${metric.fieldname}">${escapeHtml(metric.label)}</button>`).join('')}
					</div>
					<div class="vetedge-history-chart-canvas"></div>
				</section>
				<div class="vetedge-history-timeline">${renderTimeline(data)}</div>
			</div>
		`;
		let activeMetric = METRICS[0];
		const draw = () => renderChart(wrapper, data.trends || {}, activeMetric);
		wrapper.querySelectorAll('[data-vital-metric]').forEach((button) => {
			button.addEventListener('click', () => {
				activeMetric = METRICS.find((metric) => metric.fieldname === button.dataset.vitalMetric) || METRICS[0];
				wrapper.querySelectorAll('[data-vital-metric]').forEach((item) => item.classList.remove('is-active'));
				button.classList.add('is-active');
				draw();
			});
		});
		wrapper.querySelectorAll('[data-history-doctype][data-history-name]').forEach((button) => {
			button.addEventListener('click', () => frappe.set_route('Form', button.dataset.historyDoctype, button.dataset.historyName));
		});
		window.requestAnimationFrame?.(draw);
	}

	function fetchHistory(patient, fromDate, toDate, limit = 100) {
		return frappe.call({
			method: 'vetedge.services.medical_history.get_patient_medical_history_view',
			args: { patient, from_date: fromDate, to_date: toDate, limit },
		}).then((response) => response.message || {});
	}

	function openDialog({ patient, patientLabel = '', onClose = null } = {}) {
		if (!patient) {
			frappe.msgprint(__('Select a patient before opening Medical History.'));
			return null;
		}
		const dialog = new frappe.ui.Dialog({
			title: __('Medical History: {0}', [patientLabel || patient]),
			size: 'extra-large',
			fields: [
				{ fieldname: 'from_date', fieldtype: 'Date', label: __('From Date'), default: frappe.datetime.add_days(frappe.datetime.get_today(), -90), reqd: 1 },
				{ fieldname: 'date_column_break', fieldtype: 'Column Break' },
				{ fieldname: 'to_date', fieldtype: 'Date', label: __('To Date'), default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: 'history_section', fieldtype: 'Section Break' },
				{ fieldname: 'history_html', fieldtype: 'HTML' },
			],
			primary_action_label: __('Refresh'),
			primary_action: () => load(),
			secondary_action_label: __('Open Full History'),
			secondary_action: () => {
				frappe.route_options = { patient };
				frappe.set_route('veterinary-medical-history');
			},
		});
		const body = dialog.fields_dict.history_html.$wrapper[0];
		async function load() {
			const fromDate = dialog.get_value('from_date');
			const toDate = dialog.get_value('to_date');
			if (fromDate && toDate && fromDate > toDate) {
				frappe.msgprint(__('From Date cannot be after To Date.'));
				return;
			}
			body.innerHTML = `<div class="vetedge-history-empty">${__('Loading medical history...')}</div>`;
			try {
				const data = await fetchHistory(patient, fromDate, toDate, 100);
				render(body, data);
			} catch (error) {
				body.innerHTML = `<div class="alert alert-danger">${escapeHtml(error?.message || __('Medical history could not load.'))}</div>`;
			}
		}
		dialog.$wrapper.on('hidden.bs.modal', () => onClose?.());
		dialog.show();
		load();
		return dialog;
	}

	window.VetEdgeMedicalHistoryUI = Object.freeze({
		version: '1.0.0-phase5',
		metrics: METRICS,
		buildEvents,
		groupTimelineByDate,
		fetchHistory,
		render,
		openDialog,
	});
})();
