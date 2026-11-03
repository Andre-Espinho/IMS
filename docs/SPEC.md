# IMS: Inventory Management System — Specification v0.1

Status: draft for approval.
Written for: the owner (decisions and approval) and whoever implements it.

## 1. Scope

- One local operator uses a browser UI on a Windows PC. The UI runs on `127.0.0.1` only.
- The local database is the **source of truth**.
- A `.xlsx` copy of the inventory lives in a SharePoint document library. People read it; nobody edits it. The app overwrites it.
- Other people submit simple movements from a mobile app into a **SharePoint List (inbox)**. The local app pulls them in and applies them to the database. They then appear in the local UI and in the next `.xlsx` export.

Out of scope for v1: allocations/reservations (the `QTD_ALOCADA` field is removed), multiple simultaneous local users, Azure hosting, per-serial-number tracking.

## 2. Decisions

| Topic | Decision |
|---|---|
| Source of truth | Local SQLite database |
| Outbound to SharePoint | `.xlsx` in a document library, overwritten by the app (Microsoft Graph) |
| Inbound from mobile | SharePoint List `Movimentos` (inbox). Mobile never writes to the `.xlsx`. |
| Allocation | Removed. Not in the model or the export. |
| Hosting | Local Windows PC, Python 3.12 |
| Users | 1 local operator (UI). Remote users only submit via mobile. |
| Auth to Graph | App-only (client credentials), `Sites.Selected` scoped to one site |

Note on the inbox: the original plan had only an `.xlsx` target. Mobile submissions can't be written safely into a shared workbook, so they go to a List and the `.xlsx` stays an export. This needs your approval.

## 3. Architecture

```
 Mobile app ──► SharePoint List "Movimentos" ◄──poll──┐
                        ▲ status written back         │
                                                      │
 Browser (127.0.0.1) ──► FastAPI ──► SQLite (truth) ──┤ Sync worker
                         + React UI                   │  - export (debounced + nightly)
                                                      │  - inbox poll (every 5 min)
                                                      └──► SharePoint .xlsx (PUT, If-Match eTag)
```

Components:
- **API / server**: FastAPI, SQLAlchemy, Alembic migrations.
- **UI**: React + Vite SPA, served by FastAPI.
- **Sync worker**: runs inside the app process (APScheduler).
- **Graph client**: MSAL confidential client, client credentials flow.
- **Excel**: `openpyxl` for import and export.

## 4. Data model

All tables use integer or UUID primary keys and UTC timestamps.

**item**
- `id` (int, primary key) — legacy `id` from the workbook (349…), kept so the export matches.
- `description`, `brand`, `reference` (not unique), `ean` (optional), `notes`
- `verified_at` (nullable) — set by a VERIFY movement
- `active` (bool), `created_at`, `updated_at`

**location**
- `id`, `estante` (int, nullable), `prateleira` (text, nullable: `2`, `3`, `4`, `Topo`)
- unique (`estante`, `prateleira`)
- Label is derived, e.g. `E5-P4`, `E3-Topo`. Special row `id=0`, label `Sem localização`, for items with no location.

**stock**
- `item_id`, `location_id`, `qty` (integer ≥ 0)
- primary key (`item_id`, `location_id`)

**movement** (append-only)
- `id` (UUID), `created_at`, `type` ∈ {`IN`, `OUT`, `MOVE`, `ADJUST`, `VERIFY`, `IMPORT`}
- `item_id`, `from_location_id` (nullable), `to_location_id` (nullable), `qty`
- `reason` (text), `operator` (text), `source` ∈ {`local`, `mobile`, `import`}
- `external_ref` (unique, nullable) — SharePoint List item id for mobile movements; provides idempotency

**inbox_state**
- `external_ref` (primary key), `status` ∈ {`applied`, `rejected`}, `message`, `processed_at`

**sync_run**
- `id`, `kind` ∈ {`export`, `poll`, `import`}, `started_at`, `finished_at`, `status`, `detail`

