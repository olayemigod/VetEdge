# VHOME-01B Navigation Hardening

## Trigger

Post-submission Veterinary Home QA identified two navigation defects on the accepted local `vetedge.local` QA composition:

1. Home appeared as a one-item collapsible section containing a redundant Veterinary Home child item.
2. The Product Menu control could be present in an EdgeSuite shell without a usable shared product-menu host/trigger interaction.

## Scope

VHOME-01B remains on VetEdge PR #60 (`feature/vetedge-smart-home-vhome01`) stacked on authoritative PR #57. It does not modify the pinned EdgeSuite UI candidate or any clinical, billing, stock, accounting or hospitalisation workflow.

### Direct Home

The post-QA navigation bridge recognises the EdgeSuite Veterinary Home section, removes the redundant disclosure chevron from the visible Home control, hides the nested one-item Veterinary Home container, and routes the visible Home control directly to `/desk/vetedge` through the existing VetEdge navigation adapter.

Other sidebar sections retain their normal accordion behaviour.

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

`VetEdge VHOME-01B Navigation Validation` performs syntax/loader checks and a real Chromium smoke that reproduces the missing-native-host condition. It asserts:

- Home is patched as a direct control and the redundant nested item is hidden.
- Clicking Home routes to `/desk/vetedge`.
- A canonical product-menu trigger is available in the visible EdgeSuite topbar.
- Product Menu opens, search remains usable, an item navigates through the registered product configuration, and the menu closes.
