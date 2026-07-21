# Tada UI — how to build with it

Tada is a warm, no-guilt cleaning app. Screens are phone-first (~390px wide,
one column), friendly and rounded, set in Nunito (weights 500 and 800 only).

## Setup

No provider or wrapper is required — every component works bare. `AppShell`
is the screen frame (optional title bar + fixed bottom nav); put screen
content inside it and wrap the whole screen in a phone-width container.
Nav links render as plain anchors here; active-state highlighting follows the
page's real URL path.

## Styling idiom

Components style themselves via **props** (`variant`, `size`, `tone`, `band`,
`padding`) — never pass CSS classes to them. For your own layout glue
(wrappers, grids, headings), use inline styles or your own CSS built from the
design tokens. The tokens are CSS custom properties (defined at the end of
`_ds_bundle.css`):

- Anchor colors, each with one job: `--color-coral` (+`-strong`/`-soft`) = GO,
  primary actions; `--color-teal` (…) = DONE/success; `--color-purple` (…) =
  celebration. Neutrals: `--color-bg` (warm cream page), `--color-surface`
  (white cards), `--color-ink` / `--color-ink-soft` (text), `--color-line`
  (hairlines).
- Chip/category tints (bg+ink pairs): `--tint-peach-bg`/`--tint-peach-ink`,
  same for `berry`, `lavender`, `periwinkle`, `mint`, `neutral`.
- Dirtiness bands: `--status-fresh`, `--status-aging`, `--status-due`,
  `--status-overdue` (urgency reads as "could use some love", never a scold).
- Type: `--font-sans`; sizes `--text-xs`…`--text-2xl`; weights ONLY
  `--weight-regular` (500) and `--weight-bold` (800).
- Space `--space-1`(4px)…`--space-8`(48px); radii `--radius-card`,
  `--radius-button`, `--radius-pill`; shadows `--shadow-card`,
  `--shadow-raised`; motion `--motion-fast/base/slow`,
  `--ease-standard/pop`; min touch target `--tap-target` (48px).

## Component vocabulary

`Button` variant: `primary` (coral go) | `success` (teal Done) | `secondary`
(quiet) | `ghost`; size `md`|`lg`; `fullWidth`. `Chip` tone: the six tints
plus `coral`/`teal` (reserved for go/done meanings). `DirtinessDot` +
`TaskRow` take `band` / `Task` objects (see their prompt docs for the Task
shape). `FocusCard` is the one-task-at-a-time session card. `ProgressDots`
(`total`, `current` 1-based) is session momentum. `Burst` (`play`) and
`Confetti` (`active`) are the celebration moments. `SnoozeMenu` is the gentle
"when should it come back?" sheet.

## Where the truth lives

Read `styles.css` → `_ds_bundle.css` (component classes, tokens at the end)
and `fonts/fonts.css` before inventing styles; each component ships a
`.prompt.md` with composition examples and a `.d.ts` with its exact props.

## Idiomatic screen

```tsx
<AppShell
  title="Kitchen"
  nav={[
    { href: "/", label: "Home", icon: "🏠" },
    { href: "/rooms", label: "Rooms", icon: "🧹" },
    { href: "/settings", label: "Settings", icon: "⚙️" },
  ]}
>
  <div style={{ display: "grid", gap: "var(--space-4)", padding: "var(--space-4)" }}>
    <Card padding="lg">
      <Chip tone="peach">Kitchen</Chip>
      <h2
        style={{
          margin: "var(--space-3) 0 var(--space-1)",
          fontSize: "var(--text-xl)",
          fontWeight: "var(--weight-bold)",
          color: "var(--color-ink)",
        }}
      >
        Wipe the counters
      </h2>
      <p style={{ margin: 0, color: "var(--color-ink-soft)" }}>about 15 min</p>
      <div style={{ marginTop: "var(--space-4)" }}>
        <Button variant="success" size="lg" fullWidth>
          Done!
        </Button>
      </div>
    </Card>
  </div>
</AppShell>
```
