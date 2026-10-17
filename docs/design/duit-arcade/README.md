# DUIT — Co-op Arcade asset pack

Production artwork and a frontend handoff based on the selected DUIT mockup.

1. Read **[FRONTEND_HANDOFF.md](FRONTEND_HANDOFF.md)**. It explains the design, every asset, sprite coordinates, responsive behavior, and data caveats.
2. Open **[preview.html](preview.html)** for the responsive dashboard example, or **[examples/asset-gallery.html](examples/asset-gallery.html)** to inspect every icon and animation. Both work offline after unzipping; keep the folder structure intact.
3. Copy `assets/` and `css/` together into the frontend's public asset directory. Keep application text and amounts in real HTML.

Included: Hanz and Vanisa idle/wave sprites; Chu Chu idle/walk/sleep sprites; 28 individual transparent PNG frames; 3 normalized sprite sheets and 2× copies; 31 SVG icons and PNG copies; skyline; DUIT wordmarks and favicon; fonts with licenses; reusable CSS; reference fixture; source artwork and regeneration/export scripts.

`preview.html` is an implementation example with sample-only filters, CSV export, and a classification interaction. It has no backend and saves nothing. The supplied sample figures are visually faithful but do not form a reconciled ledger. See the handoff before connecting real data.

The selected design is `reference/selected-dashboard.png`. Source image-generation sheets live in `source/`; use the normalized assets in `assets/` for the app.

Version: 1.0.0 · Prepared 17 October 2026.
