import { Outlet } from "react-router-dom";
import { MobileNav, Sidebar } from "./Sidebar";

export function AppShell() {
  return (
    <div className="flex min-h-screen bg-paper">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-surface px-4 py-2.5 sm:hidden">
          <span className="font-mono text-sm font-medium tracking-tight text-ink">
            Ledger<span className="text-accent">Lens</span>
          </span>
          <MobileNav />
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
