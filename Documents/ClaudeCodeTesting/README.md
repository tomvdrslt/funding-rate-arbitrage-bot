# OrcaSlicer Profile Sync

Bidirectional sync of OrcaSlicer printer/filament/process profiles across machines using Google Drive.

## Setup

### 1. Google Cloud Console

1. Go to https://console.cloud.google.com/
2. Create a new project (or select an existing one).
3. Enable the **Google Drive API** under *APIs & Services > Library*.
4. Go to *APIs & Services > Credentials* and click **Create Credentials > OAuth client ID**.
   - Application type: **Desktop app**
5. Download the JSON and save it as `orca_sync/credentials.json`.

### 2. Install dependencies

```
pip install -r requirements.txt
```

### 3. Run

Double-click `run.bat`, or from the project root:

```
python orca_sync/main.py
```

The first run opens a browser for OAuth consent. Approve access and the token is cached in `orca_sync/token.json` for subsequent runs.

## How it works

- A **file watcher** monitors all OrcaSlicer profile directories and uploads changed files to `OrcaSlicerSync/` in your Google Drive within ~1 second.
- A **Drive poller** checks for remote changes every 5 seconds and downloads any files newer than the local copy.
- **Conflict resolution**: last-write-wins (Drive `modifiedTime` vs local `mtime`).
- The **system tray icon** shows sync status (green = synced, yellow = syncing, red = error). Right-click for Sync Now, Open Log, and Quit.

## Directories synced

| Local path | Drive folder |
|---|---|
| `%APPDATA%\OrcaSlicer\system\Custom\filament\` | `OrcaSlicerSync\filament\` |
| `%APPDATA%\OrcaSlicer\system\Custom\machine\` | `OrcaSlicerSync\machine\` |
| `%APPDATA%\OrcaSlicer\system\Custom\process\` | `OrcaSlicerSync\process\` |
| `%APPDATA%\OrcaSlicer\user\default\filament\` | `OrcaSlicerSync\filament\` |
| `%APPDATA%\OrcaSlicer\user\default\machine\` | `OrcaSlicerSync\machine\` |
| `%APPDATA%\OrcaSlicer\user\default\process\` | `OrcaSlicerSync\process\` |

## Log file

`orca_sync/orca_sync.log` — accessible from the tray icon menu.
