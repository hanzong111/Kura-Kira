# DUIT frontend handoff — Co-op Arcade

**Goal:** update the existing couple spending dashboard to match `reference/selected-dashboard.png`, using this pack's actual assets. Hanz is P1, Vanisa is P2, and their orange tabby Chu Chu is the mascot. Preserve the application's current accounting, authentication, storage, and navigation; this pack supplies presentation assets and integration examples.

## 1. Start here

Open `preview.html` after unzipping. Resize to **1440 px** and **390 px** to see the responsive direction. Open `examples/asset-gallery.html` for the complete visual inventory and live animations. These are local examples, with no build step or remote font requests.

Recommended integration:

1. Copy `assets/` and `css/` into `public/duit/`, retaining their relative positions.
2. Load `/duit/css/duit.css` once. The CSS resolves its fonts and image URLs relative to itself.
3. Reuse the class names or translate the tokens into the project's existing styling system. The stylesheet has a small global reset; scope it to the dashboard if the rest of the application already has a design system.
4. Replace the example fixture with the existing app's data selectors. Do not replace working business logic with `examples/preview.js`.
5. Use the individual PNGs first; enable sprite animations where appropriate. Use the manifest instead of measuring the generation source sheets.

```html
<link rel="stylesheet" href="/duit/css/duit.css">
<img src="/duit/assets/brand/duit-cream.svg" alt="DUIT" width="184" height="56">
<span class="du-sprite" data-character="hanz" data-animation="idle"
      aria-hidden="true"></span>
```

`examples/BudgetMeter.tsx` is an optional React integration example. All graphics and CSS are framework independent.

## 2. Visual direction

A warm arcade scoreboard on a dark plum background. Cream panels hold the finances. Coral identifies Hanz; teal identifies Vanisa. The top skyline provides the Malaysian shophouse atmosphere. The two people and cat add personality without competing with the amounts.

Use square corners, stepped pixel silhouettes, **2 px inner borders**, **4 px outer frames**, and hard **4 px / 4 px / 0 blur shadows**. All spacing should use a 4 px rhythm, normally 8, 12, 16, or 24 px. Use flat fills. Do not add glass, soft shadows, smooth gradients, rounded cards, perspective, photographic backgrounds, or real brand logos.

The supplied mockup is a visual reference, not an image to stretch over the UI. Render every heading, name, amount, table cell, button, status, and percentage as live HTML. Only characters, skyline, logo, and icons are image assets.

### Palette

| CSS token | Hex | Use |
| --- | --- | --- |
| `--du-bg`, `--du-ink` | `#211B32` | Page background, outlines, readable text on light fills |
| `--du-surface` | `#F7EDCF` | Main cream panels |
| `--du-surface-light` | `#FFF7E3` | Controls and empty bar tracks |
| `--du-line` | `#C5B9A2` | Dashed separators and table rules |
| `--du-muted` | `#655B69` | Secondary text on cream |
| `--du-coral`, `--du-hanz` | `#F26F73` | P1 frame, primary warm accent |
| `--du-teal`, `--du-vanisa` | `#62B6BB` | P2 frame, cool accent |
| `--du-green` | `#5F9E71` | On track; paid tags |
| `--du-yellow` | `#F6CB45` | Ahead of pace; settlement strip |
| `--du-red` | `#E85167` | Over budget; due tags |
| `--du-blue` | `#77A9C0` | Partial bill payment |

Hanz's **green clothing is character art**, not a financial status. P1/P2 identity colors must never change because a budget becomes red. Use dark plum text on green/yellow/red fills, and readable status words alongside colors.

The raster art contains small shading variations of this palette. Do not recolor it with CSS filters.

### Typography

| Font | Local file | Use |
| --- | --- | --- |
| Press Start 2P Regular | `assets/fonts/PressStart2P-Regular.ttf` | Short section headings, P1/P2 chips, month at wide desktop sizes |
| IBM Plex Mono Regular | `assets/fonts/IBMPlexMono-Regular.ttf` | Body, tables, filter labels, metadata |
| IBM Plex Mono SemiBold | `assets/fonts/IBMPlexMono-SemiBold.ttf` | Amounts, budget labels, buttons, totals |

The CSS aliases are `DuitPixel` and `DuitMono`. Fonts are bundled and self-hosted. Keep the included OFL license files when redistributing them. The wordmark is custom SVG artwork and does not require a font.

