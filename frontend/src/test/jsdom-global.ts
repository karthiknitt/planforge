/**
 * Per-file DOM environment for component tests (bun has no built-in DOM).
 *
 * Import this module BEFORE any React/RTL import in a *.test.tsx file.
 * We register jsdom rather than happy-dom because React 19's input
 * change-detection (value tracking) never fires onChange under happy-dom,
 * while keyboard-driven input via @testing-library/user-event works under
 * both. See site-style-step.test.tsx for the working interaction matrix.
 */
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
  url: "http://localhost/",
  pretendToBeVisual: true,
});

const g = globalThis as unknown as Record<string, unknown>;
const w = dom.window as unknown as Record<string, unknown>;
for (const key of [
  "window",
  "document",
  "navigator",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLSelectElement",
  "Event",
  "CustomEvent",
  "KeyboardEvent",
  "MouseEvent",
  "Node",
  "Element",
  "getComputedStyle",
  "requestAnimationFrame",
  "cancelAnimationFrame",
]) {
  g[key] = w[key];
}
// RTL's act() environment flag — silences React 19's not-wrapped-in-act noise.
(g.window as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// React's ChangeEventPlugin probes `"oninput" in document` to decide between
// the modern input-event path and an IE8 attachEvent polyfill that crashes
// under jsdom (jsdom implements neither document.oninput nor attachEvent).
// Declaring the handler keeps React on the modern path.
(document as unknown as Record<string, unknown>).oninput = null;

// Belt-and-braces: depending on module evaluation order react-dom may still
// have captured isInputEventSupported=false and route focusin through its IE
// polyfill. Give every element inert attach/detachEvent so that path is a
// no-op instead of a TypeError. Real input still flows through keyboard
// events (@testing-library/user-event).
const elementProto = dom.window.HTMLElement.prototype as unknown as Record<string, unknown>;
elementProto.attachEvent = () => {};
elementProto.detachEvent = () => {};
