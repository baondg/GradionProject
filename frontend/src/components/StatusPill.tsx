import type { ProjectStatus } from "../types"

const LABELS: Record<ProjectStatus, string> = {
  draft: "Draft",
  in_progress: "In progress",
  done: "Done",
}

export function StatusPill({ status }: { status: ProjectStatus }) {
  const cls =
    status === "done" ? "ink" : status === "draft" ? "gray" : ""
  return (
    <span className={`gd-pill ${cls}`.trim()}>
      {status === "in_progress" ? <span className="dot" /> : null}
      {LABELS[status]}
    </span>
  )
}
