import { LogOut } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { PageBody, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input, StatusBadge } from "@/components/ui/primitives";
import { api, errorMessage, tokenStore } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { User } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { fmtDate } from "@/lib/utils";
import { validatePassword } from "@/lib/validation";

export function ProfilePage() {
  usePageTitle("Profile");
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState(user?.name ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const [savingName, setSavingName] = useState(false);
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [pwErrors, setPwErrors] = useState<Record<string, string>>({});
  const [savingPw, setSavingPw] = useState(false);

  if (!user) return null;

  async function saveName(e: FormEvent) {
    e.preventDefault();
    if (name.trim().length < 2) return setNameError("Enter your name (at least 2 characters).");
    setNameError(null);
    setSavingName(true);
    try {
      setUser(await api.patch<User>("/api/auth/me", { name: name.trim() }));
      toast.success("Name updated.");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSavingName(false);
    }
  }

  async function savePassword(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!pw.current) errs.current = "Enter your current password.";
    const rule = validatePassword(pw.next);
    if (rule) errs.next = rule;
    if (pw.next !== pw.confirm) errs.confirm = "The passwords do not match. Type the same password twice.";
    setPwErrors(errs);
    if (Object.keys(errs).length) return;
    setSavingPw(true);
    try {
      // A password change signs out every other session; this device continues with the fresh token returned.
      const res = await api.post<{ access_token?: string }>("/api/auth/change-password", { current_password: pw.current, new_password: pw.next });
      if (res?.access_token) tokenStore.set(res.access_token);
      setPw({ current: "", next: "", confirm: "" });
      toast.success("Password changed. Your other devices were signed out.");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSavingPw(false);
    }
  }

  const signOut = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <PageBody width="narrow">
      <PageHeader title="Profile and account" />
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-1">
            <CardTitle>Account</CardTitle>
            <CardDescription>Member since {fmtDate(user.created_at, false)}</CardDescription>
          </div>
          <StatusBadge tone="ink" className="capitalize">{user.role}</StatusBadge>
        </CardHeader>
        <CardContent>
          <form onSubmit={saveName} className="flex flex-col gap-5" noValidate>
            <Field id="profile-name" label="Full name" error={nameError}>
              <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </Field>
            <Field id="profile-email" label="Email" hint="Your email and role were set at registration and cannot be changed here.">
              <Input value={user.email} readOnly />
            </Field>
            <Button type="submit" className="self-start" loading={savingName} loadingLabel="Saving" disabled={name.trim() === user.name}>Save changes</Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-1">
            <CardTitle>Change password</CardTitle>
            <CardDescription>Changing it signs out your other devices.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={savePassword} className="flex flex-col gap-5" noValidate>
            <Field id="pw-current" label="Current password" error={pwErrors.current}>
              <Input type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
            </Field>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field id="pw-next" label="New password" error={pwErrors.next} hint="At least 8 characters, with a letter and a number.">
                <Input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
              </Field>
              <Field id="pw-confirm" label="Confirm new password" error={pwErrors.confirm}>
                <Input type="password" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />
              </Field>
            </div>
            <Button type="submit" variant="secondary" className="self-start" loading={savingPw} loadingLabel="Updating password">Update password</Button>
          </form>
        </CardContent>
      </Card>
      <Button variant="secondary" className="self-start" icon={<LogOut aria-hidden />} onClick={signOut}>Sign out</Button>
    </PageBody>
  );
}
