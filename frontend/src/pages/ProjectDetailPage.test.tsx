import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AuthProvider } from "../auth"
import { detail } from "../test/helpers"
import { AUTH_STORAGE_KEY } from "../types"
import { ProjectDetailPage } from "./ProjectDetailPage"

function renderDetail() {
  localStorage.setItem(
    AUTH_STORAGE_KEY,
    JSON.stringify({ email: "mira@example.com", name: "Mira Hassan" }),
  )
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="/projects" element={<p>Projects home</p>} />
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe("ProjectDetailPage", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it("shows a load error when GET detail fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: { message: "backend down" } }),
      }),
    )
    renderDetail()
    expect(await screen.findByText(/backend down/i)).toBeInTheDocument()
  })

  it("navigates to the list on 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: { code: "not_found", message: "missing" } }),
      }),
    )
    renderDetail()
    expect(await screen.findByText("Projects home")).toBeInTheDocument()
  })

  it("renders attempt history from the detail payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () =>
          detail("run", {
            attempts: [
              {
                step: "style",
                at: "t",
                outcome: "failed",
                message: "quota",
              },
              {
                step: "style",
                at: "t2",
                outcome: "success",
                message: null,
              },
            ],
          }),
      }),
    )
    renderDetail()
    expect(await screen.findByText(/attempt history/i)).toBeInTheDocument()
    expect(screen.getByText(/2 attempts · last success/i)).toBeInTheDocument()
  })
})
