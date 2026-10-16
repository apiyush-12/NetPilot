# NetPilot Console Themes — v2

A frontend-only patch for the **NetPilot Settings Page v1**. Adds four new non-Bento, utilitarian operations-console themes: Carbon Steel, Command Navy, Terminal Green, and Industrial Amber. Graphite (default) and Midnight are retained (six total). Existing teal/blue/amber accents, density, large text, refresh preferences, token handling, and safety confirmations remain available.

## Modified files (ONLY THESE)

- `dashboard/src/lib/settings.js` — allow-list new themes and apply their classes when settings load/save.
- `dashboard/src/pages/Settings.jsx` — add theme names and a compact preview strip.
- `dashboard/src/pages/themes.css` — **new** stylesheet containing theme palettes and previews.
- `dashboard/tests/settings.test.mjs` — adds two new tests; total eight.

**No changes to `App.jsx`, `style.css`, backend, Docker, AWS, or the controller.** The extra classes are applied by `saveSettings()` and `loadSettings()` so the patch does not overwrite your application integration.

## Install

1. Stop `npm run dev` with `Ctrl+C` (no need to stop Docker/AWS).
2. Save `NetPilot_Console_Themes_v2.zip` in `A:\NetPilot`.
3. Back up the three files that will be overwritten:

```powershell
cd A:\NetPilot
New-Item -ItemType Directory -Force .\backups\pre-themes
Copy-Item .\dashboard\src\lib\settings.js .\backups\pre-themes\settings.js
Copy-Item .\dashboard\src\pages\Settings.jsx .\backups\pre-themes\Settings.jsx
Copy-Item .\dashboard\tests\settings.test.mjs .\backups\pre-themes\settings.test.mjs
```

4. Extract the patch at the project root:

```powershell
Expand-Archive -Path .\NetPilot_Console_Themes_v2.zip -DestinationPath . -Force
```

5. Test and build:

```powershell
cd A:\NetPilot\dashboard
node --test tests\settings.test.mjs
npm run build
npm run dev
```

6. Open `http://127.0.0.1:5173/`, then **Settings > Appearance > Console theme**. Change theme, navigate away, reload and confirm it persists. If the browser is refreshed, control tokens must be re-entered by design.

## Where to add your own theme later

1. Add a new theme ID, e.g. `maritime`, to the `ALLOWED.theme` array in `dashboard/src/lib/settings.js`.
2. Add it to `EXTRA_CONSOLE_THEMES` in the same file, so its `np-maritime` class is toggled on the HTML root. (`dark` and `midnight` are handled by the existing `App.jsx`.)
3. Add `[ 'maritime', 'Maritime / description' ]` to `THEME_OPTIONS` in `dashboard/src/pages/Settings.jsx`.
4. Copy a theme palette block in `dashboard/src/pages/themes.css` and rename `:root.np-carbon` to `:root.np-maritime`. Set background, sidebar, panel, text, and border colors. Also include the new class in each shared `:root:is(...)` selector (or add a new ruleset using the same selectors).
5. Add `.theme-preview-maritime` to that CSS file.

Only UI presentation settings are saved in localStorage. **Never store your NetPilot control token or AWS secrets there.**

## Notes

- This patch assumes the prior NetPilot Settings Page v1 files are still in place. If you have edited these specific files since then, review differences before overwriting.
- These themes alter the appearance but do not change Docker, router operation, recovery behavior, or AWS service status.
- Unit tests verify preference values and class toggling, not the browser's pixel rendering.
