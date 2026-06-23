# VetEdge White-Label Naming Inventory

This document inventories all occurrences of branding and product keywords in the VetEdge codebase, classifying them to guide future white-label renaming efforts.

## Keyword Occurrence & Classification Summary

### 1. `VetEdge` (Found in 153 files)
- **Classifications**:
  - **Internal technical reference**: Python imports, namespace strings, and mock test classes (e.g. `get_vetedge_product_app()`, `class TestVetEdgeBranding`). **[Keep]**
  - **User-facing labels / Title strings**: App name in settings, UI footers, and text headers (e.g. `app_title = "VetEdge"` in `hooks.py`, `Welcome to VetEdge` in footers). **[Change later]**
  - **DocType names**: DocTypes containing the prefix `vetedge_` (e.g. `vetedge_license_profile`). **[Rename later]**
  - **Notification/email/print/dialog strings**: Email templates and notification logs (e.g. `fixtures/vetedge_email_templates.json` containing `VetEdge Account Activation`). **[Change later]**
  - **Platform/operator-only reference**: site_config keys (e.g. `vetedge_white_label_enabled`). **[Keep or hide]**

### 2. `VETEDGE` (Found in 2 files)
- **Classifications**:
  - **Internal technical reference**: Upper-case replacement matches in `replace_brand_tokens`. **[Keep]**
  - **User-facing labels**: Hardcoded capitalized strings in tests and templates. **[Change later]**

### 3. `vetedge` (Found in 223 files)
- **Classifications**:
  - **Internal technical reference**: Folder names, module imports, relative paths, app name configs, database field references (e.g. `app_name = "vetedge"`, `import vetedge.services`). **[Keep]**
  - **User-facing labels**: Minor occurrences in default URLs (e.g. `/vetedge_guest_booking`). **[Change later]**

### 4. `EdgeSuite` (Found in 0 files)
- **Classifications**:
  - None found. No actions needed.

### 5. `CoreEdge` (Found in 10 files)
- **Classifications**:
  - **Internal technical reference / Platform-only**: Checks for platform modes, imports from the coreedge package, and integration adapter tests (e.g. `coreedge_adapter.py`, `is_coreedge_available()`). **[Keep]**

### 6. `SaaS` (Found in 4 files)
- **Classifications**:
  - **Internal technical reference / Platform-only**: References inside license profile validation and API simulation tests (e.g. `vetedge_license_profile.json`). **[Keep]**

---

## DocTypes with `vetedge_` / `VetEdge` prefix
These are the DocTypes defined in the module that start with `vetedge_` (which translates to `VetEdge` in the Desk):
- `vetedge_license_profile` (VetEdge License Profile)
- `vetedge_notification_log` (VetEdge Notification Log)
- `vetedge_notification_preference` (VetEdge Notification Preference)
- `vetedge_role_bundle` (VetEdge Role Bundle)
- `vetedge_role_bundle_role` (VetEdge Role Bundle Role)

*Note: These DocTypes must NOT be renamed in this phase.*

---

## Expected M&G Profile Values (Documented Only - Do Not Hardcode)
For the M&G client site, the following branding settings are expected to be configured in the `CoreEdge Tenant Branding Profile` record on their site:

- **tenant_site**: `mg-vet.erpnext.com` (or current site name on Frappe Cloud)
- **product_app**: `vetedge`
- **enable_white_label**: `1` (True)
- **brand_name**: `M & G Vet Home`
- **company_name**: `Mercy and Grace Vet Home`
- **short_name**: `M&G Vet`
- **module_label**: `Veterinary`
- **app_title**: `M & G Vet Home`
- **hide_source_product_name**: `1` (True)
- **branding_locked**: `1` (True)
- **managed_by_platform**: `1` (True)
- **status**: `Active`
