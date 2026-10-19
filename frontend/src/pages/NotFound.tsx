import { Link } from "react-router-dom";

import { Logo } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { homeFor, useAuth } from "@/lib/auth";
import { usePageTitle } from "@/lib/usePageTitle";

export function NotFoundPage() {
  usePageTitle("Page not found");
  const { user } = useAuth();
  return (
    <div className="grid min-h-screen place-items-center bg-slate-25 px-4">
      <div className="flex max-w-[520px] flex-col items-center gap-4 text-center">
        <Logo />
        <span className="eyebrow text-slate-500">Error 404</span>
        <h1 className="m-0 text-h1 font-semibold text-slate-900">This page does not exist</h1>
        <p className="m-0 text-body text-slate-600">The address may be mistyped, or the page may have moved. You may also not have access to it.</p>
        <Button asChild><Link to={user ? homeFor(user.role) : "/login"}>{user ? "Go to your dashboard" : "Go to sign in"}</Link></Button>
      </div>
    </div>
  );
}
