# PlanForge – Ambitious MVP PRD

## 1. Product Objective

Build a rule-driven, structurally-aware, compliance-validating G+1 2D residential planning engine for Indian small builders and civil engineers.

The system must:
- Generate 3 distinct layout options
- Enforce compliance rules
- Include structural grid awareness
- Export professional PDF drawings
- Support rectangular and quadrilateral plots

---

## 2. Target Users

- Small home builders (India)
- Civil engineers
- Draftsmen handling 600–3000 sq ft houses

---

## 3. Core Features

### 3.1 Plot Support
- Rectangular and convex quadrilateral plots
- Road-facing side selector
- North direction selector
- Custom setback inputs
- Minimum buildable area validation

---

### 3.2 Floors
- Ground + First floor
- Independent first-floor layout
- Mandatory vertical alignment for structure

---

### 3.3 Room Configuration
User inputs:
- Bedrooms (1–4)
- Number of toilets
- Parking (Yes/No)

System validates feasibility before generation.

---

### 3.4 Compliance Engine (India-based)

Enforced rules:
- Minimum bedroom size
- Minimum kitchen size
- Minimum toilet size
- Staircase width ≥ 900 mm
- Corridor width minimum
- Wall thickness (230mm external, 115mm internal)
- Setback validation
- Floor coverage validation

Rules stored in configurable JSON.

---

### 3.5 Structural Awareness Engine

Rule-based structural logic:
- Auto column placement at:
  - External corners
  - Major wall intersections
  - Staircase core
- Maximum beam span rule (4–4.5m)
- Vertical alignment across G+1
- Structural warning flags

No structural design calculations.

---

### 3.6 Layout Generation Engine

Generates 3 layout variations based on:
- Staircase placement
- Kitchen orientation
- Living orientation
- Bedroom distribution

Process:
1. Subtract setbacks
2. Define buildable polygon
3. Generate structural grid
4. Allocate rooms
5. Validate compliance
6. Produce 3 valid variants

---

### 3.7 Vastu (Optional Toggle)

If enabled:
- Kitchen preferred in SE
- Master bedroom in SW
- Living in NE
- Toilet avoidance in NE

Nearest-valid placement logic if conflicts arise.

---

### 3.8 Output

Single vector PDF containing:
- Ground floor plan
- First floor plan
- Column grid
- Room labels
- Dimensions
- North arrow
- Title block

Scale: 1:100

---

## 4. Tech Stack

Frontend:
- Next.js
- SVG rendering

Backend:
- FastAPI
- Shapely (geometry)
- Custom constraint solver
- Reportlab (PDF)

Database:
- PostgreSQL

Deployment:
- Docker + VPS

---

## 5. Timeline

Estimated 3–5 months solo development.

---

## 6. Risks

- Room packing complexity
- Structural span edge cases
- Layout combinatorial explosion
- Scope creep
- Burnout risk

---

## 7. Competitive Advantage

- Strong planning IP
- Hard to replicate engine
- High pricing power
- Solid SaaS foundation
