# SilentHelp landing hero

React + Tailwind hero mounted into `templates/landing-cinematic.html`. The existing Flask route and all sections except the former hero and beginning gallery are retained. The hero uses `sh-brain-engraving.png`, an anatomical illustration with SH integrated into its folds. Neuron locations are sampled from its visible surface. The original SH vector mark remains in the navigation.

```sh
cd web/landing-hero
npm ci
npm run check
npm run build
```

Commit the source and `static/cinematic/hero/` together. Flask serves the committed assets without requiring Node on the production host. HLS is lazy-loaded, with `enableWorker: false`; the black hero remains usable if streaming or JavaScript is unavailable. Motion respects reduced-motion preferences. Canvas work pauses offscreen and in hidden tabs; its backing resolution is capped at 2×. Move over or tap the brain to reveal 220 seeded synapses; keyboard focus activates the center.

The non-hero content and demo interactions remain in the original template, `cinematic.css`, and `ui.js`. `landing-refinements.css` adds true black surfaces, monochrome styling, accessible mobile navigation, and staggered scroll reveals. The former global Three.js scene is no longer loaded on the landing page.
