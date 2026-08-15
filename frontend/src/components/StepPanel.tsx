import { useState } from "react"
import { STEP_LABELS, type ProjectDetail, type StepKey } from "../types"

export function StepPanel({
  project,
  posting,
  onRun,
}: {
  project: ProjectDetail
  posting: boolean
  onRun: (step: StepKey, style?: string) => void
}) {
  const [style, setStyle] = useState("")
  const step = project.current_step
  const label = step ? STEP_LABELS[step] : ""
  const busy = posting || project.action === "wait"
  const showStyleField =
    step === "style" &&
    (project.action === "run" ||
      project.action === "retry" ||
      project.action === "recover")

  if (project.action === "none") {
    return (
      <div className="step-panel">
        <div className="status-line done-line">
          <span className="gd-num-square done sm">✓</span>
          All 5 steps complete
        </div>
        <p className="help">
          This project is done. Reopen it any time; nothing here regenerates
          automatically.
        </p>
      </div>
    )
  }

  if (project.action === "wait") {
    return (
      <div className="step-panel">
        <div className="status-line">
          <span className="spinner" />
          Generating {label} — this step is running.
        </div>
        <p className="help">
          Refreshing or opening another tab will not start a second request.
        </p>
        <button className="gd-btn gd-btn-primary" type="button" disabled>
          Generating {label}…
        </button>
      </div>
    )
  }

  if (project.action === "retry") {
    return (
      <div className="step-panel">
        <div className="status-line">
          {label} failed. {project.error?.message ?? "Try this step again."}
        </div>
        {showStyleField ? (
          <StyleField value={style} onChange={setStyle} />
        ) : null}
        <p className="help">Earlier steps are kept. Only this step runs again.</p>
        <button
          className="gd-btn gd-btn-primary"
          type="button"
          disabled={busy || !step}
          onClick={() => step && onRun(step, style)}
        >
          Retry {label}
        </button>
      </div>
    )
  }

  if (project.action === "recover") {
    return (
      <div className="step-panel">
        <div className="status-line">
          This step was interrupted (the server restarted). Earlier results are
          kept. Recover is safe.
        </div>
        {showStyleField ? (
          <StyleField value={style} onChange={setStyle} />
        ) : null}
        <p className="help">One click claims the step and runs it again.</p>
        <button
          className="gd-btn gd-btn-secondary"
          type="button"
          disabled={busy || !step}
          onClick={() => step && onRun(step, style)}
        >
          Recover {label}
        </button>
      </div>
    )
  }

  return (
    <div className="step-panel">
      <div className="status-line">
        Ready for the next step: <b>{label}</b>.
      </div>
      {showStyleField ? (
        <StyleField value={style} onChange={setStyle} />
      ) : null}
      <p className="help">
        Reopening this page mid-step will not fire a second request.
      </p>
      <button
        className="gd-btn gd-btn-primary"
        type="button"
        disabled={busy || !step}
        onClick={() => step && onRun(step, style)}
      >
        Generate {label} <span className="gd-arrow">→</span>
      </button>
    </div>
  )
}

function StyleField({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="gd-field">
      <span>Art style (optional)</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Leave blank to let the model choose a style"
      />
    </label>
  )
}