## 5. Movement rules

Every movement runs in one database transaction. Corrections are new movements; nothing is edited or deleted.

| Type | Meaning | Rule |
|---|---|---|
| IN | Add qty to a location | qty > 0; location defaults to `Sem localização` if not given |
| OUT | Remove qty from a location | qty > 0; stock at that location ≥ qty, otherwise rejected |
| MOVE | Transfer qty between locations | qty > 0; source stock ≥ qty |
| ADJUST | Set the counted qty at a location | qty ≥ 0; stores the delta as the movement qty |
| VERIFY | Mark the item as checked | no quantity change; sets `item.verified_at` |
| IMPORT | Initial/baseline load from the workbook | source = `import` |

Mobile movement rules:
- Each List item becomes a movement with `external_ref` = List item id. Re-processing is a no-op.
- The item is matched by `id` first, then by `reference` if unambiguous. Ambiguous or unknown → rejected with a message.
- Mobile can add quantities to existing items only. Creating new items stays local (see open questions).

## 6. SharePoint integration

### 6.1 Outbound: `.xlsx` export
- Generated with `openpyxl`. Sheet name `INVENTARIO yyyymmdd-HHMMSS`.
- Columns, in order: `DESCRICAO, MARCA, REFERENCIA, id, QTD_STOCK, PRATELEIRA, ESTANTE, S_N, EAN, Verificado`.
  - `QTD_ALOCADA` is dropped.
  - `Verificado` is the date from `item.verified_at`, or blank. (The older sheet had an `x` flag; the date replaces it.)
  - One row per item-location. Items with stock in several locations repeat `id`; today every item has at most one location, so this has no effect yet.
- Upload: `PUT /drives/{drive-id}/items/{item-id}/content` with `If-Match: <eTag>` from the last export.
  - If the eTag no longer matches (someone edited the file in SharePoint), the app does **not** overwrite. It logs an error and shows it in the UI.
- Triggers: 60 s after the last committed change (debounced), a nightly full export, and a manual "sincronizar agora" button.
- Each export is also saved locally under `exports/` (git-ignored).

### 6.2 Inbound: mobile inbox
- Poll the List every 5 minutes (configurable). Process new items in creation order.
- Expected List columns: `Title` (reference or id), `Tipo` (Entrada / Saída / Mover / Verificar), `Quantidade`, `Destino` (`E5-P4`-style label), `Operador`, `Notas`.
- Each result is written back to the List items in `Estado` (Aplicado / Rejeitado) and `Mensagem`, so the mobile user sees the outcome.
- Requires write access to the List, granted in the same `Sites.Selected` approval.

### 6.3 Failure behaviour
- Graph unreachable: outbound retries with backoff, UI shows "pendente"; the local database is unaffected.
- Inbox errors: the individual item is rejected with a message. Other items still process.

## 7. Initial import

- `POST /api/import/xlsx`: upload a workbook and choose a sheet.
- **Dry run first**: shows counts, duplicate references, items without location, and the 21 items where allocated > stock (informational only; the field is dropped).
- **Commit**: writes items, locations, and stock, plus one `IMPORT` movement per item.
- Re-running an import is idempotent by `id`: it updates attributes and adds only the stock delta as an `ADJUST`.
- Acceptance: the commit creates 828 items (from the 2026-10-28 sheet), and the report lists every issue found.

## 8. Local UI

Labels in the UI follow the decision on language (see open questions).

1. **Itens**: table with search (description, reference, EAN, brand), filters (brand, estante, prateleira, zero stock), sorting, pagination.
2. **Item**: stock by location, movement history, actions (Entrada, Saída, Mover, Ajustar, Verificar), edit attributes.
3. **Movimentos**: full log, filters by type and source (local / mobile / import).
4. **Caixa de entrada**: mobile submissions with status and reason; retry for rejected items.
5. **Sincronização**: last export, last poll, errors, manual sync button.
6. **Importação**: upload, dry-run report, commit.

