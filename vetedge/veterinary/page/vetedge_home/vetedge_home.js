frappe.pages['vetedge-home'].on_page_load=function(wrapper){wrapper.page=frappe.ui.make_app_page({parent:wrapper,title:__('Veterinary Home'),single_column:true});};
frappe.pages['vetedge-home'].on_page_show=function(wrapper){
	const page=wrapper.page;wrapper.current_visit_id=(wrapper.current_visit_id||0)+1;const visitId=wrapper.current_visit_id;
	if(wrapper.vue_app){wrapper.vue_app.unmount();wrapper.vue_app=null;}$(page.body).empty();
	const $loading=$('<div class="p-6 text-center text-muted"></div>').text(__('Loading Veterinary Home...')).appendTo(page.body);
	const fail=(message)=>{$loading.remove();$('<div class="alert alert-danger p-6 text-center"></div>').text(message||__('Veterinary Home failed to load.')).appendTo(page.body);};
	frappe.require('edgeui.bundle.js',()=>{if(wrapper.current_visit_id!==visitId)return;const runtime=window.EdgeSuiteUI||window.EdgeUI;const required=['EdgeAppShell','EdgePageLayout','EdgePageHeader','EdgeBranchContextSwitcher','EdgeDashboardLayout','EdgeStatCard','EdgeStatusBadge','EdgeLoadingState','EdgeErrorState'];const missing=required.filter((name)=>!runtime?.components?.[name]);if(!runtime?.createEdgeApp||missing.length){fail(missing.length?__('Missing EdgeSuite UI components: {0}. Rebuild EdgeSuite UI 0.4.1 or newer.',[missing.join(', ')]):__('The standalone EdgeSuite UI runtime is unavailable.'));return;}
		frappe.require('vetedge_home.bundle.js',()=>{if(wrapper.current_visit_id!==visitId)return;if(!window.mountVetEdgeHome){fail(__('The Veterinary Home product bundle is unavailable.'));return;}try{$loading.remove();const root=$('<div class="vetedge-home-root" data-edge-product="vetedge"></div>').appendTo(page.body);wrapper.vue_app=window.mountVetEdgeHome(root[0]);}catch(error){console.error('Error mounting Veterinary Home:',error);fail(__('Error mounting Veterinary Home: {0}',[error.message||String(error)]));}});
	});
};
