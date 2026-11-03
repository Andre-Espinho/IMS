# IMS: Inventory Management System

IMS is a desktop app for keeping track of stock: items, where they are stored, how many there are, and a full history of every change. It runs on one Windows PC as an Electron window, with a Python backend and a local database. It can import the inventory workbook (`Inventário.xlsx`) from a file or from SharePoint.

The interface is available in Portuguese (PT-PT, the default) and English (EN-UK).

> Status: the local app is working. The SharePoint export and the mobile inbox are not built yet. See [Roadmap](#roadmap).

## Features

- **Items:** search by description, reference, EAN, brand or id; filter by stock and rack; sort by any column; create, edit, deactivate (soft delete) and reactivate.
- **Stock movements:** entries, exits, transfers between locations, counts (adjustments) and verifications. Every change is recorded in an append-only history.
- **Voiding:** a movement can be undone with a reversing movement. The original stays in the history.
- **Locations:** racks (estante) and shelves (prateleira), plus "Sem localização" for items without one. A location's text can be edited directly.
- **Import:** analyse a workbook first (rows, new and updated items, issues to review), then confirm. Re-importing only records stock differences.
- **SharePoint:** sign in with your own work account (device-code sign-in), choose the workbook link, and import it the same way. Sign-out is available.
- **Delete local data:** a guarded action (typed confirmation) that clears all inventory data on the PC before a fresh import. The SharePoint file and sign-in are kept.
- **Light and dark themes**, remembered between launches.

## Requirements

- Windows 10 or 11
- [Node.js LTS](https://nodejs.org/) (for the frontend and Electron)
- Python 3.12 or newer

## Setup

Run these once, from the repository root.

**1. Backend (Python)**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**2. Frontend (Node / Electron)**

```powershell
cd frontend
npm install
```

The Electron app starts the backend from `backend\.venv`. To use a different Python, set `IMS_PYTHON` to the full path of its `python.exe`.

## Running

```powershell
cd frontend
npm run electron:dev
```

This starts the Vite dev server, waits for it, opens the Electron window, and starts the backend on `127.0.0.1:8000`. Closing the window stops the backend.

If the page shows "A aguardar o servidor local…" (Waiting for the local server…) for more than a few seconds, the backend failed to start. The app shows a dialog with the backend's last output.

## Importing the inventory

1. Open **Importação** (Import).
2. Choose **Ficheiro local** (local file) and select the workbook, or **SharePoint**.
3. Click **Analisar** (Analyse) and review the report.
4. Click **Importar** (Import) to confirm.

For a fresh start, use **Apagar dados locais** (Delete local data) at the bottom of the screen first. It asks you to type `APAGAR` (or `DELETE` in English).

### SharePoint sign-in

1. In **Importação**, choose **SharePoint** and click **Iniciar sessão no SharePoint**.
2. Open the link shown, enter the code, and sign in with your work account.
3. Approve the consent prompt. It shows *Microsoft Graph Command Line Tools*, the Microsoft client IMS uses for sign-in.

Some tenants require an administrator to approve this client. If you see "Sem permissão" (no permission), use the **Procedimento alternativo** shown on the screen: sync the SharePoint library with OneDrive and import from the synced folder with **Ficheiro local**.

## Data and configuration

Everything local is stored in `data/`, which is git-ignored:

| File | Contents |
|---|---|
| `data/ims.sqlite3` | The inventory database (source of truth) |
| `data/msal_cache.bin` | SharePoint sign-in tokens (removed by **Terminar sessão**) |
| `data/sharepoint.json` | Optional SharePoint settings: `client_id`, `tenant`, `share_url`. Saved from the UI. |

The workbook and business data are not stored in git. `Inventário.xlsx` is git-ignored.

## Tests

```powershell
cd backend
$env:PYTHONPATH = "."
.venv\Scripts\python.exe -m pytest -q tests
```

The tests use a temporary database and fake SharePoint responses; they don't contact Microsoft. The import tests that use the real workbook are skipped if `Inventário.xlsx` is not in the repository root.

To check the frontend builds:

```powershell
cd frontend
npm run build
```

## Project layout

```
backend/
  ims/
    models.py        database tables (items, locations, stock, movements)
    services.py      movement rules (in, out, transfer, adjust, verify, void)
    importer.py      workbook analysis and import
    sharepoint.py    device-code sign-in and file download (Microsoft Graph)
    api.py           HTTP API used by the UI
    db.py, main.py   database setup and the FastAPI app
  tests/             backend tests
frontend/
  electron/main.cjs  starts the backend and opens the window
  src/               React UI (App.tsx, components/, i18n.tsx, api.ts)
docs/SPEC.md         design specification and decision log
```

## Roadmap

- **SharePoint export:** write the updated workbook back to the SharePoint library, with a check that nobody edited it there in the meantime.
- **Mobile inbox:** a SharePoint List that phones write to; the app applies the entries and writes back the result.
- **Migrations:** move from the small in-place upgrades to Alembic.
- **Packaging:** bundle the backend into the Electron installer so the app runs without a Python install.

See [docs/SPEC.md](docs/SPEC.md) for the full design and the decisions behind it.
