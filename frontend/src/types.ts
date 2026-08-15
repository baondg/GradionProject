export type StepKey =
  | "style"
  | "characters"
  | "portraits"
  | "chapters"
  | "illustrations"

export type StepView = "done" | "current" | "pending"

export type ProjectAction = "run" | "wait" | "retry" | "recover" | "none"

export type ProjectStatus = "draft" | "in_progress" | "done"

export type ProjectListItem = {
  id: string
  title: string
  created_at: string
  status: ProjectStatus
  completed_step: "none" | StepKey
  current_step: StepKey | null
  run: "idle" | "running" | "failed"
  stuck: boolean
  action: ProjectAction
  steps: { key: StepKey; view: StepView }[]
  error: { code: string; message: string } | null
}

export type ProjectDetail = ProjectListItem & {
  book_text: string
  style: string | null
  style_source: "user" | "generated" | null
  characters: { name: string; prompt: string; portrait_url: string | null }[]
  chapters: { name: string; prompt: string; illustration_url: string | null }[]
}

export const STEP_LABELS: Record<StepKey, string> = {
  style: "Style",
  characters: "Characters",
  portraits: "Portraits",
  chapters: "Chapters",
  illustrations: "Illustrations",
}

export const AUTH_STORAGE_KEY = "biStudio.identity"
