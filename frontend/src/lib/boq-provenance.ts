// BOQ provenance — pure helpers for the "IS-code designed" vs "estimated"
// per-line badges and the top-level "PRELIMINARY ESTIMATE" banner. The
// backend basis field is being added on a sibling branch; code defensively
// here so this component doesn't break before/if that field is absent.

export type BOQBasis = "designed" | "estimated";

export interface BOQProvenanceItem {
  basis?: string | null;
}

export interface BOQProvenanceSummary {
  preliminary?: boolean | null;
  basis_summary?: string | null;
  items?: BOQProvenanceItem[];
}

export function boqBasisLabel(basis: string | null | undefined): string {
  return basis === "designed" ? "IS-code designed" : "estimated";
}

// True once at least one line item carries a basis field — used to decide
// whether the backend has shipped provenance data at all yet.
export function hasBasisData(boq: BOQProvenanceSummary): boolean {
  return (boq.items ?? []).some((item) => item.basis != null);
}

// Show the preliminary banner when the backend says so explicitly, OR when
// no basis data is present at all (older backend / feature not yet live —
// treat as estimated/preliminary rather than silently claiming precision).
export function shouldShowPreliminaryBanner(boq: BOQProvenanceSummary): boolean {
  if (boq.preliminary === true) return true;
  if (boq.preliminary === false) return false;
  return !hasBasisData(boq);
}
