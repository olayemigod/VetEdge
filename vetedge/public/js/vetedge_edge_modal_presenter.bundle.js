import { h } from "vue";

export function modalPresenterReady() {
	return Boolean(h && (window.EdgeSuiteUI || window.EdgeUI)?.components?.EdgeModal);
}

if (typeof window !== "undefined") {
	window.VetEdgeEdgeModalPresenter = { ready: modalPresenterReady };
}
