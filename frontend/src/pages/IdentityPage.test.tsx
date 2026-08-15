import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AuthProvider } from "../auth"
import { AUTH_STORAGE_KEY } from "../types"
import { IdentityPage } from "./IdentityPage"

function renderIdentity() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<IdentityPage />} />
          <Route path="/projects" element={<p>Projects home</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe("IdentityPage", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it("shows a validation error when name or email is invalid", () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    renderIdentity()
    fireEvent.click(screen.getByRole("button", { name: /continue/i }))
    expect(
      screen.getByText(/enter your name and a valid email/i),
    ).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("identifies and navigates when name and email are valid", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ email: "mira@example.com", name: "Mira Hassan" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    renderIdentity()
    fireEvent.change(screen.getByPlaceholderText("Mira Hassan"), {
      target: { value: "Mira Hassan" },
    })
    fireEvent.change(screen.getByPlaceholderText("mira@example.com"), {
      target: { value: "mira@example.com" },
    })
    fireEvent.click(screen.getByRole("button", { name: /continue/i }))
    await waitFor(() => {
      expect(screen.getByText("Projects home")).toBeInTheDocument()
    })
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/identify",
      expect.objectContaining({ method: "POST" }),
    )
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toContain("mira@example.com")
  })
})
