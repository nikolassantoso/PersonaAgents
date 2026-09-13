import type { Run } from "./data";

export interface RevampImage {
  persona_id: string;
  step: number;
  reasoning: string;
  original_screenshot_url: string;
  fixed_screenshot_url: string | null;
  status: "pending" | "generating" | "completed" | "failed";
  error: string | null;
}

export interface Revamp {
  run_id: string;
  status: "created" | "running" | "completed" | "partial" | "failed";
  total_images: number;
  completed_images: number;
  images: RevampImage[];
  error: string | null;
}

export function screenshotCount(run: Run): number {
  return Object.values(run.results).reduce(
    (count, result) => count + result.steps.filter((step) => step.screenshot_url).length, 0,
  );
}

export function canRevamp(run: Run): boolean {
  return !run.id.startsWith("demo") &&
    (run.status === "completed" || run.status === "failed") && screenshotCount(run) > 0;
}

export function revampInProgress(revamp: Revamp): boolean {
  return revamp.status === "created" || revamp.status === "running";
}
