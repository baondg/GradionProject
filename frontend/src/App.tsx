import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { AuthProvider, useAuth } from "./auth"
import { AppShell } from "./components/AppShell"
import { IdentityPage } from "./pages/IdentityPage"
import { NewProjectPage } from "./pages/NewProjectPage"
import { ProjectDetailPage } from "./pages/ProjectDetailPage"
import { ProjectListPage } from "./pages/ProjectListPage"

function ProtectedShell() {
  const { identity } = useAuth()
  if (!identity) return <Navigate to="/" replace />
  return <AppShell />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<IdentityPage />} />
          <Route element={<ProtectedShell />}>
            <Route path="/projects" element={<ProjectListPage />} />
            <Route path="/projects/new" element={<NewProjectPage />} />
            <Route path="/projects/:id" element={<ProjectDetailPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/projects" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
