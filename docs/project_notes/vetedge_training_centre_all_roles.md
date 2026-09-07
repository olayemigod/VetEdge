# VetEdge Training Centre — All-Roles Expansion

## Scope

This change expands the manifest-backed Veterinary Training Centre from a doctor-only catalogue into a role-aware learning centre for every current VetEdge starter operational bundle.

## Access Contract

- Every recognised VetEdge operational role receives `Shared Operations`.
- Each role receives only its specialist training group.
- Front Desk and Branch Manager also receive `Boarding Operations` because there is no separate boarding starter role.
- VetEdge Administrator and System Manager receive the complete published catalogue for training governance.
- Supplemental ERPNext roles such as `Accounts User`, `Sales User` or `Stock User` do not expose VetEdge training by themselves.
- Training visibility never grants DocType, page, report, branch, stock or accounting permission.

## Published Training Groups

1. Shared Operations
2. Owner & Administration
3. Branch Management
4. Doctor Operations
5. Nursing Operations
6. Front Desk Operations
7. Accounts & Billing
8. Dispensary & Stock
9. Laboratory Operations
10. Grooming Operations
11. Boarding Operations

## Content Baseline

The expanded modules cover Veterinary Home, EdgeSuite navigation and appearance, Medical History completion rules, safe handoffs, Veterinary Settings, Billing Center, hospitalisation, VCN/NADIS reporting, ERPNext procurement/stock/sales/accounting essentials and each specialist role workflow.

Medical History training follows the implemented source rule:

- saved consultations and structured Vital Signs contribute clinical context;
- Lab Orders appear only at workflow status `Completed`;
- Vaccination Records appear only at workflow status `Administered`;
- Hospitalisation contributes admission, non-duplicated activity and discharge events;
- billing does not create clinical history, although a payment gate may delay the clinical completion action.

## Validation

- Manifest JSON parses successfully.
- All module IDs are unique.
- All Markdown paths resolve inside the approved training directory.
- All internal `training-module:` links resolve.
- Expanded modules include practice exercises and screenshot capture references.
- Training Centre service and shell contract tests pass.

## Deployment Note

This branch is stacked on the PR 61 training source baseline. Rebase or retarget only after preserving the PR 61 Veterinary Home, navigation and Billing Center contracts.

