/**
 * SiteStyleStep — Task 24 (solver-capability-uplift plan).
 *
 * Deviations from the plan's sketch, recorded as "Task 24 rulings" in the plan:
 * - presets load from GET /api/backend/style-presets, so global.fetch is
 *   stubbed here and the first lookup uses findByLabelText;
 * - the derived road side at 90° is "E" (matching vastu.py's
 *   `road_side_for_north_angle`), not "W" — the sketch had the same E/W swap
 *   fixed twice during Phase 4.5;
 * - text entry uses userEvent.type: React 19's input value-tracking never
 *   fires onChange from fireEvent.change under bun's DOM environments, while
 *   keyboard events work (selects and clicks stay on fireEvent).
 */
import "@/test/jsdom-global";

import { afterAll, beforeAll, beforeEach, expect, test } from "bun:test";
import * as matchers from "@testing-library/jest-dom/matchers";
import { cleanup, fireEvent, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SiteStyleStep } from "./site-style-step";
import { PRESETS_FIXTURE } from "./site-style-step.fixtures";

beforeAll(() => {
  expect.extend(matchers);
});

beforeEach(() => {
  globalThis.fetch = (() =>
    Promise.resolve(
      new Response(JSON.stringify(PRESETS_FIXTURE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )) as typeof fetch;
});

afterAll(() => {
  cleanup();
});

async function renderStep() {
  const view = render(<SiteStyleStep onChange={() => {}} />);
  // Wait for the presets request to resolve before interacting.
  await view.findByLabelText("Style preset");
  return view;
}

test("notch fields are disabled for a rectangular plot", async () => {
  const view = await renderStep();
  expect(view.getByLabelText("Notch width")).toBeDisabled();
  expect(view.getByLabelText("Notch depth")).toBeDisabled();
});

test("offers exactly two plot shapes — T is not implemented", async () => {
  const view = await renderStep();
  // Task 9 raises on plot_template T/U. A third radio would let the user build
  // a request the backend rejects. See "Task 9 rulings" ruling 1.
  const shapes = view.getAllByRole("radio", {
    name: /Rectangle|L-shaped|T-shaped/,
  });
  expect(shapes).toHaveLength(2);
  expect(view.queryByLabelText("T-shaped")).toBeNull();
});

test("choosing L-shaped enables the notch fields", async () => {
  const view = await renderStep();
  fireEvent.click(view.getByLabelText("L-shaped"));
  expect(view.getByLabelText("Notch width")).not.toBeDisabled();
  expect(view.getByLabelText("Notch depth")).not.toBeDisabled();
});

test("selecting a style pre-ticks its typical programme with percentages", async () => {
  const view = await renderStep();
  fireEvent.change(view.getByLabelText("Style preset"), {
    target: { value: "Kerala" },
  });
  expect(view.getByLabelText(/Central courtyard/)).toBeChecked();
  expect(view.getByLabelText(/Car porch open/)).toBeChecked();
  expect(view.getByLabelText(/Verandah \/ osari/)).not.toBeChecked();
  // Kerala shows courtyard AND terrace at 30%, verandah AND pooja at 10%.
  expect(view.getAllByText(/typical \(30%\)/).length).toBeGreaterThan(0);
  expect(view.getAllByText(/uncommon \(10%\)/).length).toBeGreaterThan(0);
  expect(view.getByText(/rare \(0%\)/)).toBeInTheDocument();
});

test("a user override survives a later style change", async () => {
  const view = await renderStep();
  fireEvent.change(view.getByLabelText("Style preset"), {
    target: { value: "Kerala" },
  });
  fireEvent.click(view.getByLabelText(/Central courtyard/)); // untick
  fireEvent.change(view.getByLabelText("Style preset"), {
    target: { value: "Goan" },
  });
  expect(view.getByLabelText(/Central courtyard/)).not.toBeChecked();
});

test("road side is derived from the north angle and shown read-only", async () => {
  const view = await renderStep();
  const angle = view.getByLabelText("North angle");
  await userEvent.clear(angle);
  await userEvent.type(angle, "90");
  // Parity with vastu.py::road_side_for_north_angle — 90° is road side E.
  expect(view.getByTestId("derived-road-side")).toHaveTextContent("E");
});
