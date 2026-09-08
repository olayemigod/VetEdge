# VHOME-01B Navigation Hardening

## Trigger

Post-submission Veterinary Home QA identified two navigation defects on the accepted local `vetedge.local` QA composition:

1. Home appeared as a one-item collapsible section containing a redundant Veterinary Home child item.
2. The Product Menu control could be present in an EdgeSuite shell without a usable shared product-menu host/trigger interaction.

A follow-up visual QA clarification also fixed the intended top-level sidebar contract: the direct item is labelled **Veterinary Home**, it has no disclosure/expand control, and the first operational groups are presented as **Dashboard**, **Clinical Operations**, and **Appointments**.

## Scope

VHOME-01B remains on VetEdge PR #60 (`feature/vetedge-smart-home-vhome01`) stacked on authoritative PR #57. It does not modify the pinned EdgeSuite UI candidate or any clinical, billing, stock, accounting or hospitalisation workflow.

### Direct Veterinary Home

The post-QA navigation bridge recognises the generated one-item Home section and replaces the whole accordion section with a single direct **Veterinary Home** sidebar item. The resulting item has no chevron, no `aria-expanded`/accordion state, no hidden nested Home item, and no second click. It routes directly to `/desk/vetedge` through the existing VetEdge navigation adapter.

The bridge also normalises the first operational group labels/order to:

1. Veterinary Home — direct navigation, never collapsible.
2. Dashboard — normal collapsible group.
3. Clinical Operations — normal collapsible group.
4. Appointments — normal collapsible group.

All remaining sidebar groups retain their existing relative order and normal accordion behaviour.

### Product Menu reliability

The bridge first allows the shared EdgeSuite product menu to mount normally. If its canonical trigger/panel is absent or the trigger is not usable in the visible VetEdge EdgeSuite shell, VetEdge reuses the shared product-menu IDs, configuration, rendering and navigation contract inside the visible EdgeSuite topbar. It does not introduce a second product-menu data model.

An unresponsive canonical trigger also receives a bounded open retry through the shared EdgeSuite runtime.

## Safety

- No ERPNext or VetEdge business document is written.
- No permission bypass is introduced.
- No accounting, stock, consultation, lab or hospitalisation workflow is altered.
- Native ERPNext pages remain governed by the existing product-menu native guard.
- The EdgeSuite UI candidate remains pinned at `8ba77eaee73ebd4466ec25dd27afb55154bd97cd`.

## Automated regression

`VetEdge VHOME-01B Navigation Validation` performs syntax/loader checks and a real Chromium smoke that reproduces the generated one-item Home section and missing-native-host condition. It asserts:

- the generated Home accordion is replaced by exactly one direct `Veterinary Home` item;
- `Veterinary Home` has no expansion state or redundant nested item;
- the primary sidebar sequence is `Veterinary Home`, `Dashboard`, `Clinical Operations`, `Appointments`;
- clicking Veterinary Home routes to `/desk/vetedge`;
- a canonical product-menu trigger is available in the visible EdgeSuite topbar;
- Product Menu opens, search remains usable, an item navigates through the registered product configuration, and the menu closes.
