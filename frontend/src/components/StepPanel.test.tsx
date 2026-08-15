import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { detail } from "../test/helpers"
import { StepPanel } from "./StepPanel"

describe("StepPanel", () => {
  it("shows Generate for action run", () => {
    const onRun = vi.fn()
    render(
      <StepPanel
        project={detail("run", { current_step: "style" })}
        posting={false}
        onRun={onRun}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: /generate style/i }))
    expect(onRun).toHaveBeenCalledWith("style", "")
  })

  it("disables the button and names the step for action wait", () => {
    render(
      <StepPanel
        project={detail("wait", { current_step: "portraits" })}
        posting={false}
        onRun={vi.fn()}
      />,
    )
    expect(screen.getByText(/generating portraits — this step is running/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /generating portraits/i })).toBeDisabled()
  })

  it("shows the error and Retry for action retry", () => {
    render(
      <StepPanel
        project={detail("retry", {
          current_step: "characters",
          error: { code: "gemini_error", message: "quota" },
        })}
        posting={false}
        onRun={vi.fn()}
      />,
    )
    expect(screen.getByText(/quota/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /retry characters/i })).toBeEnabled()
  })

  it("shows Recover for action recover", () => {
    render(
      <StepPanel
        project={detail("recover", { current_step: "chapters", stuck: true })}
        posting={false}
        onRun={vi.fn()}
      />,
    )
    expect(screen.getByText(/server restarted/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /recover chapters/i })).toBeEnabled()
  })

  it("shows completion copy for action none", () => {
    render(
      <StepPanel
        project={detail("none", {
          current_step: null,
          completed_step: "illustrations",
          status: "done",
        })}
        posting={false}
        onRun={vi.fn()}
      />,
    )
    expect(screen.getByText(/all 5 steps complete/i)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /generate|retry|recover/i })).not.toBeInTheDocument()
  })
})
