import VetedgeStockExpiryMonitor from './vetedge_stock_expiry_monitor/VetedgeStockExpiryMonitor.vue';

function getEdgeSuiteRuntime() {
  const runtime = window.EdgeSuiteUI || window.EdgeUI;
  if (!runtime?.createEdgeApp || !runtime?.components) {
    throw new Error('EdgeSuite UI runtime is not available.');
  }
  return runtime;
}

export function mountVetedgeStockExpiryMonitor(target) {
  if (!target) {
    throw new Error('A mount target is required for the Stock Expiry Monitor.');
  }

  const runtime = getEdgeSuiteRuntime();

  // Override the temporary app-local compatibility registry so the migrated page
  // renders exclusively with components supplied by the standalone EdgeSuite UI app.
  VetedgeStockExpiryMonitor.components = runtime.components;

  const app = runtime.createEdgeApp(VetedgeStockExpiryMonitor);
  app.mount(target);
  return app;
}

if (typeof window !== 'undefined') {
  window.VetedgeStockExpiryMonitor = VetedgeStockExpiryMonitor;
  window.mountVetedgeStockExpiryMonitor = mountVetedgeStockExpiryMonitor;
}

export default VetedgeStockExpiryMonitor;