Recommended sizes: hero amount 24 px desktop / 21 px phone; section headings 16–21 px desktop / 14–18 px phone; normal text 14 px; compact desktop table 12 px; phone transaction title 14 px and metadata 12 px. Do not reduce the whole desktop to fit a phone. Use `font-variant-numeric: tabular-nums` for amounts. Use the regular monospace font for long labels and data; reserve the wide pixel font for short headings.

## 3. File map

| Path | Role |
| --- | --- |
| `README.md` | Quick start |
| `FRONTEND_HANDOFF.md` | This design and implementation contract |
| `ASSET_INDEX.json` | File-level inventory with dimensions and SHA-256 hashes |
| `preview.html` | Responsive offline component demonstration |
| `examples/asset-gallery.html` | Complete visual asset gallery and animation preview |
| `examples/preview.js` | Sample-only interactions and fixture rendering |
| `examples/BudgetMeter.tsx` | Optional data-safe React meter example |
| `css/duit.css` | Fonts, tokens, panel components, responsive layouts, sprite playback |
| `assets/sprites/sprite-manifest.json` | Exact frame coordinates, anchors, animation rows and timings |
| `assets/sprites/{hanz,vanisa,chuchu}/` | Normalized sheets, 2× sheets, individual frames |
| `assets/icons/` | Individual SVGs, 48 px PNG copies, symbol sheet and manifest |
| `assets/brand/` | DUIT wordmarks and favicon |
| `assets/scene/` | Transparent skyline and optional dither tile |
| `assets/fonts/` | Self-hosted TTF fonts |
| `data/design-tokens.json` | Machine-readable palette, spacing and size tokens |
| `data/reference-fixture.json` | Clearly labeled design sample, money in integer cents |
| `data/reference-fixture.js` | Same fixture as a global for file:// preview compatibility |
| `reference/selected-dashboard.png` | User-selected source mockup |
| `source/*-generated.png` | Original generated art; retained unchanged for future edits |
| `source/generation-prompts.json` | Prompts and built-in generation provenance |
| `tools/export-art.cjs` | Repeatable alpha, slicing, alignment and nearest-neighbor export |
| `tools/build-ui-assets.cjs` | Editable definitions for the pixel SVG icon/logo set |
| `tools/build-demo.cjs` | Rebuilds the fixture and HTML entry points |
| `licenses/` | Third-party font licenses and provenance |

Runtime files are `assets/` and `css/`, plus whichever example components you adapt. You do not need to deploy `source/`, `reference/`, `tools/`, or the sample fixture.

## 4. Character sprites — exact usage

### Shared geometry

Every runtime frame is a **64 × 64 px RGBA PNG** with a transparent background, binary alpha, and a **bottom-center anchor `(32, 60)`**. The last four rows are transparent padding. All sheets have **4 columns**. There is **no gutter, extruded edge, or extra outside sheet margin**. Do not auto-trim individual frames: the padding keeps them aligned.

Use 64 × 64 CSS pixels for ordinary avatars and 128 × 128 for enlarged gallery views. The artwork occupies only part of each cell; this is deliberate. Use `image-rendering: pixelated`. Avoid 1.25× or 1.5× scales and fractional CSS positions. For a static `<img>`, use `idle-00.png`, set explicit dimensions, and disable image smoothing when using canvas.

`*-sheet@2x.png` is a nearest-neighbor duplicate with coordinates doubled. If using it for a 64 px CSS sprite, retain the logical `background-size` shown below; do not double CSS coordinates just because the source image is 2×. The CSS uses the smaller 1× sheets by default.

| Character | Sheet | Actual dimensions | 2× dimensions | Static default | Main placement |
| --- | --- | --- | --- | --- | --- |
| Hanz | `assets/sprites/hanz/hanz-sheet.png` | 256 × 128 | 512 × 256 | `assets/sprites/hanz/idle-00.png` | Header party; P1/Hanz card; optional payer detail |
| Vanisa | `assets/sprites/vanisa/vanisa-sheet.png` | 256 × 128 | 512 × 256 | `assets/sprites/vanisa/idle-00.png` | Header party; P2/Vanisa card; optional payer detail |
| Chu Chu | `assets/sprites/chuchu/chuchu-sheet.png` | 256 × 192 | 512 × 384 | `assets/sprites/chuchu/idle-00.png` | Header party; Vanisa card; empty states |

Characters are stylized versions of those in the selected design: short dark hair and green shirt for Hanz, long dark hair and coral top for Vanisa, orange/cream tabby for Chu Chu. They are not asserted to be photographic likenesses.

### Animation map

