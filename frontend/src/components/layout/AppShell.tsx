// Application shell: a 232px ink-900 sidebar on wide screens; on phones and tablets a top bar whose menu opens the
// same navigation stacked above the content.
import {
  ChartColumn, ClipboardList, FileText, GraduationCap, Inbox, LayoutDashboard, LogOut, Menu, UserRound, X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { PRODUCT_NAME } from "@/lib/brand";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

type NavItem = { to: string; label: string; icon: ReactNode; end?: boolean };

const TEACHER_NAV: NavItem[] = [
  { to: "/teacher", label: "Dashboard", icon: <LayoutDashboard />, end: true },
  { to: "/teacher/assessments", label: "Assessments", icon: <FileText /> },
  { to: "/teacher/submissions", label: "Submissions", icon: <Inbox /> },
  { to: "/teacher/analytics", label: "Analytics", icon: <ChartColumn /> },
];

const STUDENT_NAV: NavItem[] = [
  { to: "/student", label: "Dashboard", icon: <LayoutDashboard />, end: true },
  { to: "/student/assessments", label: "Assessments", icon: <FileText /> },
  { to: "/student/submissions", label: "Submissions", icon: <ClipboardList /> },
  { to: "/student/results", label: "Results", icon: <GraduationCap /> },
];

/** Wordmark: a margin rule beside the product name. */
export function Logo({ className, inverse }: { className?: string; inverse?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2 whitespace-nowrap text-h4 font-semibold", inverse ? "text-white" : "text-ink-900", className)}>
      <span aria-hidden className={cn("h-6 w-[3px] rounded-full", inverse ? "bg-ink-300" : "bg-ink-600")} />
      {PRODUCT_NAME}
    </span>
  );
}

function NavLinks({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {items.map(({ to, label, icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={onNavigate}
          className={({ isActive }) => cn(
            "flex h-11 items-center gap-3 rounded-sm px-3 text-body font-medium no-underline transition-colors duration-150 [&_svg]:size-[18px]",
            isActive ? "bg-ink-700 text-white hover:text-white" : "text-ink-100 hover:bg-ink-800 hover:text-white",
          )}>
          {icon}{label}
        </NavLink>
      ))}
    </nav>
  );
}

function AccountLinks({ base, onSignOut, onNavigate }: { base: string; onSignOut: () => void; onNavigate?: () => void }) {
  const { user } = useAuth();
  return (
    <div className="flex flex-col gap-1 border-t border-ink-800 pt-4">
      <div className="flex min-w-0 flex-col px-3 pb-2">
        <span className="truncate text-body font-medium text-white">{user?.name}</span>
        <span className="truncate text-caption text-ink-200"><span className="capitalize">{user?.role}</span> · {user?.email}</span>
      </div>
      <NavLink to={`${base}/profile`} onClick={onNavigate}
        className={({ isActive }) => cn("flex h-11 items-center gap-3 rounded-sm px-3 text-body font-medium no-underline transition-colors duration-150 [&_svg]:size-[18px]",
          isActive ? "bg-ink-700 text-white hover:text-white" : "text-ink-100 hover:bg-ink-800 hover:text-white")}>
        <UserRound />Profile
      </NavLink>
      <button type="button" onClick={onSignOut}
        className="flex h-11 items-center gap-3 rounded-sm border-0 bg-transparent px-3 text-left text-body font-medium text-ink-100 transition-colors duration-150 hover:bg-ink-800 hover:text-white [&_svg]:size-[18px]">
        <LogOut />Sign out
      </button>
    </div>
  );
}

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const items = user?.role === "teacher" ? TEACHER_NAV : STUDENT_NAV;
  const base = user?.role === "teacher" ? "/teacher" : "/student";

  useEffect(() => setMenuOpen(false), [location.pathname]);

  const signOut = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-25 lg:grid lg:grid-cols-[232px_minmax(0,1fr)]">
      <a href="#main" className="sr-only rounded-sm bg-white px-3 py-2 text-ink-700 focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50">
        Skip to content
      </a>

      {/* wide screens: sidebar */}
      <aside className="sticky top-0 hidden h-screen flex-col gap-8 overflow-y-auto bg-ink-900 px-4 py-6 lg:flex">
        <Link to={base} className="px-3 no-underline" aria-label={`${PRODUCT_NAME} home`}><Logo inverse /></Link>
        <div className="flex-1"><NavLinks items={items} /></div>
        <AccountLinks base={base} onSignOut={signOut} />
      </aside>

      {/* phones and tablets: top bar + stacked navigation */}
      <header className="sticky top-0 z-30 bg-ink-900 lg:hidden">
        <div className="flex h-14 items-center justify-between gap-4 px-4 sm:px-6">
          <Link to={base} className="no-underline" aria-label={`${PRODUCT_NAME} home`}><Logo inverse /></Link>
          <button type="button" onClick={() => setMenuOpen((o) => !o)} aria-expanded={menuOpen} aria-controls="mobile-nav"
            className="flex h-11 items-center gap-2 rounded-sm border-0 bg-transparent px-3 text-body font-medium text-white hover:bg-ink-800 [&_svg]:size-5">
            {menuOpen ? <X aria-hidden /> : <Menu aria-hidden />}{menuOpen ? "Close" : "Menu"}
          </button>
        </div>
        {menuOpen && (
          <div id="mobile-nav" className="flex flex-col gap-4 border-t border-ink-800 px-4 pb-4 pt-3 sm:px-6">
            <NavLinks items={items} onNavigate={() => setMenuOpen(false)} />
            <AccountLinks base={base} onSignOut={signOut} onNavigate={() => setMenuOpen(false)} />
          </div>
        )}
      </header>

      <main id="main" className="min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
