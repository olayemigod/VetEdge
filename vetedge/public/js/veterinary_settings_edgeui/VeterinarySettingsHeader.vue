<template>
	<section class="veterinary-settings-edgeui-surface" data-edge-product="veterinary">
		<EdgePageHeader
			eyebrow="Veterinary Practice Management"
			title="Veterinary Settings"
			subtitle="Configure clinic branding, clinical workflows, billing controls, notifications, and operational defaults."
		/>
		<div class="veterinary-settings-edgeui-brand">
			<div class="veterinary-settings-edgeui-logo">
				<img v-if="logoUrl" :src="logoUrl" alt="Clinic logo" />
				<span v-else>V</span>
			</div>
			<div>
				<p class="edge-eyebrow">Clinic branding</p>
				<strong>{{ brandName || "Veterinary Clinic" }}</strong>
				<small>The saved branding values are used in the clinic header.</small>
			</div>
		</div>
		<div class="veterinary-settings-edgeui-badges">
			<EdgeStatusBadge label="Clinic Branding" status="default" tone="success" />
			<EdgeStatusBadge label="Clinical Workflows" status="default" tone="neutral" />
			<EdgeStatusBadge label="Billing and Payments" status="default" tone="neutral" />
			<EdgeStatusBadge label="Notifications" status="default" tone="neutral" />
		</div>
	</section>
</template>

<script>
export default {
	name: "VeterinarySettingsHeader",
	props: {
		brandName: { type: String, default: "" },
		logoUrl: { type: String, default: "" },
	},
};
</script>