Each sequence has four frames read **left to right**. Frame `i` has source rectangle **`(i × 64, row × 64, 64, 64)`**. The manifest lists all 28 rectangles individually.

| Character / state | Row / Y | Individual files | Timing | Intended trigger |
| --- | --- | --- | --- | --- |
| Hanz idle | 0 / 0 | `hanz/idle-00.png` through `idle-03.png` | 4000 ms loop | Quiet default; brief blink |
| Hanz wave | 1 / 64 | `hanz/wave-00.png` through `wave-03.png` | 800 ms, 4 equal steps, once | Optional brief acknowledgment after a successful user action |
| Vanisa idle | 0 / 0 | `vanisa/idle-00.png` through `idle-03.png` | 4400 ms loop | Quiet default; offset from Hanz |
| Vanisa wave | 1 / 64 | `vanisa/wave-00.png` through `wave-03.png` | 800 ms, 4 equal steps, once | Optional brief acknowledgment |
| Chu Chu idle | 0 / 0 | `chuchu/idle-00.png` through `idle-03.png` | 4800 ms loop | Seated blink/tail pose |
| Chu Chu walk | 1 / 64 | `chuchu/walk-00.png` through `walk-03.png` | 640 ms, 4 equal steps, loop | Optional short decorative walk on an empty header rail |
| Chu Chu sleep | 2 / 128 | `chuchu/sleep-00.png` through `sleep-03.png` | 2400 ms, 4 equal steps, loop | Calm empty state or inactive mascot |

All paths in the animation table begin with `assets/sprites/`. Idle is **not** four equal-duration frames: hold frame 0 for 88% of the cycle, frame 1 for 2%, frame 2 for 2%, frame 3 for 8%. This prevents an unnaturally long blink. The CSS already implements this.

Use wave as a one-shot. On `animationend`, restore `data-animation="idle"`. Do not use `animation-fill-mode: forwards` with the sheet's full-width `steps(4)` endpoint: that endpoint lies beyond the fourth frame. If you want a frozen final pose, explicitly choose `wave-03.png` or a background X of `-192px`.

```html
<!-- Static avatar: simplest integration -->
<img src="/duit/assets/sprites/hanz/idle-00.png" width="64" height="64"
     alt="" style="image-rendering:pixelated">

<!-- Animated mascot -->
<span class="du-sprite" data-character="chuchu" data-animation="walk"
      data-facing="left" aria-hidden="true"></span>
```

Chu Chu's walk is drawn facing right. `data-facing="left"` mirrors that sprite only. Keep any movement of its containing element separate from sprite frame playback. Do not flip the entire UI or a label. Do not move Chu Chu across totals, controls, focus rings, or table content. Never interpret the mascot's pose as an accounting state.

The production PNGs are already cleaned and normalized. The original generation sheet had uneven row spacing for Chu Chu; `tools/export-art.cjs` records the corrected cuts. Slice the **runtime sheet**, not the raw source image. Source art remains unchanged. Technical export thresholds alpha at 128, aligns baselines, and resizes with nearest-neighbor; it does not redraw costumes or faces.

## 5. Brand and environment assets

| File | Native size | Display / usage |
| --- | --- | --- |
| `assets/brand/duit-cream.svg` | 23 × 7 viewBox | Main logo on plum; 184 × 56 desktop, 161 × 49 phone |
| `assets/brand/duit-ink.svg` | 23 × 7 viewBox | Alternate logo on cream; never use dark logo on plum |
| `assets/brand/duit-cream@10x.png` | 230 × 70 | Raster copy when SVG is unavailable |
| `assets/brand/duit-ink@10x.png` | 230 × 70 | Dark raster copy |
| `assets/brand/favicon.svg` | 32 × 32 | Browser tab icon, pixel D on plum |
| `assets/brand/favicon-32.png` | 32 × 32 | PNG favicon fallback |
| `assets/scene/skyline.png` | 384 × 64 | Transparent sunset shophouse header ornament |
| `assets/scene/skyline@2x.png` | 768 × 128 | Same image at 2×; display at 384 × 64 or 768 × 128 |
| `assets/scene/plum-dither.svg` | 8 × 8 | Optional repeating background tile; plain plum is the default |

The skyline is one coherent strip: buildings, trees, benches, sun, and lamp. It is **not** a seamlessly repeating tile or a parallax kit. Keep it top-right at wide widths, hide it below 1280 px, and do not stretch it vertically. Decorative scene images use `alt=""` and `aria-hidden="true"`.

## 6. Every UI icon

