import type { ProjectDetail, ProjectListItem, StepKey } from "./types"

export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function readJson(response: Response): Promise<unknown> {
  const data: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    const err = (data as { error?: { code?: string; message?: string } }).error
    throw new ApiError(
      response.status,
      err?.code ?? "error",
      err?.message ?? response.statusText,
    )
  }
  return data
}

export async function identify(
  name: string,
  email: string,
): Promise<{ email: string; name: string }> {
  const response = await fetch("/api/identify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email }),
  })
  return (await readJson(response)) as { email: string; name: string }
}

export async function listProjects(
  headers: HeadersInit,
): Promise<ProjectListItem[]> {
  const response = await fetch("/api/projects", { headers })
  return (await readJson(response)) as ProjectListItem[]
}

export async function getProject(
  id: string,
  headers: HeadersInit,
): Promise<ProjectDetail> {
  const response = await fetch(`/api/projects/${id}`, { headers })
  return (await readJson(response)) as ProjectDetail
}

export async function createProject(
  title: string,
  text: string,
  headers: HeadersInit,
): Promise<ProjectDetail> {
  const form = new FormData()
  form.append("title", title)
  form.append("file", new File([text], "book.txt", { type: "text/plain" }))
  const response = await fetch("/api/projects", {
    method: "POST",
    headers,
    body: form,
  })
  return (await readJson(response)) as ProjectDetail
}

export async function runStep(
  id: string,
  step: StepKey,
  headers: HeadersInit,
  style?: string,
): Promise<ProjectDetail> {
  const body =
    step === "style" ? JSON.stringify({ style: style ?? "" }) : undefined
  const response = await fetch(`/api/projects/${id}/steps/${step}`, {
    method: "POST",
    headers: {
      ...headers,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body,
  })
  return (await readJson(response)) as ProjectDetail
}
