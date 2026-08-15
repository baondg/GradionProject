import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AuthProvider } from "../auth"
import { AUTH_STORAGE_KEY } from "../types"
import { NewProjectPage } from "./NewProjectPage"

function renderNew() {
  localStorage.setItem(
    AUTH_STORAGE_KEY,
    JSON.stringify({ email: "mira@example.com", name: "Mira Hassan" }),
  )
  return render(
    <AuthProvider>
      <MemoryRouter>
        <NewProjectPage />
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe("NewProjectPage", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it("validates empty title and text without calling fetch", () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    renderNew()
    fireEvent.click(screen.getByRole("button", { name: /create project/i }))
    expect(
      screen.getByText(/give the project a title and provide the book text/i),
    ).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("rejects a non-.txt upload without calling fetch", () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    renderNew()
    const input = document.querySelector("#book-file") as HTMLInputElement
    const file = new File(["not a book"], "notes.pdf", { type: "application/pdf" })
    fireEvent.change(input, { target: { files: [file] } })
    expect(screen.getByText("Upload a .txt file.")).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("shows the API error when create fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ error: { message: "could not save project" } }),
    })
    vi.stubGlobal("fetch", fetchMock)
    renderNew()
    fireEvent.change(
      screen.getByPlaceholderText(/the wind in the willows/i),
      { target: { value: "River Bank" } },
    )
    fireEvent.change(
      screen.getByPlaceholderText(/once upon a time/i),
      { target: { value: "The Mole had been working." } },
    )
    fireEvent.click(screen.getByRole("button", { name: /create project/i }))
    expect(await screen.findByText(/could not save project/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })
  })
})