All icons use a **24 × 24** integer viewBox and crisp edges. Each row below maps to **`assets/icons/<id>.svg`** and **`assets/icons/<id>@2x.png`** (48 × 48). Display at 24 or 48 px; use a 44 px minimum hit area for clickable icons. Icons contain no text and no real brand logos.

| ID | Use |
| --- | --- |
| `coin-stack` | Combined budget heading |
| `heart` | Couple/card decoration; not a budget severity marker |
| `house` | Fixed House bill badge |
| `car` | Fixed Car bill badge |
| `receipt` | Spending log heading; Unsorted chip |
| `question` | Needs answer alert |
| `arrow-left` | Previous month |
| `arrow-right` | Next month |
| `chevron-down` | Custom dropdown affordance; omit when using the browser's own arrow |
| `search` | Search input |
| `download` | Export CSV action |
| `swap` | Settlement direction / transfer strip |
| `chart` | Top places heading |
| `sushi` | Optional Sushi-Mentai food illustration, unbranded |
| `grocery` | Grocery bucket; Jaya Grocer row illustration, unbranded |
| `petrol` | Petrol bucket; Petronas row illustration, unbranded |
| `calendar` | Month/date selection outside the main header |
| `weekday` | Weekday bucket (same drawing as calendar, semantic alias) |
| `weekend` | Weekend bucket, sun-face motif |
| `extra` | Extra bucket / occasional purchase |
| `paw` | Chu Chu & Toiletries bucket; cat expense |
| `soap` | Toiletries answer option where an icon is useful |
| `toll` | Toll bucket |
| `parents` | Parents bucket |
| `check` | Confirmed/paid state, accompanied by text |
| `clock` | Due/pending state, accompanied by text |
| `close` | Dismiss or close in existing app flows |
| `filter` | Filter toggle on small screens if the application uses a drawer |
| `plus` | Existing add-transaction action, if present |
| `medal` | Ranking badge base; render rank 1/2/3 as live text on top |
| `empty-wallet` | No transactions / empty result illustration |

Use individual files for `<img>` or imports. `assets/icons/icons.svg` also contains all symbols:

```html
<svg class="du-icon" aria-hidden="true">
  <use href="/duit/assets/icons/icons.svg#house"></use>
</svg>
```

Serve the symbol sheet from the same origin. The offline gallery uses individual SVGs because external `<use>` support under `file://` differs between browsers. An icon-only control must still have a visible tooltip or accessible name such as `aria-label="Previous month"`.

## 7. Layout and components

### A. Header

Order: DUIT logo; Hanz + Chu Chu + Vanisa; month picker with previous/next buttons; `day 17/31`; decorative skyline at the far right. Derive month, elapsed day, and number of days from the selected month and app timezone. Month navigation updates all dependent sections and filter defaults together.

### B. Combined budget

Full width, cream panel, teal outer frame with a small coral accent under COMBINED. A coin icon introduces the title. The large total reads `RM 3,120 / RM 5,020 spent (62%)` in the supplied fixture.

The hero bar contains a thin dark month-elapsed marker, with `Month 55%` underneath. Do not bake it into an image. Clamp the **visual fill** to 0–100%, preserve actual values in the label, and announce overage text. Keep green/yellow/red state names in a small legend.

Eight buckets, in this order: Weekday, Weekend, Extra, Grocery, Chu Chu & Toiletries, Petrol, Toll, Parents. Use 4 columns × 2 rows on wide desktop. The long Chu Chu label should wrap naturally when needed; never replace it with an unexplained icon.

Below the bars, use a dashed separator and live House/Car payment badges. These are not progress bars. Then the payer totals and the settlement strip.

### C. Personal cards

Hanz on the left, Vanisa on the right. Mirror their internal structures. Each dark title strip contains a colored P1/P2 chip, avatar, and large name. Card frame: coral for Hanz, teal for Vanisa. Chu Chu can sit beside Vanisa's heading.

Inside each: `This week` first, with Weekday and Weekend bars plus the numeric amount left; then `This month` total and its six smaller buckets. On wide desktop these sections can sit side by side. At intermediate widths put the weekly section above the monthly section. House/Car bill badges sit in the footer. Vanisa also has `Unsorted RM 120`.

For Toll at `RM 53 / RM 50`, fill the bar to 100%, add `OVER`, and show `RM 3 over`; the bar must not escape the frame. Bills and unsorted amounts are separate presentation components with their own domain semantics.

### D. Needs answer

