import { type FormEvent, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { createProject } from "../api"
import { useAuth } from "../auth"

export function NewProjectPage() {
  const { headers } = useAuth()
  const navigate = useNavigate()
  const [title, setTitle] = useState("")
  const [text, setText] = useState("")
  const [fileName, setFileName] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  function onFile(file: File | undefined) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith(".txt")) {
      setError("Upload a .txt file.")
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      setText(String(reader.result ?? ""))
      setFileName(file.name)
      setError("")
    }
    reader.readAsText(file)
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmedTitle = title.trim()
    const trimmedText = text.trim()
    if (!trimmedTitle || !trimmedText) {
      setError(
        "Give the project a title and provide the book text (paste or upload).",
      )
      return
    }
    setError("")
    setSubmitting(true)
    try {
      const project = await createProject(trimmedTitle, trimmedText, headers)
      navigate(`/projects/${project.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create project.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="app-body narrow">
      <Link className="back-link" to="/projects">
        ← Back to projects
      </Link>
      <h3>Start a new illustration project</h3>
      <p className="meta lede-inline">
        Give it a title, then paste the book&apos;s text or upload a .txt file.
      </p>
      <form onSubmit={onSubmit}>
        <label className="gd-field">
          <span>
            Project title <span className="req">*</span>
          </span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="e.g. The Wind in the Willows — cottage-core"
          />
        </label>
        <div className="gd-field">
          <span>
            Book text <span className="req">*</span>
          </span>
          <label
            className={`dropzone${fileName ? " has-file" : ""}`}
            htmlFor="book-file"
          >
            <div className="drop-label">
              {fileName ? `✓ ${fileName} loaded` : "Click to choose a .txt file"}
            </div>
            <div className="hint">
              Plain text only · used once as context for every later step
            </div>
          </label>
          <input
            id="book-file"
            type="file"
            accept=".txt,text/plain"
            hidden
            onChange={(event) => onFile(event.target.files?.[0])}
          />
          <div className="divider-or">or paste text</div>
          <textarea
            rows={5}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Once upon a time, in a small burrow by the river..."
          />
        </div>
        {error ? <p className="err">{error}</p> : null}
        <button
          className="gd-btn gd-btn-primary wide"
          type="submit"
          disabled={submitting}
        >
          Create project <span className="gd-arrow">→</span>
        </button>
      </form>
    </div>
  )
}
