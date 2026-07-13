# AI Render Accuracy — PR #23 verification + fixes (Bug #11, 2026-07-12)

## Reported symptoms (pro-tester)
- Car parked inside the staircase area; paving/parking drawn where the plan has none
- Dining room missing from the render
- Dimensions "a bit random"

## Did PR #23's fix work?
Partially. PR #23 (`8cc0f60` + `e7125f1`) correctly wired the R3F snapshot as the
img2img conditioning image (the `python-multipart` dep fix made the multipart
upload actually reach the backend — verified by `test_render_jobs.py`). So the
model *was* receiving true geometry. The remaining inaccuracy is a prompt +
conditioning-view problem, not a plumbing problem:

1. **Isometric conditioning** — the 3/4 iso view distorts room proportions and
   hides layout structure; gpt-image-2 follows a top-down plan reference far
   more literally. Fixed: the R3F scene now defaults to a **direct top-down
   plan view** (`view="top"`), which is also what the tester asked to see.
2. **No negative constraints** — the prompt listed rooms to draw but never
   said what NOT to draw. Image models fill "empty-looking" floor area with
   stock content (cars, paving, gardens). Fixed in `render_prompt.py`:
   data-driven hard constraints — "NO parking/garage/driveway" when the floor
   has none, "Dining MUST be visible" when present, the staircase pinned to
   its exact coordinates, and "render NOTHING that is not listed".
3. **Wrong CAD fallback page** — when no R3F snapshot was attached, the CAD
   fallback always rasterised **page 0 (GF)** even for a first-floor render.
   Fixed: page index mapped per floor (GF=0, FF=1).
4. **Single-floor pipeline** — renders were implicitly GF-only. Fixed: floor
   is now a first-class parameter through job → runner → prompt → cache.

## What can't be fixed in code
gpt-image-2 does not do metric-accurate geometry; dimensions will always be
approximate. The top-down R3F reference + exact room list keeps proportions
close, but treat renders as visualisation, not drawings (the PDFs remain the
dimensioned deliverable).

## Recommended follow-ups (not in this branch)
- A/B the top-down R3F reference vs the CAD plan-page reference per provider.
- Consider `image_guidance`/fidelity params if OpenRouter exposes them.
- Optionally overlay room labels in the R3F capture (text in the reference
  strongly anchors room identity for img2img models).