A small full-width coral-framed alert with the question icon, `Watsons RM 75 · Vanisa: Toiletries or Extra?`, and the two live buttons. In the actual app, disable buttons during submission, prevent double assignment, keep the alert visible if saving fails, and update the correct transaction and aggregates only after the data layer accepts the change. A polite live region announces the result.

### E. Spending log and Top places

Wide desktop: log takes the flexible column; Top places occupies about 236 px on the right. Filters: month, who, bucket, category, search. Place Export CSV after the controls. Keep a real semantic table with headings:

`Date | Day | Who | Place / item | Bucket | Category | Amount | Split | Paid by`

Right-align Amount, retain two decimal places for transaction amounts, and keep split and payer details explicit. Use light dashed row rules and a slightly darker table heading strip. Real place names remain ordinary text. The sample Top places numbers are independent mockup data, not computed from the four visible example rows.

An empty filtered result gets a clear text message. Do not render a fake zero-spending success state while data is loading. A load failure should keep valid cached figures visibly distinguished from fresh data, according to the app's existing conventions.

### Responsive contract

| Width | Behavior |
| --- | --- |
| ≥1280 px | Full header including skyline; 4-column combined buckets; 2 personal cards; weekly/monthly sections side by side; log + right sidebar |
| 768–1279 px | Hide skyline; allow header wrapping as needed; 2-column combined buckets; 2 personal cards; weekly content above monthly inside each card; table can scroll locally |
| ≤767 px | Stack combined → Hanz → Vanisa → Needs answer → log → Top places; single-column combined buckets; wrap fixed badges; full-width settlement; 2-column filters with full-width search |
| 390 px target | 12 px page padding, 16 px section gaps, at least 44 px controls; one transaction per receipt entry; preserve every field |
| 320–359 px | Smaller logo and month control; keep body readable; wrap labels, do not scale the page |

At phone widths, each transaction card retains Date, Day, Who, place/item, Bucket, Category, Amount, Split and Paid by. Hanz must remain above Vanisa. Keep the DOM's reading order identical to the visual order. The preview keeps desktop and mobile transaction renderings in sync and hides the unused rendering with `display:none`; the production app may instead use one responsive component.

The original screenshot is dense. A **1440 × 900 viewport may scroll vertically** when exact labels, visible category amounts, and accessible controls need more room. Do not force a fixed 900 px container or hide the bottom of the log to imitate a screenshot. There should be no document-level horizontal scrolling at 390 px.

## 8. Budget behavior and data binding

Budget display math belongs to the app. Use **integer cents** (`312000` for RM 3,120) and format only for display. `who` / expense ownership and `paidBy` / cash paid are different fields; preserve that distinction.

For a pace-aware variable-spend bucket, the general rule is:

1. `spent > budget` → **Over budget**, red.
2. Otherwise, `spent / budget > elapsed proportion of that bucket's period` → **Ahead of pace**, yellow.
3. Otherwise → **On track**, green.

For weekly buckets, use elapsed time in that bucket's **week**, with the app's configured week start and eligible spending days. Do not use the monthly 55% marker for actual weekly classification. For a historical closed month, use the completed period; for a future month, use the app's planned-spending rules. Scheduled one-time obligations need cadence-aware treatment: an already-paid Parents budget need not imply a problem just because it is 100% used early in the month.

The preview deliberately uses the common **55%** sample marker to demonstrate colors. It is not the production status algorithm. Keep status, amount, and optional pace label separate so existing business rules can supply them.

For a zero/absent budget, show `No budget set`, or an explicit over-budget amount if the product's model defines zero as a real limit. Never divide by zero or show NaN/Infinity. Refunds may make net spending negative: preserve the actual value in text and clamp only the fill. All normal state labels need text, not color alone.

House/Car are fixed bills with statuses such as PAID / DUE / partial count. Derive them from bill records. Do not add their amounts to the category total again if the ledger already includes them. Keep unsorted transactions unassigned until they are resolved, with explicit inclusion/exclusion semantics in the app's totals.

For settlements, use each person's actual paid amounts **and allocated shares of the same eligible transactions**, including unequal splits and prior settlements. `Vanisa owes Hanz RM 86.30` is supplied display copy. It must not be derived from the two payer totals alone or assumed to mean a 50/50 split.

### Supplied sample inconsistencies — preserve only in the design fixture

