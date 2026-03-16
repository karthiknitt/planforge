# PlanForge — Product Feature Roadmap

**Last updated:** 2026-03-15
**Owner:** Karthikeyan Natarajan
**Strategy:** Fix trust gaps → expand workflow coverage → grow via distribution

---

## Priority Framework

| Level | Label | Criteria |
|-------|-------|----------|
| P0 | **Now** | Blocks conversions, breaks trust, or is user-reported |
| P1 | **Next** | High impact, medium effort, clear user demand |
| P2 | **Later** | Differentiator features, higher effort |
| P3 | **Future** | Growth, distribution, enterprise |

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Done |
| 🔄 | In Progress |
| ⬜ | Not Started |
| ⏸ | Deferred |

---

## P0 — Fix Now (Trust & Quality Blockers)

These are issues that break professional trust or were caught in user testing.

| # | Feature | Problem It Solves | Effort | Status |
|---|---------|-------------------|--------|--------|
| P0-1 | **CAD primitives rendering fix** | `cad_primitives.py` and `cad_advanced.py` are not being called. Plans still look like colored rectangles, not architectural drawings. Breaks professional trust. | M | ✅ `aca53a9` |
| P0-2 | **Blank area auto-fill** | Unused floor space left in generated plans. GF residual area → Utility/Store room. Top floor residual → Open Terrace. Notify user of additions. | M | ✅ `4516c03` |
| P0-3 | **Beam & column layout as separate PDF pages** | Structural grid must be a separate drawing. Architectural plan (Pages 1–2) + Structural grid (Pages 3–4). Not overlaid. | S | ✅ `40af73c` |
| P0-4 | **Duplicate column keys fix** | React SVG column markers throw duplicate key warnings (`10.67-1.73`). Index-based keys needed. | XS | ✅ `943b83a` |
| P0-5 | **OpenRouter AI provider support** | AI chat hard-wired to Anthropic/OpenAI. Add OpenRouter so any model (Claude, GPT-4, Llama, Gemini) can be used. User has API key ready. | S | ✅ `5085bd2` |

---

## P1 — Next Sprint (High Impact, India-Specific)

These close the biggest gap between current features and real user workflows.

| # | Feature | Problem It Solves | Effort | Status |
|---|---------|-------------------|--------|--------|
| P1-1 | **Vastu toggle properly exposed in UI** | `vastu.py` exists but Vastu is not clearly visible in generate form or layout view. Add: enable toggle, zone overlay on SVG, per-layout Vastu score badge, violation list. | M | ✅ `a30a789` |
| P1-2 | **Share link (read-only client view)** | Engineer must export PDF and WhatsApp it. A shareable link (`/view/:token`) shows clean read-only layout with no edit UI. Works on mobile. | M | ✅ `24b2270` |
| P1-3 | **WhatsApp share button** | India's default comms channel. One-click share: thumbnail image + share link sent via WhatsApp Web API. | S | ✅ `d09c45f` |
| P1-4 | **Municipality / city bye-law selector** | Generic NBC compliance doesn't match Chennai (CMDA), Bangalore (BBMP), Hyderabad (GHMC), Pune (PMC). Each has different FAR, setback, and height rules. City selector auto-loads correct compliance JSON. | L | ✅ `ec5f145` |
| P1-5 | **Layout side-by-side comparison** | Users generate 3 layouts but can only view them one at a time. Add a compare view: 2 layouts shown at same scale side by side with diff highlights. | M | ✅ `8c8f44c` |

---

## P2 — Later (Differentiators & Upgrade Drivers)

Features that justify paid plans and build competitive moat.

| # | Feature | Problem It Solves | Effort | Status |
|---|---------|-------------------|--------|--------|
| P2-1 | **BOQ with city-wise material rates** | Current BOQ uses generic rates. Material costs vary 20–30% by city. Add city-linked rate table (steel, cement, bricks, tiles) to make estimates actionable. | M | ✅ `201ff1d` |
| P2-2 | **Manual room nudge / edit mode** | Plans are fully automated with no user control. Add click-to-select room → drag handles to resize. Live compliance check as user edits. | XL | ✅ `e51c17a` |
| P2-3 | **Approval drawing package** | Municipality submissions require specific formatting: title block with application number, owner name, plot survey number, engineer's license, seal block, IS-code line weights. Generate a "submit-ready" PDF. | L | ✅ `af310ad` |
| P2-4 | **Revision history / versioning** | No version control. If a user breaks a project they can't restore. Add v1/v2/v3 snapshots, visible in sidebar, with one-click restore. | M | ✅ `94a0ba7` |
| P2-5 | **Interior furniture overlay** | Post-layout "Furnish" mode: drop standard symbols (beds, sofa, dining, kitchen slab) to help clients visualize. Presentation layer only — no structural change. | L | ✅ `ceb23bc` |
| P2-6 | **Vastu zone overlay visualization** | Render the 16-zone or 8-zone Vastu grid as a semi-transparent SVG layer on the floor plan. Let users toggle it on/off. | M | ✅ covered by P1-1 `a30a789` |
| P2-7 | **4BHK / custom room count** | Currently capped at 3BHK. Larger plots (2400+ sqft) need 4BHK. Extend room config form and solver constraints. | M | ✅ `02a5f67` |

---

## P3 — Future (Growth, Distribution, Enterprise)

