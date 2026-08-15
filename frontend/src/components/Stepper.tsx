import { STEP_LABELS, type ProjectListItem } from "../types"

export function Stepper({
  steps,
  mini = false,
}: {
  steps: ProjectListItem["steps"]
  mini?: boolean
}) {
  if (mini) {
    return (
      <div className="progress-mini" aria-hidden="true">
        {steps.map((step) => (
          <span
            key={step.key}
            className={`seg${step.view === "done" ? " on" : ""}`}
          />
        ))}
      </div>
    )
  }

  return (
    <div className="stepper" aria-label="Pipeline steps">
      {steps.map((step, index) => (
        <div key={step.key} className="step-wrap">
          <div className={`step ${step.view}`}>
            <span
              className={`gd-num-square ${
                step.view === "done"
                  ? "done"
                  : step.view === "pending"
                    ? "gray"
                    : ""
              }`.trim()}
            >
              {step.view === "done" ? "✓" : index + 1}
            </span>
            <span className="lbl">{STEP_LABELS[step.key]}</span>
          </div>
          {index < steps.length - 1 ? (
            <div
              className={`connector${step.view === "done" ? " done" : ""}`}
            />
          ) : null}
        </div>
      ))}
    </div>
  )
}
