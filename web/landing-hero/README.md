# SilentHelp landing hero

React + Tailwind hero mounted into `templates/landing-cinematic.html`. The existing Flask route and all sections except the former hero and beginning gallery are retained. The hero uses `sh-brain-engraving.png`, an anatomical illustration with SH integrated into its folds. Neuron locations are sampled from its visible surface. The original SH vector mark remains in the navigation.

```sh
cd web/landing-hero
npm ci
npm run check
npm run build
```

Commit the source and `static/cinematic/hero/` together. Flask serves the committed assets without requiring Node on the production host. The hero has a plain black background with no video, grid, or glass card. Original SilentHelp headline and descriptive copy are preserved. Motion respects reduced-motion preferences. Canvas work pauses offscreen and in hidden tabs; its backing resolution is capped at 2×. The larger illustration is drawn at 34% opacity. Muted, slow ambient neuron activity is composited into its surface without pointer interaction.

The non-hero content and demo interactions remain in the original template, `cinematic.css`, and `ui.js`. `landing-refinements.css` adds true black surfaces, monochrome styling, accessible mobile navigation, and staggered scroll reveals. The former global Three.js scene is no longer loaded on the landing page.

Brand assets: run `npm run build:brand` to render the supplied clean SH logo into website badges, full wordmarks, favicons, and native app icon sources. Rebuild and sign the macOS app on a Mac to include the new icon in its downloadable package.
