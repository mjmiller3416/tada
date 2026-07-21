# design-sync notes — Tada

Repo-specific gotchas for re-syncs. Read before running the driver.

## Build wiring

- This is an app repo, not a library: there is no dist. The bundle entry is
  `frontend/src/design-sync.entry.ts` (committed, `cfg.entry`) — it re-exports
  exactly the synced components. Add new DS components there AND in
  `cfg.componentSrcMap`.
- `next/link` and `next/navigation` are aliased to browser shims in
  `.design-sync/shims/` via `.design-sync/tsconfig.sync.json` (`cfg.tsconfig`).
  Without them, Next client internals reference `process.env.__NEXT_*` at
  module level and the whole IIFE dies (`[BUNDLE_EXPORT] 12/12 not a
  component`). usePathname shim reads `location.pathname`, so nav active-state
  never shows in previews — expected.
- The tsconfig paths plugin resolves a directory target before trying
  `/index.ts`: `@/components/ui` needs its exact-file alias (first key in
  paths) or esbuild fails with `Cannot read file …/ui: Incorrect function`.
- Excluded components (`componentSrcMap: null` + not in the entry): AuthGate,
  HouseholdSection, KidHome, PushSubscribeButton, ServiceWorkerRegister,
  TaskForm — they fetch the API or register browser services on mount.
  TaskForm looks presentational but imports createTask/getMembers/getSupplies
  (multi-line import — single-line greps miss it).
- `frontend/src/lib/api.ts` must never enter the value graph
  (`process.env.NEXT_PUBLIC_API_URL` at module level). Type-only imports are
  fine.

## Styling / fonts

- Tokens live in `frontend/src/app/globals.css`, shipped via
  `cfg.cssEntry` (appended to `_ds_bundle.css`). No tokens package.
- Nunito is loaded by next/font at runtime in the app, so the repo ships no
  font files. `.design-sync/fonts/nunito.css` + two woff2 (variable font —
  one file serves weights 500 and 800; latin + latin-ext subsets, OFL,
  fetched from Google Fonts 2026-07) ship via `cfg.extraFonts`.
- `globals.css` line ~58 got `var(--font-nunito, "Nunito")` (fallback param
  added for non-Next consumers) — keep that if the file is regenerated.

## Verification environment

- playwright is installed in `.ds-sync/` WITHOUT browsers; render check +
  capture use system Chrome via
  `DS_CHROMIUM_PATH="C:/Program Files/Google/Chrome/Application/chrome.exe"`.

## Known render warns

- DirtinessDot (`AllBands` cell): a single ~14px row of 10px dots — the true
  component size. Expected `[RENDER_THIN]`; do not inflate.
- ProgressDots: legitimately tiny (8px dots, ~12px row). Expected
  `[RENDER_THIN]`; label copy in the cells gives scale context.
- AppShell nav never shows an active item in previews (shimmed usePathname
  can't match nav hrefs) — expected, not a bug.

## Preview techniques that work here (reuse on re-sync)

- Fixed-position containment without config overrides: wrap in
  `position: relative; overflow: hidden; transform: translateZ(0)` — the
  transform makes the wrapper the containing block for `position: fixed`
  descendants (AppShell bottom nav, Confetti shower). `min-height: 100dvh`
  and `105vh` keyframes still resolve against the real viewport; the
  wrapper's overflow clips the excess.
- Phone frames on grid sheets: keep wrappers ≤ 390×640 — taller frames get
  clipped by the sheet cell (~510 scaled px).
- One-shot animation freeze: `animation-play-state: paused !important` +
  negative `animation-delay`. Burst poses well at `-0.12s` with a compact
  48px circular marker (wide pills hide the particle ring) and `zoom: 1.5`.
  Confetti needs banded nth-child delays (`-0.25s` / `3n: -0.75s` /
  `3n+1: -1.25s`, all !important) to spread pieces across the card.
- Skipped-by-design states: FocusCard's mid-celebration Burst
  (interaction-only, 650ms window); Burst play=false / Confetti active=false
  (render null).

## Re-sync risks

- Nunito files are pinned copies of the Google Fonts v32 build; if the app
  moves to different weights/subsets in layout.tsx, refresh
  `.design-sync/fonts/`.
- The next/* shims track only what components use today (Link render,
  usePathname, useRouter no-ops, useSearchParams). A component using more of
  next/navigation will need the shim extended.
- The entry + componentSrcMap enumerate components by hand; a new component
  added to the app is NOT picked up automatically.
