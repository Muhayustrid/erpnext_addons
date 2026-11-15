# ERPNext Add-ons

General ERPNext v16 enhancements for Roti Ropi. Replaces `intercompany_sync`
(Update Items pricing only), `item_group_series` and `stock_entry_series`.

## Features
- **Update Items (Sales Order / Purchase Order)**: editable UOM, native price
  lookup and manual-rate guards in the native Update Items dialog.
- **Item naming series per Item Group** (`Item Group.custom_naming_series`).
- **Stock Entry naming series per Stock Entry Type** (`Stock Entry Type.custom_naming_series`).
- **Material Request naming series per type** via the `Naming Series Map` DocType.
- **Intercompany Progress** on PO, SO, DN, PR, SI and PI (returns included): five
  system-only checkboxes (`Ordered`, `Delivered`, `Received`, `Sales Invoiced`,
  `Purchase Invoiced`) and a `Next Step` list column, the same for every document
  in a chain. Native statuses are untouched.
- **List Settings column order** always wins over Frappe list layout columns.

Seeds only fill empty values; admin configuration is never overwritten.

## Migrating from the old apps
`Naming Series Map` is taken over in place: `after_sync`/`after_migrate` move
the DocType to module `ERPNext Add-ons`. Follow
`docs/runbook/erpnext-addons-cutover.md` in the project repo; never uninstall
`stock_entry_series` before the ownership gate passes, and never uninstall
this app without `erpnext_addons.migration.hand_back_naming_series_map` first.

## License
MIT
