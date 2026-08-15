import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { AttemptHistory } from "./AttemptHistory"
import type { Attempt } from "../types"

const mixed: Attempt[] = [
  {
    step: "style",
    at: "2026-08-15T12:00:00+00:00",
    outcome: "failed",
    message: "quota",
  },
  {
    step: "style",
    at: "2026-08-15T12:01:00+00:00",
    outcome: "success",
    message: null,
  },
  {
    step: "characters",
    at: "2026-08-15T12:02:00+00:00",
    outcome: "success",
    message: null,
  },
]

describe("AttemptHistory", () => {
  it("renders grouped counts and the last failed message", () => {
    render(<AttemptHistory attempts={mixed} />)
    expect(screen.getByText(/attempt history/i)).toBeInTheDocument()
    expect(screen.getByText(/style/i).closest("p")).toHaveTextContent(
      /2 attempts · last success/i,
    )
    expect(screen.getByText(/characters/i).closest("p")).toHaveTextContent(
      /1 attempt · last success/i,
    )
    expect(screen.queryByText(/quota/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/portraits/i)).not.toBeInTheDocument()
  })

  it("shows the last error when the last outcome is failed", () => {
    render(
      <AttemptHistory
        attempts={[
          {
            step: "portraits",
            at: "t",
            outcome: "failed",
            message: "no image bytes",
          },
        ]}
      />,
    )
    expect(screen.getByText(/no image bytes/i)).toBeInTheDocument()
    expect(screen.getByText(/portraits/i).closest("p")).toHaveTextContent(
      /last failed/i,
    )
  })

  it("hides the block when there are no attempts", () => {
    const { container } = render(<AttemptHistory attempts={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
