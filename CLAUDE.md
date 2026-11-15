# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Frappe/ERPNext v16 app for Roti Ropi. It replaces three older apps:
`intercompany_sync` (Update Items pricing only), `item_group_series` and
`stock_entry_series`. The parent project rules (Docker stacks, data safety,
conventions) are in `/Users/rotiropi/ERPNext-Project/CLAUDE.md`.

## Commands

Run from the app root. The bench venv (`../../env/bin/python`) is a symlink to a
container path and does not work on the host; use the host `python3` (3.14).

```bash
python3 -m unittest discover -s erpnext_addons/tests -t .          # all Python unit tests
python3 -m unittest erpnext_addons.tests.test_migration            # one module
python3 -m unittest erpnext_addons.tests.test_naming_series.<Class>.<test>  # one test
node --test erpnext_addons/tests/*.test.js                          # JS tests (node:test)
ruff check .                                                        # lint (line-length 110, tabs)
```

On the host the integration test classes skip (no site). They run under a real
site with `bench --site <site> run-tests --app erpnext_addons`.

## Testing pattern

- `tests/fakes.py` provides `FakeFrappe` and `ensure_frappe_importable()`. Unit
  tests patch the module-level `frappe` of the code under test with `FakeFrappe`,
  so they never touch a real database even under bench.
- Integration classes use `frappe.tests.IntegrationTestCase` and skip when
  `frappe.local.site` is unset.
- JS tests load `public/js/*.js` into a `vm` context with a minimal `frappe`
  stub and capture the `frappe.ui.form.on` handlers.

## Architecture

- **Naming series on insert** (`overrides/item.py`, `stock_entry.py`,
  `material_request.py`, wired via `doc_events` `before_insert` in `hooks.py`).
  Each picks a target series (Item Group / Stock Entry Type
  `custom_naming_series`, or the `Naming Series Map` DocType for Material
  Request, then a code fallback) and only overwrites `naming_series` when it is
  still a framework default. An explicitly chosen series is respected. The
  `public/js/*_form.js` files mirror this on the desk form.
- **Update Items pricing** (`public/js/order_update_pricing.js`, Sales Order and
  Purchase Order): editable UOM, native price lookup and manual-rate guards in
  the native Update Items dialog. JS only.
- **Seeds and ownership takeover** (`migration.py`). `after_sync` (covers
  `install-app`, which does not migrate) and `after_migrate` both run the
  `patches/v1_0` seeds, then `ensure_naming_series_map` last. Seeds only fill
  empty values, never overwrite admin configuration. These helpers never commit;
  install/migrate owns the transaction. `patches.txt` is intentionally empty.
- **`Naming Series Map` ownership.** The DocType originally belonged to
  `stock_entry_series`. Frappe uninstall deletes every DocType whose module
  belongs to the removed app, so ownership is moved in place by setting
  `DocType.module` and `Module Def.app_name` with `frappe.db.set_value` (not
  `DocType.save`, which would export JSON in developer mode).
  - Never uninstall `stock_entry_series` before the ownership gate passes
    (`assert_naming_series_map_owner`).
  - Never uninstall this app without running
    `erpnext_addons.migration.hand_back_naming_series_map` first. Cutover
    runbook: `docs/runbook/erpnext-addons-cutover.md` in the project repo.
- **Intercompany Progress** (`intercompany/`). `progress.compute` is a pure
  calculator (net stock qty per item, plus SI/PI `net_amount`). `chain.py` walks
  native links (BFS, no hub document) from any member and writes the same values
  to all members. `events.py`: `on_change`/`before_cancel` only collect documents;
  a `short` job enqueued `after_commit` recomputes under a site `filelock`, so
  progress code never runs inside a submit/cancel transaction. `guard` reverts
  manual edits. Fields are created in code (`setup.ensure_fields`), not fixtures.
  Backfill: patch on migrate, `after_sync` on fresh install (install marks patches
  done). `patches.txt` must keep both `[pre_model_sync]` and `[post_model_sync]`
  sections or migrate fails.
- **List Settings** (`public/js/list_settings_columns.js`, `app_include_js`):
  Frappe 16.52 list layouts override column order; the wrapper makes saved
  List View Settings win.
- **Fixtures**: only the two `custom_naming_series` Custom Fields listed in
  `hooks.py` `fixtures`.
