# ProcessEdge Veterinary Branding Contract

## Purpose

This document defines the production branding contract for the VetEdge codebase.

The technical Frappe app, Python package, repository identity, routes, workspace keys, role names, DocType names, patches, and API namespaces remain `vetedge` / `VetEdge` where they are internal compatibility identifiers.

The ProcessEdge-owned production product name is **ProcessEdge Veterinary**.

The operational workspace label remains **Veterinary**.

## Production assets

- App/icon mark: `/assets/vetedge/images/processedge-veterinary-app-icon.png`
- Horizontal product logo: `/assets/vetedge/images/processedge-veterinary-logo-horizontal.svg`
- Stacked product logo: `/assets/vetedge/images/processedge-veterinary-logo-stacked.svg`
- Tagline: **Better Care. Better Practice.**
- Primary blue: `#0056A6`
- Dark blue: `#003E73`
- Primary green: `#1C9C5D`

## Deployment mode matrix

| Deployment mode | Product shell | Product logo | Clinic / tenant identity |
| --- | --- | --- | --- |
| `standalone` | ProcessEdge Veterinary by default | ProcessEdge Veterinary icon | Company / Veterinary Settings clinic identity remains separate |
| `shared_hosted` | ProcessEdge Veterinary | ProcessEdge Veterinary icon | CoreEdge / tenant clinic name and clinic logo remain separate from product identity |
| `white_label` with an active brand | Tenant-configured product name | Tenant-configured logo | Tenant / clinic branding |
| `white_label` without an active brand | Generic Veterinary | No ProcessEdge logo | Generic clinic identity until configured |

A white-label deployment must never fall back to ProcessEdge Veterinary branding simply because tenant branding is incomplete.

## Branding priority

The raw branding resolver keeps the existing priority:

1. Active CoreEdge product branding
2. Explicit `site_config` white-label branding
3. Distribution defaults

Visible product-shell branding must be resolved through `vetedge.services.branding.get_shell_branding()`, which adds deployment-mode safety on top of the raw resolver.

## White-label safety

For `white_label` mode:

- Do not expose ProcessEdge Veterinary name, icon, logo, or favicon as a fallback.
- Missing tenant app title falls back to **Veterinary**.
- Missing tenant logo remains blank rather than using the ProcessEdge logo.
- Tenant branding may override visible app title, launcher logo, navbar logo, and website product identity.
- Internal route and database keys remain unchanged.

## Shared-hosted / ProcessEdge SaaS behaviour

For `shared_hosted` mode:

- Product shell: **ProcessEdge Veterinary**
- Operational workspace label: **Veterinary**
- Tenant name: resolved clinic / company / CoreEdge tenant name
- Tenant logo: resolved clinic / company / CoreEdge tenant logo

This separation allows a clinic to see its own identity alongside the ProcessEdge Veterinary product identity.

## Migration safety

The branding migration is idempotent and only replaces blank or known historical product values such as:

- `VetEdge`
- `Veterinary`
- `ProcessEdge Veterinary`

Unrelated customer-defined Website Settings values are preserved.

Submitted accounting documents, clinical data, permissions, role names, DocType names, and business workflows are not changed by branding migration.

## Do not rename

Do not mass-rename these as part of branding work:

- `vetedge` Python package
- GitHub repository
- Frappe app key
- route keys such as `/app/vetedge`
- Workspace Sidebar record key `VetEdge`
- technical API paths
- patch module paths
- existing role names
- DocType internal names

Any future technical rename must be planned as a separate migration project.
