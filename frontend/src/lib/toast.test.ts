import { describe, expect, it, mock } from "bun:test";
import { toast } from "sonner";
import { showErrorToast, showToast } from "./toast";

describe("showToast", () => {
  it("routes each tone to its matching sonner function", () => {
    const success = mock(() => "");
    const warning = mock(() => "");
    const info = mock(() => "");
    toast.success = success;
    toast.warning = warning;
    toast.info = info;

    showToast("success", "Plan approved");
    showToast("warning", "Design has warnings");
    showToast("info", "Structural design queued");

    expect(success).toHaveBeenCalledWith("Plan approved");
    expect(warning).toHaveBeenCalledWith("Design has warnings");
    expect(info).toHaveBeenCalledWith("Structural design queued");
  });
});

describe("showErrorToast", () => {
  it("routes to sonner's error toast", () => {
    const error = mock(() => "");
    toast.error = error;

    showErrorToast("Save failed");

    expect(error).toHaveBeenCalledWith("Save failed");
  });
});
