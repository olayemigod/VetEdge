# EdgeSuite UI Stock Expiry Monitor migration

## Scope

The Stock Expiry Monitor is the first VetEdge page migrated from an app-local EdgeUI compatibility runtime to the standalone `edgesuite_ui` Frappe app.

VetEdge continues to own:

- the Stock Expiry Monitor Vue page
- stock-expiry APIs and permissions
- notifications and notification actions
- navigation and product identity
- the VetEdge product bundle

EdgeSuite UI now owns:

- the Vue application mounting runtime
- shared shell, layout, state, stat, status, filter, and notification components
- shared visual tokens and compatibility styles

CoreEdge is not required to build or render this page.

## Installation on an existing VetEdge bench

Run from the bench directory:

```bash
bench get-app https://github.com/olayemigod/processedge-edge-suite-ui.git --branch agent/edgeui-foundation
bench --site vetedge.local install-app edgesuite_ui
bench build --app edgesuite_ui --app vetedge
bench --site vetedge.local migrate
bench --site vetedge.local clear-cache
bench clear-website-cache
```

For a fresh site, install `edgesuite_ui` before `vetedge`. VetEdge declares it in `required_apps` so Frappe can enforce this dependency.

## Validation

```bash
bench --site vetedge.local list-apps
bench --site vetedge.local run-tests --app edgesuite_ui
bench --site vetedge.local run-tests --app vetedge --module vetedge.tests.test_vetedge_stock_expiry_monitor
```

Confirm that `edgesuite_ui` appears in `list-apps`, then open:

```text
/app/stock-expiry-monitor
```

Verify:

1. The page loads without an EdgeSuite UI failure message.
2. Filters refresh stock data.
3. Summary cards and the batch table render.
4. Pagination works.
5. The notification bell and drawer open and execute notification-only actions.
6. Browser network requests load `edgeui.bundle.js` before `vetedge_stock_expiry_monitor.bundle.js`.
7. The page still loads when central CoreEdge services are unreachable, provided VetEdge access policy permits the session.

## Rollback

Before the migration is merged, switch VetEdge back to the previous commit and rebuild:

```bash
git -C apps/vetedge checkout ae92c86fb296830dcc715ddf15dad0d97e1bd859
bench build --app vetedge
bench --site vetedge.local clear-cache
```

Do not uninstall `edgesuite_ui` while any migrated product page depends on it.
