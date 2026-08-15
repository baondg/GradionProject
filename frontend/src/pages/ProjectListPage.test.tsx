import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
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
        <ProjectListPage />
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

  it("renders a row with a status pill", async () => {
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
  })

  it("shows a loading skeleton before the list arrives", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValue(new Promise(() => undefined)),
    )
    renderList()
    expect(document.querySelector("[aria-busy]")).toBeTruthy()
  })
})