| Item | Supplied values | Integration implication |
| --- | --- | --- |
| Joint total vs bucket totals | Hero RM 3,120; eight bucket spends sum to **RM 2,950** | RM 170 difference; no supplied explanation. Do not invent an extra bucket or correction. |
| Joint total vs people | RM 1,690 + RM 1,690 = **RM 3,380**, not RM 3,120 | Treat individual card totals as fixture values; derive real totals consistently. |
| Payer totals | RM 2,140 + RM 1,620 = **RM 3,760** | May have a different scope; the brief does not specify it. |
| Settlement | RM 86.30 | Not derivable without allocation and settlement records. Equal shares of the payer totals alone would produce RM 260, a different result. |
| Small personal bucket numbers | Only the Toll-over example is specified numerically | Other personal small-bar amounts in `personalBucketFixture` are clearly marked illustrative. Replace them with real app data. |
| Weekday names | 18 Oct = Sun, 16 Oct = Fri, 15 Oct = Thu, 14 Oct = Wed in 2026 | Original row labels Sat/Thu/Wed/Tue are preserved only in the fixture. Production should derive weekday from the actual date in its timezone. |
| Current day vs log | Header day 17; example row on 18 Oct | Future-dated row is a supplied visual example, not proof of a completed transaction. |
| Percentages | 3120/5020 ≈ 62.15%; 17/31 ≈ 54.84% | 62% and 55% are rounded labels; use unrounded values for calculation. |

The combined budget limits **do** sum to RM 5,020. The split lunch amounts RM 13.20 + RM 14.50 **do** equal RM 27.70. Preserve the supplied exact fixture for visual comparison, but use one authoritative transaction model when integrating the app.

## 9. Accessibility and motion

Use semantic headings, real buttons/selects/inputs, explicit field labels, and visible keyboard focus. Include a progressbar or equivalent accessible description with the real amount and state. For amounts over the limit, clamp `aria-valuenow` to the bounded range and include the actual overage in `aria-valuetext`. See `examples/BudgetMeter.tsx`.

Decorative avatars and icons beside visible labels use empty alternative text or `aria-hidden`. Do not announce the same person twice. A character shown by itself can have a concise label such as `Chu Chu, sleeping`.

`prefers-reduced-motion: reduce` freezes the sprite at the first frame of the selected row. Do not substitute a GIF that ignores this setting. Keep animations quiet, pause them offscreen if the existing app has that capability, and avoid flashing states. Financial success/failure should be conveyed with text rather than an emotional judgment from the characters.

## 10. Integration acceptance checks

- All files resolve under the intended asset base path; no missing fonts, black image rectangles, or blurry upscales.
- The desktop and 390 px phone layouts preserve the requested information order and all transaction fields.
- Hanz is coral/P1, Vanisa is teal/P2; status green/yellow/red remain independent.
- Fixed bills are badges, personal cards are mirrored, and the unresolved question has both choices.
- Sprite animation has no neighboring-frame bleed; wave returns to idle; cat left-facing is a sprite-only mirror.
- Keyboard focus is visible, buttons are operable, and reduced motion disables animation.
- Data selectors reconcile real totals, derive actual weekdays, use bucket-specific periods, and handle zero budgets/refunds.
- Filter and CSV scope match the existing application's intended behavior. The preview exports its filtered sample rows.

## 11. Source and maintenance

The character and skyline art were generated with the built-in image generation tool, guided by the user-selected reference. Prompts are in `source/generation-prompts.json`; original outputs are retained. SVG icons, logo, CSS, and examples were authored for this handoff. No stock logos or external icon library is embedded.

Optional rebuilding of technical exports uses Node.js with `sharp`:

```sh
# Run from the unzipped pack directory, with sharp available in your project.
node tools/export-art.cjs
node tools/build-ui-assets.cjs
node tools/build-demo.cjs
```

The three scripts regenerate their described derived files and retain source artwork. Keep any intentional edits to generated fixture/HTML files in the generator as well. If you edit or replace source art, re-check row cuts, anchors, all frames, and update the inventory hashes.

Font upstreams and licenses (retrieved 17 October 2026):

- Press Start 2P: https://github.com/google/fonts/tree/main/ofl/pressstart2p — included `licenses/PressStart2P-OFL.txt`.
- IBM Plex Mono: https://github.com/google/fonts/tree/main/ofl/ibmplexmono — included `licenses/IBMPlexMono-OFL.txt`.
- IBM Plex project: https://github.com/IBM/plex.

See `licenses/ASSET_PROVENANCE.md` for the distinction between generated artwork, handoff code, reference image, and third-party fonts. This pack does not claim exclusive rights to generated imagery or change the original reference image's ownership.