## 9. Security and configuration

- **Entra ID app registration**: client credentials, `Sites.Selected` granted to one site, write access to the `Movimentos` List and the library folder.
- **Secret**: stored in Windows Credential Manager or a local `.env` that is git-ignored. Never in the repo or in the UI.
- **Binding**: UI and API listen on `127.0.0.1` only.
- **Backups**: the SQLite file is copied daily (Task Scheduler) to a second location. The `.xlsx` in SharePoint is also a recent copy of current state.
- **Audit**: the movement table is the audit trail. Every row records operator and source.

## 10. Repository layout

```
backend/        FastAPI app, models, services (movements, sync, graph, excel), tests
frontend/       React + Vite SPA
docs/SPEC.md    this file
data/           SQLite database            (git-ignored)
exports/        local copies of exports    (git-ignored)
Inventário.xlsx source workbook            (git-ignored; business data stays out of git)
```

## 11. Phases and acceptance

| Phase | Work | Done when |
|---|---|---|
| P1 Foundations | Repo, schema, migrations, test setup, local server + empty UI | Migrations run; tests run; UI loads on localhost |
| P2 Import | Dry run and commit from the workbook | 828 items imported; report lists all issues |
| P3 Local movements + UI | Movement rules, item screens, log | Every rule in §5 has a test; UI actions update stock |
| P4 Export | `.xlsx` generation and SharePoint upload with eTag check | File in the library matches the database; a manual edit in SharePoint blocks overwrite and shows an error |
| P5 Mobile inbox | Poll, apply, write back status | A test List item shows "Aplicado" and appears in the UI; re-poll does not duplicate it |
| P6 Hardening | Backups, runbook, error reporting | Restore from backup tested once |

Progress:
- **P1 done** (backend only). Models, DB setup, `/api/health`; 7 tests. Deviations: schema is created with `create_all`, and Alembic is not added yet (planned before P6). The frontend is not started because Node.js is not installed.
- **P2 done** (importer service). Dry run and commit by header name; `QTD_ALOCADA` ignored; re-runs record only stock differences. Tests use the real workbook: 828 items imported. Dry run reports 2 repeated references (`27230171`, `30118303`) and 484 items without location. The HTTP endpoint for import is not added yet.
- **P3 done**. Movement rules (IN, OUT, MOVE, ADJUST, VERIFY) in `backend/ims/services.py`, one transaction per movement. API in `backend/ims/api.py`: items list and detail, item edits, movements, locations, and import dry-run/commit (upload). 37 backend tests passing. Each §5 rule has a test.
- **Local UI (phase 3 screens) built**: Itens (search, stock and shelf filters), item detail (edit, stock by location, movement form, history, verify), Movimentos (filters), Importação (analyse then import). Frontend type-checks and builds; not yet exercised in the Electron window.
- **Not yet built**: item creation from the local UI (not in the spec; add when wanted), mobile inbox (P5, deferred), SharePoint export (P4, waiting on site/library details), Alembic migrations (planned before P6).

## 12. Decisions log and open items

Resolved:
- **UI language**: Portuguese.
- **Items without location**: kept under `Sem localização`.
- **Mobile creating new items**: not in v1.
- **Poll interval**: 5 minutes (applies once the mobile inbox is built).
- **Mobile phase**: deferred until the local UI is finished. The form tool (Power Apps vs Microsoft Forms) is decided then. §6.2 and P5 are on hold until then.
- **SharePoint host**: tenant `bridgepointeng.sharepoint.com`. The `.xlsx` will be created as a new document there.

Open (needed before P4, the SharePoint export):
1. **Site path and library**: the exact site URL (e.g. `https://bridgepointeng.sharepoint.com/sites/<name>`) and the document library where the `.xlsx` lives. The List is not needed until the mobile phase.
2. **Entra app registration**: someone with admin rights must create it and grant `Sites.Selected` for that site.
