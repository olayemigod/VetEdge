# VetEdge EdgeSuite UI Phase 2B Review

## Goal

Migrate pricing- and service-sensitive Veterinary masters into a dedicated full EdgeSuite UI workspace without bypassing Frappe permissions, controller validation, ERPNext Item rules or existing pricing and stock side effects.

## Scope

- Veterinary Treatment Item
- Veterinary Treatment Type
- Veterinary Lab Test
- Veterinary Vaccine
- Pet Grooming Service

Operational Consultation, Lab Order, Vaccination Record, Grooming Appointment, Grooming Session, Sales Invoice, Payment Entry and Stock Entry documents remain outside this provider.

## Implementation

- Added `/app/vetedge-pricing-master-workspace`.
- Added permission-aware list, search, filters, pagination, create, edit and delete.
- Preserved DocType sections and conditional-field metadata in EdgeSuite forms.
- Made autoname identity fields read-only after creation.
- Added optimistic timestamp protection.
- Added server-filtered Link options and matching backend validation.
- Redirected all five native list and form routes into the EdgeSuite workspace.
- Added save-behaviour notices before users change pricing or stock-sensitive values.

## Smart Link Rules

- Treatment Item: enabled sales Items; active Service Type and Treatment Type; enabled selling Price List.
- Treatment Type: enabled sales Item for the optional default Item.
- Lab Test: enabled non-stock sales Item; enabled selling Price List.
- Vaccine: active Species; enabled sales Item, whether stock or non-stock; enabled selling Price List.
- Grooming Service: enabled non-stock sales Item.

Frontend filtering is not trusted alone. The same rules are enforced by the backend workspace service, and existing DocType controllers still run during `doc.insert()` and `doc.save()`.

## Pricing and Stock Side Effects

### Treatment Item

- Positive Default Price continues to update or create ERPNext Item Price through `sync_master_item_price`.
- Positive Shelf Life continues to update the linked ERPNext Item shelf-life setting through the existing Treatment Item controller.

### Lab Test

- Positive Default Price continues to update or create ERPNext Item Price for the linked non-stock billing Item.

### Vaccine

- Positive Default Price continues to update or create ERPNext Item Price for the linked stock or non-stock sales Item.

### Grooming Service

- Default Rate remains a VetEdge grooming-service default.
- It does not silently create or mutate ERPNext Item Price because the existing Grooming Service controller does not perform that synchronisation.

### Treatment Type

- The optional default Item is validated as an enabled sales Item.
- No Item Price or stock document is changed.

## Accounting and Stock Safety

The workspace does not create, submit, cancel or mutate Sales Invoice, Payment Entry or Stock Entry records. It does not mutate submitted accounting documents. Any Item Price or Item shelf-life change occurs only through existing master controller behaviour after a normal permitted document save.

## Review Findings

- A generic clinical-reference provider was not sufficient because these masters have pricing and stock implications.
- A dedicated pricing-aware workspace was created instead of expanding Phase 2A blindly.
- Autoname fields are locked after insert to prevent document-name and identity-field divergence.
- Lab Test and Grooming Service exclude stock Items because their current controllers require non-stock billing Items.
- Vaccine permits stock Items because vaccination administration may consume batches.
- Existing dependent-field conditions and grouped sections are preserved in the generated EdgeSuite schema.
- Native routes redirect into one consistent interface.

## Automated Tests

- Static scope, safety, Link-filter, route and EdgeSuite component contracts.
- Python compilation and Ruff.
- JavaScript syntax checks for the bundle, loader and all redirects.
- Clean Frappe v16 bench and standalone VetEdge site.
- EdgeSuite UI and VetEdge asset builds and migration.
- Live metadata, list and permission contracts.
- Stock versus non-stock Item filtering.
- Controller-driven Item Price and shelf-life synchronisation.
- Immutable identity fields.
- Optimistic-lock rejection.
- Inactive Species and negative-value rejection.

## Manual QA Status

Manual browser, mobile and role-by-role QA remains pending and should be performed with the grouped EdgeSuite migration QA session. The Phase 2B pull request must remain draft until that acceptance is complete.
