# VetEdge → CoreEdge V2.4 Context Normalizer

VetEdge continues to use ERPNext Branch as its operational branch identity. No second VetEdge Branch master is introduced.

`vetedge.services.coreedge_context_reconciliation.get_context_reconciliation_rows()` discovers Branches already referenced by VetEdge configuration, access assignments or workflows. An operator can also provide an explicit Branch list.

Because ERPNext Branch is not inherently a Company binding in this deployment model, the normalizer derives Company only from existing accounting/stock evidence:

- Branch Cost Center / VetEdge Cost Center → Cost Center Company;
- Branch Warehouse / VetEdge Dispensary Warehouse → Warehouse Company.

If those sources disagree, or no Company can be derived, the row includes `normalization_issue` and leaves Company unresolved. CoreEdge V2.4B must treat that condition as Conflict rather than proposing a mapping.

The helper is read-only. It does not:

- create a new Branch model;
- modify Branch → Cost Center or Warehouse mappings;
- alter Branch User or Practitioner Assignments;
- change clinical access;
- create CoreEdge bindings;
- switch active context;
- touch ERPNext accounting documents.

This preserves the VetEdge rule that Branch is operational and Cost Center/accounting configuration remains the financial boundary.
