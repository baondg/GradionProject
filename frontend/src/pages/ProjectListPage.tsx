import { useEffect, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { listProjects } from "../api"
import { useAuth } from "../auth"
import { StatusPill } from "../components/StatusPill"
import { Stepper } from "../components/Stepper"
import { STEP_LABELS, type ProjectListItem, type StepKey } from "../types"

const STEP_ORDER: StepKey[] = [
  "style",
  "characters",
  "portraits",
  "chapters",
  "illustrations",
]

export function projectSubtitle(project: ProjectListItem): string {
  if (project.status === "draft") {
    return "Book text saved · style not yet generated"
  }
  if (project.status === "done") {
    return "All 5 steps complete"
  }
  if (project.completed_step === "none") {
    return "Book text saved · style not yet generated"
  }
  const index = STEP_ORDER.indexOf(project.completed_step)
  const names = STEP_ORDER.slice(0, index + 1).map((key) => STEP_LABELS[key])
  return `${names.join(" + ")} done`
}

export function ProjectListPage() {
  const { headers } = useAuth()
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null)
  const [error, setError] = useState("")
  const loadRef = useRef<() => Promise<void>>(async () => undefined)

  useEffect(() => {
    let cancelled = false
    async function fetchList() {
      try {
        const rows = await listProjects(headers)
        if (cancelled) return
        setError("")
        setProjects(rows)
      } catch (err: unknown) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : "Could not load projects.")
      }
    }
    loadRef.current = fetchList
    void fetchList()
    function onFocus() {
      void fetchList()
    }
    window.addEventListener("focus", onFocus)
    return () => {
      cancelled = true
      window.removeEventListener("focus", onFocus)
    }
  }, [headers])

  return (
    <div className="app-body">
      <div className="list-head">
        <h2>Your projects</h2>
        {projects && projects.length > 0 ? (
          <Link className="gd-btn gd-btn-primary" to="/projects/new">
            + New project
          </Link>
        ) : null}
      </div>
      {error ? (
        <div className="list-error">
          <p className="err">{error}</p>
          <button
            type="button"
            className="gd-btn gd-btn-secondary gd-btn-sm"
            onClick={() => void loadRef.current()}
          >
            Try again
          </button>
        </div>
      ) : null}
      {projects === null && !error ? (
        <div className="project-list" aria-busy="true">
          <div className="skeleton-row" />
          <div className="skeleton-row" />
        </div>
      ) : error && projects === null ? null : projects && projects.length === 0 ? (
        <div className="empty-state">
          <p>No projects yet.</p>
          <Link className="gd-btn gd-btn-primary" to="/projects/new">
            + New project
          </Link>
        </div>
      ) : projects ? (
        <div className="project-list">
          {projects.map((project, index) => (
            <div
              key={project.id}
              className="project-row"
              role="link"
              tabIndex={0}
              style={{ ["--stagger" as string]: `${index * 45}ms` }}
              onClick={() => navigate(`/projects/${project.id}`)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault()
                  navigate(`/projects/${project.id}`)
                }
              }}
            >
              <div className="title">
                <h4>{project.title}</h4>
                <span className="meta">
                  Created {formatDate(project.created_at)} · {projectSubtitle(project)}
                </span>
              </div>
              <Stepper steps={project.steps} mini />
              <StatusPill status={project.status} />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString()
}
