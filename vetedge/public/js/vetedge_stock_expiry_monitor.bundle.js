import * as Vue from 'vue';
import VetedgeStockExpiryMonitor from './vetedge_stock_expiry_monitor/VetedgeStockExpiryMonitor.vue';

export function mountVetedgeStockExpiryMonitor(target) {
  if (typeof window === 'undefined') return null;

  if (!window.EdgeUI) {
    throw new Error("EdgeSuite UI runtime not loaded: window.EdgeUI is undefined");
  }
  if (!window.EdgeUI.createEdgeApp) {
    throw new Error("EdgeSuite UI runtime compatibility error: createEdgeApp is missing");
  }

  console.log("EdgeUI version:", window.EdgeUI.version);
  return window.EdgeUI.createEdgeApp(VetedgeStockExpiryMonitor, target);
}

if (typeof window !== 'undefined') {
  window.VetedgeStockExpiryMonitor = VetedgeStockExpiryMonitor;
  window.mountVetedgeStockExpiryMonitor = mountVetedgeStockExpiryMonitor;
}

export default VetedgeStockExpiryMonitor;
