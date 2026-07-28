# PlanForge – Lean MVP PRD

## 1. Product Objective

Launch a G+1 rectangular plot planning tool that generates 3 template-based layout variations with essential compliance checks and exports PDF drawings.

Goal: Launch within 3 months and validate market demand.

---

## 2. Target Users

- Indian small home builders
- Civil engineers
- Draftsmen

---

## 3. Scope Restrictions

### 3.1 Plot Support
- Rectangular plots only
- User inputs:
  - Length
  - Width
  - Setbacks
  - Road side
  - North direction
- Minimum plot size validation

No quadrilateral plots in MVP.

---

### 3.2 Floors
- G+1
- First floor independent layout
- Staircase vertically aligned
- Columns vertically aligned

---

### 3.3 Room Configuration

User selects:
- 2BHK or 3BHK
- Number of toilets
- Parking required (Yes/No)

No arbitrary room count in MVP.

---

## 4. Layout Engine Strategy

Use 3 predefined parametric layout archetypes:

- Layout A: Front staircase
- Layout B: Center staircase
- Layout C: Rear staircase

Rooms arranged proportionally using deterministic slicing logic.

No dynamic constraint solver.

---

## 5. Compliance Rules (Essential Only)

Validate:
- Bedroom ≥ 9.5 sqm
- Kitchen ≥ 7 sqm
- Toilet ≥ 3 sqm
- Stair width ≥ 900 mm
- External wall thickness 230 mm
- Internal wall thickness 115 mm
- Floor coverage %
- Setback enforcement

Layouts rejected if invalid.

---

## 6. Structural Awareness

Basic column grid logic:
- Columns at outer corners
- Columns at staircase core
- Columns at major wall intersections
- Max beam span ≤ 4.5m
- Warning if exceeded

No structural design calculations.

---

## 7. Output

Single vector PDF containing:
- Ground floor plan
- First floor plan
- Column markers
- Room labels
- Dimensions
- North arrow
- Title block

Scale: 1:100

---

## 8. Tech Stack

Frontend:
- Next.js
- SVG rendering

Backend:
- FastAPI
- Shapely (geometry)
- Reportlab (PDF)

Database:
- PostgreSQL (store projects + layouts)

Deployment:
- Docker + VPS

---

## 9. Timeline

Estimated 6–8 weeks focused solo development.

---

## 10. Risks

- Overengineering layout logic
- Adding quadrilateral plots too early
- Expanding compliance rules prematurely
- Feature creep before launch

---

## 11. Strategy

- Launch fast
- Gather real user feedback
- Expand gradually:
  - Quadrilateral plots
  - Vastu
  - Advanced compliance
  - Smarter layout engine
