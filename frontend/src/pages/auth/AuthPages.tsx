import { CircleCheck } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Logo } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Alert, Field, Input, RadioCards } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import { PRODUCT_NAME } from "@/lib/brand";
import type { Role } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn, firstName } from "@/lib/utils";
import { EMAIL_RE, validatePassword } from "@/lib/validation";

const POINTS = [
  "Suggested marks always come with the evidence and the rubric lines behind them.",
  "Teachers review, adjust and publish. Nothing reaches students before that.",
  "Students see what they did well first, then the one thing to add.",
];

function AuthLayout({ mode, title, children }: { mode: "login" | "register"; title: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen bg-slate-25 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="flex flex-col gap-8 bg-ink-900 px-4 py-8 text-white sm:px-10 lg:justify-between lg:px-16 lg:py-12">
        <Logo inverse />
        <div className="hidden max-w-[460px] flex-col gap-6 lg:flex">
          <p className="m-0 text-h2 font-semibold">Evaluate descriptive answers with the reasoning in view.</p>
          <ul className="m-0 flex list-none flex-col gap-4 p-0">
            {POINTS.map((p) => (
              <li key={p} className="flex gap-3 text-body text-ink-100"><CircleCheck className="mt-0.5 size-5 text-ink-300" aria-hidden />{p}</li>
            ))}
          </ul>
        </div>
        <p className="m-0 hidden text-caption text-ink-200 lg:block">{PRODUCT_NAME} · for teachers and students</p>
      </aside>
      <main className="flex items-start justify-center px-4 py-10 sm:px-6 lg:items-center lg:py-12">
        <div className="flex w-full max-w-[420px] flex-col gap-6">
          <h1 className="m-0 text-h2 font-semibold text-slate-900">{title}</h1>
          <nav aria-label="Account" className="grid grid-cols-2 gap-1 rounded-[10px] bg-slate-50 p-1">
            {([["login", "/login", "Sign in"], ["register", "/register", "Create account"]] as const).map(([m, to, label]) => (
              <Link key={m} to={to} aria-current={mode === m ? "page" : undefined}
                className={cn("flex h-9 items-center justify-center rounded-sm text-control-sm font-medium no-underline transition-colors duration-150",
                  mode === m ? "bg-white text-ink-900 shadow-e1 hover:text-ink-900" : "text-slate-600 hover:text-slate-900")}>
                {label}
              </Link>
            ))}
          </nav>
          {children}
        </div>
      </main>
    </div>
  );
}

function PasswordInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input {...props} type={show ? "text" : "password"} className="pr-20" />
      <Button variant="tertiary" size="sm" className="absolute inset-y-1 right-1 h-auto" onClick={() => setShow((s) => !s)}
        aria-label={show ? "Hide password" : "Show password"}>
        {show ? "Hide" : "Show"}
      </Button>
    </div>
  );
}

export function LoginPage() {
  usePageTitle("Sign in");
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!EMAIL_RE.test(email.trim())) return setErrors({ email: "Enter a valid email address." });
    if (!password) return setErrors({ password: "Enter your password." });
    setErrors({});
    setBusy(true);
    try {
      const user = await login(email.trim(), password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && from.startsWith(homeFor(user.role)) ? from : homeFor(user.role), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout mode="login" title="Welcome back.">
      <form onSubmit={onSubmit} className="flex flex-col gap-5" noValidate>
        {error && <Alert tone="danger" title="Sign-in failed">{error}</Alert>}
        <Field id="email" label="Email" error={errors.email}>
          <Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)}
            onBlur={() => email && !EMAIL_RE.test(email.trim()) && setErrors((s) => ({ ...s, email: "Enter a valid email address." }))} />
        </Field>
        <Field id="password" label="Password" error={errors.password}>
          <PasswordInput autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={busy} loadingLabel="Signing in">Sign in</Button>
      </form>
    </AuthLayout>
  );
}

export function RegisterPage() {
  usePageTitle("Create account");
  const { register } = useAuth();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role>("student");
  const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "", invite_code: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const errs: Record<string, string> = {};
    if (form.name.trim().length < 2) errs.name = "Enter your full name.";
    if (!EMAIL_RE.test(form.email.trim())) errs.email = "Enter a valid email address.";
    const pw = validatePassword(form.password);
    if (pw) errs.password = pw;
    if (form.confirm !== form.password) errs.confirm = "The passwords do not match. Type the same password twice.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const user = await register({
        name: form.name.trim(), email: form.email.trim(), password: form.password, role,
        ...(role === "teacher" && form.invite_code ? { invite_code: form.invite_code } : {}),
      });
      toast.success(`Welcome to ${PRODUCT_NAME}, ${firstName(user.name)}.`);
      navigate(homeFor(user.role), { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.fieldErrors.length) {
        setErrors(Object.fromEntries(err.fieldErrors.map((f) => [f.field, f.message])));
      } else {
        setFormError(err instanceof ApiError ? err.message : "Could not create the account. Check your connection and try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout mode="register" title="Create your account">
      <form onSubmit={onSubmit} className="flex flex-col gap-5" noValidate>
        <RadioCards name="role" legend="I am a" value={role} onChange={setRole}
          options={[{ value: "student", label: "Student", description: "Answer assessments and see feedback" }, { value: "teacher", label: "Teacher", description: "Create assessments and review answers" }]} />
        {formError && <Alert tone="danger" title="The account was not created">{formError}</Alert>}
        <Field id="name" label="Full name" error={errors.name}>
          <Input autoComplete="name" value={form.name} onChange={set("name")} />
        </Field>
        <Field id="email" label="Email" error={errors.email}>
          <Input type="email" autoComplete="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field id="password" label="Password" error={errors.password} hint="At least 8 characters, with a letter and a number.">
          <PasswordInput autoComplete="new-password" value={form.password} onChange={set("password")} />
        </Field>
        <Field id="confirm" label="Confirm password" error={errors.confirm}>
          <PasswordInput autoComplete="new-password" value={form.confirm} onChange={set("confirm")} />
        </Field>
        {role === "teacher" && (
          <Field id="invite" label="Teacher invite code" optional error={errors.invite_code} hint="Only needed if your institution has set one.">
            <Input value={form.invite_code} onChange={set("invite_code")} autoComplete="off" />
          </Field>
        )}
        <Button type="submit" size="lg" className="w-full" loading={busy} loadingLabel="Creating account">Create account</Button>
      </form>
    </AuthLayout>
  );
}