| # | Feature | Problem It Solves | Effort | Status |
|---|---------|-------------------|--------|--------|
| P3-1 | **Template gallery (public, SEO)** | Acquisition funnel. Public gallery of pre-generated plans filterable by plot size, BHK, city. "Customize this plan" → signup. Targets Google searches like "20x40 3BHK floor plan". | L | ✅ `ff1edc9` |
| P3-2 | **Team / firm plan** | Small firms (2–5 engineers) need shared project access. Admin seat + multiple engineer logins, shared project pool, ₹2,999/month. | L | ✅ `2ee61f3` |
| P3-3 | **Per-project credit pricing** | Many Indian builders won't subscribe monthly. Offer ₹99/project credits. Remove subscription barrier for occasional users. | S | ✅ `d48a201` |
| P3-4 | **Regional language support** | Add Tamil, Telugu, Hindi UI translations. Labels and room names in local language in SVG/PDF. | L | ✅ `824aefb` |
| P3-5 | **Client approval workflow** | Send plan to client email → client views read-only link → clicks "Approve" or "Request Changes" → engineer gets notification. Closes the loop in-product. | L | ✅ `93583ee` |
| P3-6 | **Annotation / notes on rooms** | Engineer can add sticky notes to specific rooms ("client wants wardrobe here", "verify column clearance"). Visible in exported PDF. | M | ✅ `339a2ea` |
| P3-7 | **L-shaped / irregular plot support** | Beyond rectangles and trapezoids, L-shaped plots are common in subdivided urban plots. Requires polygon input UI + solver changes. | XL | ✅ `0e0d968` |
| P3-8 | **Mobile-first responsive redesign** | Engineers use phones on site. Current UI is desktop-only. Generate and view plans on mobile. Export PDF from phone. | XL | ✅ `41b175c` |
| P3-9 | **Electrical layout overlay** | Basic switch, socket, light point positions overlaid on floor plan. Not full MEP — just typical residential layout per NBC standards. | L | ✅ `4e8dc3a` |
| P3-10 | **Plumbing layout overlay** | Pipe routing for bathrooms, kitchen, overhead tank. Overlay layer, not full MEP. | L | ✅ `4e8dc3a` |

---

## Effort Reference

| Label | Developer Days |
|-------|---------------|
| XS | < 1 day |
| S | 1–2 days |
| M | 3–5 days |
| L | 1–2 weeks |
| XL | 3–4 weeks |

---

## Monetization Map

| Feature | Ties To |
|---------|---------|
| Share link | Free (drives signups) |
| WhatsApp share | Free (distribution) |
| Vastu toggle | Basic tier |
| DXF export | Basic tier (existing) |
| Municipality bye-laws | Pro tier |
| Approval package | Per-submission add-on (₹999) |
| BOQ city rates | Pro tier |
| Manual edit mode | Pro tier |
| Team plan | Firm tier (₹2,999/month) |
| Per-project credits | One-time purchase (₹99/project) |

---

## Implementation Sequence (Recommended)

```
Sprint 1 (P0 fixes — quality baseline)
  → P0-4  Duplicate column keys         [XS]
  → P0-3  Beam/column separate PDF      [S]
  → P0-1  CAD primitives rendering fix  [M]
  → P0-2  Blank area auto-fill          [M]
  → P0-5  OpenRouter AI support         [S]

Sprint 2 (P1 — India workflow fit)
  → P1-3  WhatsApp share button         [S]
  → P1-2  Share link / client view      [M]
  → P1-1  Vastu UI (toggle + badges)    [M]
  → P1-5  Side-by-side comparison       [M]

Sprint 3 (P1 + P2 — professional tools)
  → P1-4  Municipality bye-law selector [L]
  → P2-4  Revision history              [M]
  → P2-1  BOQ city-wise rates           [M]

Sprint 4 (P2 — upgrade drivers)
  → P2-3  Approval drawing package      [L]
  → P2-6  Vastu zone SVG overlay        [M]
  → P2-7  4BHK support                  [M]

Sprint 5+ (P3 — growth)
  → P3-1  Template gallery              [L]
  → P3-3  Per-project credits           [S]
  → P3-2  Team / firm plan              [L]
  → P3-5  Client approval workflow      [L]
```

---

## Testing Backlog

Backend: **108/108** passing. Frontend: **0 test files** (no Vitest setup yet).

The following features shipped without dedicated tests and need coverage:

| Priority | Feature | Gap | Effort |
|----------|---------|-----|--------|
| High | **Compliance-check endpoint** (P2-2) | `POST /api/layouts/{id}/compliance-check` has no test — wrong result = bad wall-drag feedback | XS |
| High | **L-shaped compliance area** (P3-7) | FAR calculation using inset polygon needs a regression test | XS |
| Medium | **BOQ city rates** (P2-1) | Financial data — wrong rates erode trust | XS |
| Medium | **Share token** (P1-2) | Security-sensitive public endpoint — generate + read-only access | S |
| Medium | **Revision history** (P2-4) | Snapshot create + restore lifecycle | S |
| Low | **Approval PDF fields** (P2-3) | Formatting-only, low risk | XS |
| Low | **Frontend component tests** | No Vitest baseline exists; start with `FloorPlanSVG` render + `detectSharedWalls` unit | M |

---

## Notes

- P0 items are prerequisites before any marketing or user acquisition push
- P1-1 (Vastu) and P1-2 (Share link) together = the strongest single sprint for user retention and word-of-mouth
- P1-4 (Municipality bye-laws) is the highest-effort P1 but creates the deepest professional moat — no competitor in India has city-specific compliance
- Manual edit mode (P2-2) shipped with XL effort; most-requested power-user feature confirmed
