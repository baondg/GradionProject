import { STEP_LABELS, type Attempt, type StepKey } from "../types"

const STEPS: StepKey[] = [
  "style",
  "characters",
  "portraits",
  "chapters",
  "illustrations",
]

export function AttemptHistory({ attempts }: { attempts: Attempt[] }) {
  if (!attempts.length) return null

  return (
    <div className="attempt-history">
      <h5>Attempt history</h5>
      {STEPS.map((step) => {
        const rows = attempts.filter((row) => row.step === step)
        if (!rows.length) return null
        const last = rows[rows.length - 1]
        return (
          <p key={step} className={`attempt-row${last.outcome === "failed" ? " failed" : ""}`}>
            <b>{STEP_LABELS[step]}</b>
            {": "}
            {rows.length} {rows.length === 1 ? "attempt" : "attempts"}
            {" · last "}
            {last.outcome}
            {last.outcome === "failed" && last.message ? ` — ${last.message}` : ""}
          </p>
        )
      })}
    </div>
  )
}
