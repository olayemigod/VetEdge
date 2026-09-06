# Dispensary and Stock Operations

## Module Purpose

Issue the correct treatment stock by warehouse and Batch, protect expiry controls and complete traceable ERPNext stock movement without changing clinical instructions.

## Treatment Issue Procedure

1. Open the assigned Treatment Item, consultation or Hospitalisation stock activity.
2. Confirm patient, source clinical record, Item, prescribed quantity, Service Branch and issuing Warehouse.
3. Check available quantity and the supported Batch selection.
4. Apply FEFO: issue the earliest valid expiry first, subject to quality and storage conditions.
5. Block expired, quarantined, recalled, damaged or otherwise unusable Batch stock.
6. Record the authorised stock activity and confirm the resulting Stock Entry or stock ledger effect.
7. Return to the clinical source and verify the dispensary or stock status.

## Warehouse and Count Control

- Use Stock Entry with Purpose `Material Transfer` for warehouse-to-warehouse movement.
- Confirm source, target, Item, quantity and Batch before submission.
- Use Stock Reconciliation only after a physical count, variance investigation and approval.
- Monitor Stock Balance, Stock Ledger, Batch-Wise Balance, Stock Ageing, Stock Projected Quantity and Stock Expiry Monitor.

## Expiry Response

1. Open Stock Expiry Monitor and set Warehouse, Item Group, expiry window and threshold filters.
2. Review Expired, Expiring Soon, affected quantity and affected Warehouses.
3. Open the Item, Batch or Warehouse from the actionable row.
4. Choose the approved FEFO issue, transfer, supplier return, quarantine, disposal or write-off route.
5. Post the authorised ERPNext stock transaction and verify the row no longer represents available saleable stock.

## Practice Exercise

Issue a synthetic treatment Item using the correct unexpired Batch, demonstrate a blocked expired Batch, and reconcile the result to Stock Ledger and the VetEdge source status.

## Related Screenshots

![Stock Expiry Monitor](training_assets/screenshots/stock-expiry-monitor.png)
