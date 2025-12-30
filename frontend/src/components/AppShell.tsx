import type { ReactNode } from 'react'
import { TopBar } from './TopBar'

export function AppShell(props: { children: ReactNode }) {
  return (
    <div className="min-h-full bg-bg text-fg">
      <TopBar />
      <main className="mx-auto w-full max-w-6xl px-4 py-6">{props.children}</main>
    </div>
  )
}

