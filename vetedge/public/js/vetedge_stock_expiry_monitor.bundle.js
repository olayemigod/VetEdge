import { createApp } from 'vue';
import VetedgeStockExpiryMonitor from './vetedge_stock_expiry_monitor/VetedgeStockExpiryMonitor.vue';

export function mountVetedgeStockExpiryMonitor(target) {
  const app = createApp(VetedgeStockExpiryMonitor);
  const edgeUI = window.EdgeUI || {};
  const components = edgeUI.components || edgeUI;

  Object.entries(components).forEach(([name, component]) => {
    if (name.startsWith('Edge') && component) {
      app.component(name, component);
    }
  });

  app.mount(target);
  return app;
}

if (typeof window !== 'undefined') {
  window.VetedgeStockExpiryMonitor = VetedgeStockExpiryMonitor;
  window.mountVetedgeStockExpiryMonitor = mountVetedgeStockExpiryMonitor;
}

export default VetedgeStockExpiryMonitor;
