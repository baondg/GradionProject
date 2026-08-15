import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { ApiError, getProject, runStep } from "../api"
import { useAuth } from "../auth"
import { BookTextModal } from "../components/BookTextModal"
import { ChapterCard } from "../components/ChapterCard"
import { CharacterCard } from "../components/CharacterCard"
import { StepPanel } from "../components/StepPanel"
import { Stepper } from "../components/Stepper"
import { useProjectPoll } from "../hooks/useProjectPoll"
import type { ProjectDetail, StepKey } from "../types"

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { headers, identity } = useAuth()
  const navigate = useNavigate()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [posting, setPosting] = useState(false)
  const [bookOpen, setBookOpen] = useState(false)
  const [loadError, setLoadError] = useState("")

  const refresh = useCallback(async () => {
    if (!id) return
    try {
      const next = await getProject(id, headers)
      setProject(next)
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 403)) {
        navigate("/projects", { replace: true })
        return
      }
      setLoadError(err instanceof Error ? err.message : "Could not load project.")
    }
  }, [headers, id, navigate])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useProjectPoll(id, project?.action, refresh)

  async function onRun(step: StepKey, style?: string) {
    if (!id) return
    setPosting(true)
    try {
      const next = await runStep(id, step, headers, style)
      setProject(next)
    } catch (err) {
      if (err instanceof ApiError && err.code === "in_flight") {
        await refresh()
        return
      }
      setLoadError(err instanceof Error ? err.message : "Step failed to start.")
    } finally {
      setPosting(false)
    }
  }

  if (!project) {
    return (
      <div className="app-body">
        <Link className="back-link" to="/projects">
          ← Back to projects
        </Link>
        {loadError ? <p className="err">{loadError}</p> : <div className="skeleton-row" />}
      </div>
    )
  }

  const portraitsWaiting =
    project.action === "wait" && project.current_step === "portraits"
  const illustrationsWaiting =
    project.action === "wait" && project.current_step === "illustrations"

  return (
    <div className="app-body">
      <Link className="back-link" to="/projects">
        ← Back to projects
      </Link>
      <h2 className="detail-title">{project.title}</h2>
      <p className="meta detail-meta">
        Created {formatDate(project.created_at)}
        {identity ? ` by ${identity.name}` : ""}
      </p>
      <button
        type="button"
        className="gd-btn gd-btn-ghost gd-btn-sm"
        onClick={() => setBookOpen(true)}
      >
        Read full text →
      </button>
      <Stepper steps={project.steps} />
      <div className="detail-grid">
        <div>
          <StepPanel project={project} posting={posting} onRun={onRun} />
          {project.characters.length > 0 ? (
            <section className="entity-section">
              <div className="panel-title">
                <h3>Characters ({project.characters.length})</h3>
              </div>
              <div className="entity-grid">
                {project.characters.map((character) => (
                  <CharacterCard
                    key={character.name}
                    name={character.name}
                    prompt={character.prompt}
                    portraitUrl={character.portrait_url}
                    waiting={portraitsWaiting}
                  />
                ))}
              </div>
            </section>
          ) : null}
          {project.chapters.length > 0 ? (
            <section className="entity-section">
              <div className="panel-title">
                <h3>Chapters ({project.chapters.length})</h3>
              </div>
              <div className="entity-grid chapters">
                {project.chapters.map((chapter) => (
                  <ChapterCard
                    key={chapter.name}
                    name={chapter.name}
                    prompt={chapter.prompt}
                    illustrationUrl={chapter.illustration_url}
                    waiting={illustrationsWaiting}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </div>
        <aside>
          {project.style ? (
            <div className="side-note">
              <h5>Style</h5>
              <p>{project.style}</p>
            </div>
          ) : (
            <div className="side-note">
              <h5>Book text</h5>
              <p className="snippet">{snippet(project.book_text, 220)}</p>
            </div>
          )}
        </aside>
      </div>
      {bookOpen ? (
        <BookTextModal
          text={project.book_text}
          onClose={() => setBookOpen(false)}
        />
      ) : null}
    </div>
  )
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString()
}

function snippet(text: string, max: number): string {
  const compact = text.replace(/\s+/g, " ").trim()
  return compact.length > max ? `${compact.slice(0, max)}…` : compact
}
