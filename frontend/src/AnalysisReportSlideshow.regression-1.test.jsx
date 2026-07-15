import fs from "node:fs";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

import { focusIfConnected, handleReportDialogKeydown } from "./AnalysisReportSlideshow.jsx";

// Regression: ISSUE-003 — slide report focus escaped into background controls.
// Found by /qa on 2026-07-15.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-07-15-2.md
describe("slide report dialog focus management", () => {
  const focusable = () => ({ isConnected: true, focus: vi.fn() });
  const keyEvent = (key, shiftKey = false) => ({ key, shiftKey, preventDefault: vi.fn() });
  const dialogWith = (elements) => ({
    isConnected: true,
    focus: vi.fn(),
    contains: (element) => elements.includes(element),
    querySelectorAll: vi.fn(() => elements)
  });

  it("closes on Escape and prevents the browser default", () => {
    const event = keyEvent("Escape");
    const onClose = vi.fn();

    expect(
      handleReportDialogKeydown(event, {
        dialog: null,
        activeElement: null,
        onClose,
        go: vi.fn()
      })
    ).toBe(true);
    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("wraps forward and reverse Tab focus at dialog boundaries", () => {
    const first = focusable();
    const middle = focusable();
    const last = focusable();
    const dialog = dialogWith([first, middle, last]);
    const forward = keyEvent("Tab");
    const reverse = keyEvent("Tab", true);

    handleReportDialogKeydown(forward, { dialog, activeElement: last });
    handleReportDialogKeydown(reverse, { dialog, activeElement: first });

    expect(forward.preventDefault).toHaveBeenCalledOnce();
    expect(reverse.preventDefault).toHaveBeenCalledOnce();
    expect(first.focus).toHaveBeenCalledOnce();
    expect(last.focus).toHaveBeenCalledOnce();
  });

  it("pulls focus back inside when it starts on a background control", () => {
    const first = focusable();
    const last = focusable();
    const outside = focusable();
    const dialog = dialogWith([first, last]);
    const event = keyEvent("Tab");

    handleReportDialogKeydown(event, { dialog, activeElement: outside });

    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(first.focus).toHaveBeenCalledOnce();
  });

  it("allows normal Tab movement between controls already inside", () => {
    const first = focusable();
    const middle = focusable();
    const last = focusable();
    const dialog = dialogWith([first, middle, last]);
    const event = keyEvent("Tab");

    expect(handleReportDialogKeydown(event, { dialog, activeElement: middle })).toBe(false);
    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it("keeps focus on the dialog when it has no enabled controls", () => {
    const dialog = dialogWith([]);
    const event = keyEvent("Tab");

    expect(handleReportDialogKeydown(event, { dialog, activeElement: null })).toBe(true);
    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(dialog.focus).toHaveBeenCalledOnce();
  });

  it("restores focus only to an element that is still connected", () => {
    const connected = focusable();
    const detached = { isConnected: false, focus: vi.fn() };

    expect(focusIfConnected(connected)).toBe(true);
    expect(focusIfConnected(detached)).toBe(false);
    expect(connected.focus).toHaveBeenCalledOnce();
    expect(detached.focus).not.toHaveBeenCalled();
  });

  it("wires the focus refs and keyboard handler into the dialog", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./AnalysisReportSlideshow.jsx"), "utf8");

    expect(source).toContain("openerRef.current = document.activeElement");
    expect(source).toContain("focusIfConnected(closeButtonRef.current || dialogRef.current)");
    expect(source).toContain("handleReportDialogKeydown(e, {");
    expect(source).toContain("ref={dialogRef}");
    expect(source).toContain("ref={closeButtonRef}");
  });
});
