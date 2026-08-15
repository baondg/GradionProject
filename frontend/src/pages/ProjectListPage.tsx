import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { listProjects } from "../api"
import { useAuth } from "../auth"
import { StatusPill } from "../components/StatusPill"
import { Stepper } from "../components/Stepper"
import type { ProjectListItem } from "../types"

export function ProjectListPage() {
  const { headers } = useAuth()
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false
    void listProjects(headers)
      .then((rows) => {
        if (!cancelled) setProjects(rows)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load projects.")
          setProjects([])
        }
      })
    return () => {
      cancelled = true
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
      {error ? <p className="err">{error}</p> : null}
      {projects === null ? (
        <div className="project-list" aria-busy="true">
          <div className="skeleton-row" />
          <div className="skeleton-row" />
        </div>
      ) : projects.length === 0 ? (
        <div className="empty-state">
          <p>No projects yet.</p>
          <Link className="gd-btn gd-btn-primary" to="/projects/new">
            + New project
          </Link>
        </div>
      ) : (
        <div className="project-list">
          {projects.map((project) => (
            <div
              key={project.id}
              className="project-row"
              role="link"
              tabIndex={0}
              onClick={() => navigate(`/projects/${project.id}`)}
              onKeyDown={(event) => {
                if (event.key === "Enter") navigate(`/projects/${project.id}`)
              }}
            >
              <div className="title">
                <h4>{project.title}</h4>
                <span className="meta">
                  Created {formatDate(project.created_at)}
                </span>
              </div>
              <Stepper steps={project.steps} mini />
              <StatusPill status={project.status} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString()
}
