import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell.tsx'
import { NotFoundPage } from './pages/NotFoundPage.tsx'
import { MemoryDetailPage } from './pages/MemoryDetailPage.tsx'
import { MemoriesPage } from './pages/MemoriesPage.tsx'
import { RunDetailPage } from './pages/RunDetailPage.tsx'
import { RunsPage } from './pages/RunsPage.tsx'
import { SettingsProductsPage } from './pages/SettingsProductsPage.tsx'
import { SettingsPresetsPage } from './pages/SettingsPresetsPage.tsx'

function _routerBasename(): string {
  const rawBase = import.meta.env.BASE_URL || '/'
  if (rawBase === '/') return '/'
  return rawBase.endsWith('/') ? rawBase.slice(0, -1) : rawBase
}

export default function App() {
  return (
    <BrowserRouter basename={_routerBasename()}>
      <AppShell>
        <Routes>
          <Route path="/" element={<RunsPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/runs" element={<Navigate to="/" replace />} />
          <Route path="/memories" element={<MemoriesPage />} />
          <Route path="/memories/:memId" element={<MemoryDetailPage />} />
          <Route path="/settings/products" element={<SettingsProductsPage />} />
          <Route path="/settings/presets" element={<SettingsPresetsPage />} />
          <Route path="/settings" element={<Navigate to="/settings/products" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  )
}
