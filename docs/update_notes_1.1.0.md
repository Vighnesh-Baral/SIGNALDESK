# SIGNALDESK v1.1.0 — Premium workspace and product landing page

## Experience changes

- `/` is now a public, scroll-based product landing page explaining the customer problem, SIGNALDESK approach, capabilities, evidence standards and workspace entry points.
- `/app` is the separate customer intelligence workspace.
- Workspace uses a light, editorial SaaS visual system with warm ivory, lavender, periwinkle and pale cyan accents; translucent glass navigation and restrained glass panels; responsive modular dashboard layout; and reduced-motion support.
- Workspace navigation covers Overview, Analyse feedback, Investigations, Customers, Trends & comparison, Ask SIGNALDESK, and Reports & decisions.
- Existing upload, paste and single-complaint workflows and existing analysis APIs are retained.
- The workspace renders actual API results into overview metrics, theme bars, AI provenance, emotion signals, date trends, investigation cards, problem clusters, customer segments, evidence, Q&A and report download sections.
- Added a baseline-job comparison control wired to `POST /api/jobs/compare`.
- Added subtle CSS motion and scroll-reveal effects with `prefers-reduced-motion` handling. Hero and evidence graphics are inline SVG; the experience does not depend on remote image assets.

## Routes

- `GET /`: public landing page (`app/static/home.html`)
- `GET /app`: application workspace (`app/static/index.html`)

## Visual system

- Light theme only in this release.
- Warm ivory background with soft ambient lavender/cyan colour fields.
- Deep indigo text and muted periwinkle accents.
- Liquid-glass effects are limited to navigation, hero and selected workspace surfaces to preserve data legibility.
- No decorative motion is required for usability; reduced-motion preferences are respected.

## Notes

- Google Fonts are requested for DM Sans and Manrope; local system fallbacks are provided if the font service is unavailable.
- No frontend framework or new Python dependency was added.
- No changes were made to model prompts, classification logic or analysis semantics.
