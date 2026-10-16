# NetPilot Settings Page — UI and Operations Preferences v1

An incremental patch for the **existing NetPilot Cloud Event Explorer v2 / Operations Console**. Adds a real `Settings` navigation item and connects it to behavior in the React application. The package is **frontend-only**: no Docker, FastAPI, AWS, NetPilot agent, IAM, Lambda, or DynamoDB changes.

## Includes

- Appearance: graphite/midnight themes, teal/blue/amber accents, information density, text scaling.
- Refresh: network status polling (manual/5/10/30s), incidents and process logs (manual/8/15/30s), cloud service status (manual/60/120s), cloud events (manual/30/60/120s), live SSE stream on/off.
- In-app alerts: new incident and incident-resolved notifications while the live event stream is enabled. **No system/browser push notifications.**
- Time format: local/UTC, 12/24 hour display in top bar and formatted event/incident dates.
- First page on launch; preference export/import (JSON); reset to defaults.
- Control access: show local backend connection, token loaded state, `LOCK CONTROLS` (clears the token from React memory), and reopen `UNLOCK CONTROLS` dialog. Safeguards and destructive-action confirmations remain mandatory.

## Prerequisites

The `A:\NetPilot\dashboard` app from **NetPilot Cloud Event Explorer v2** is installed, including `src/pages/CloudEvents.jsx`, and the FastAPI backend is already working. No additional React packages are required. Python and Docker are NOT needed merely to test visual preferences while the UI is open, but live data needs the running backend and corresponding services.

## Installation (PowerShell)

1. Stop the React Vite development server with `Ctrl+C`. **You do not need to stop Docker or AWS services.**
2. Save `NetPilot_Settings_Page_v1.zip` inside `A:\NetPilot`.
3. Back up the files this patch will replace:

```powershell
cd A:\NetPilot
New-Item -ItemType Directory -Force .\backups\pre-settings
Copy-Item .\dashboard\src\App.jsx .\backups\pre-settings\App.jsx
Copy-Item .\dashboard\src\components\Chrome.jsx .\backups\pre-settings\Chrome.jsx
Copy-Item .\dashboard\src\pages\CloudEvents.jsx .\backups\pre-settings\CloudEvents.jsx
Copy-Item .\dashboard\src\lib\format.js .\backups\pre-settings\format.js
```

4. Extract the patch at the **project root**:

```powershell
Expand-Archive -Path .\NetPilot_Settings_Page_v1.zip -DestinationPath . -Force
```

5. Run the standalone settings unit tests and build:

```powershell
cd A:\NetPilot\dashboard
node --test tests\settings.test.mjs
npm run build
npm run dev
```

If `npm run build` fails, share the full error; don't overwrite backend files to fix a frontend build issue.

6. Open `http://127.0.0.1:5173/`, choose **Settings** in the sidebar, modify appearance or refresh preferences, navigate away and back, and reload to verify persistence. Existing token is intentionally cleared by a reload; unlock controls again using your current backend token. Test the **LOCK CONTROLS** action (it changes UI authorization only; it does NOT stop processes).

## Precautions

- Browser localStorage contains **only allow-listed UI preferences**. Never put `NETPILOT_CONTROL_TOKEN` or AWS keys in localStorage or React/Vite environment variables.
- Turning **off the live event stream** only disables the browser SSE connection. It does NOT stop the v4 network monitoring engine or the AWS Forwarder.
- Turning polling **off** does not stop backend services; use the top-bar refresh button for a manual fetch. Cloud Events also has its own per-page auto-refresh toggle, initialized from Settings.
- In-app alerts are displayed only for newly received SSE events. There are no email, push or sound alerts in this patch.
- AWS polling reads can incur AWS charges; the default AWS Operations auto-poll is **off**.
- Mandatory confirmation dialogs and FastAPI header authentication are unchanged and cannot be disabled by UI settings.
- Settings are per browser profile/device, not shared across accounts or AWS.
- **Frontend build** was not verified in the packaging environment because package download timed out. JS/JSX passed TypeScript parser-based syntax checks, and the self-contained native Node tests passed. Run `npm run build` locally before using the patch.

## Files changed

```
dashboard/src/App.jsx                        (replace)
dashboard/src/components/Chrome.jsx          (replace)
dashboard/src/lib/format.js                  (replace)
dashboard/src/lib/settings.js                (new)
dashboard/src/pages/CloudEvents.jsx          (replace)
dashboard/src/pages/Settings.jsx             (new)
dashboard/src/pages/settings.css             (new)
dashboard/tests/settings.test.mjs            (new)
README_SETTINGS_UPGRADE.md                   (new)
```

No backend file or `dashboard/src/style.css` is overwritten.
