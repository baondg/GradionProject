import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AuthProvider } from "../auth"
import { listItem } from "../test/helpers"
import { AUTH_STORAGE_KEY } from "../types"
import { ProjectListPage } from "./ProjectListPage"

function renderList() {
  localStorage.setItem(
    AUTH_STORAGE_KEY,
    JSON.stringify({ email: "mira@example.com", name: "Mira Hassan" }),
  )
  return render(
    <AuthProvider>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<ProjectListPage />} />
          <Route path="/projects/:id" element={<p>Opened project</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe("ProjectListPage", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it("shows an empty state when there are no projects", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
    )
    renderList()
    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /new project/i })).toBeInTheDocument()
  })

  it("renders a row with a status pill and draft subtitle", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [listItem({ status: "draft" })],
      }),
    )
    renderList()
    expect(
      await screen.findByText("The Wind in the Willows"),
    ).toBeInTheDocument()
    expect(screen.getByText("Draft")).toBeInTheDocument()
    expect(
      screen.getByText(/book text saved · style not yet generated/i),
    ).toBeInTheDocument()
  })

  it("names completed steps for in-progress and done rows", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          listItem({
            id: "p-mid",
            title: "Mid",
            status: "in_progress",
            completed_step: "characters",
            current_step: "portraits",
          }),
          listItem({
            id: "p-done",
            title: "Done book",
            status: "done",
            completed_step: "illustrations",
            current_step: null,
            action: "none",
          }),
        ],
      }),
    )
    renderList()
    expect(await screen.findByText("Mid")).toBeInTheDocument()
    expect(screen.getByText(/style \+ characters done/i)).toBeInTheDocument()
    expect(screen.getByText(/all 5 steps complete/i)).toBeInTheDocument()
  })

  it("shows a loading skeleton before the list arrives", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValue(new Promise(() => undefined)),
    )
    renderList()
    expect(document.querySelector("[aria-busy]")).toBeTruthy()
  })

  it("shows a fetch error without the empty-state copy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: { message: "projects unavailable" } }),
      }),
    )
    renderList()
    expect(await screen.findByText(/projects unavailable/i)).toBeInTheDocument()
    expect(screen.queryByText(/no projects yet/i)).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument()
  })

  it("opens a row on Space", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [listItem({ status: "draft" })],
      }),
    )
    renderList()
    const row = await screen.findByRole("link", { name: /wind in the willows/i })
    fireEvent.keyDown(row, { key: " " })
    expect(await screen.findByText("Opened project")).toBeInTheDocument()
  })

  it("refetches the list on window focus", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [listItem({ status: "draft" })],
      })
    vi.stubGlobal("fetch", fetchMock)
    renderList()
    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument()
    window.dispatchEvent(new Event("focus"))
    expect(
      await screen.findByText("The Wind in the Willows"),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
