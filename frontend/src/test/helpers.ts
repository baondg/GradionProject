import type { ProjectDetail, ProjectListItem, ProjectAction, StepKey } from "../types"

const STEPS: StepKey[] = [
  "style",
  "characters",
  "portraits",
  "chapters",
  "illustrations",
]

export function listItem(
  overrides: Partial<ProjectListItem> = {},
): ProjectListItem {
  const current = overrides.current_step ?? "style"
  return {
    id: "p1",
    title: "The Wind in the Willows",
    created_at: "2026-08-13T12:00:00+00:00",
    status: "draft",
    completed_step: "none",
    current_step: current,
    run: "idle",
    stuck: false,
    action: "run",
    steps: STEPS.map((key) => ({
      key,
      view: key === current ? "current" : "pending",
    })),
    error: null,
    ...overrides,
  }
}

export function detail(
  action: ProjectAction,
  extra: Partial<ProjectDetail> = {},
): ProjectDetail {
  return {
    ...listItem({ action, current_step: extra.current_step ?? "style" }),
    book_text: "The Mole had been working very hard.",
    style: null,
    style_source: null,
    characters: [],
    chapters: [],
    attempts: [],
    ...extra,
    action,
  }
}
