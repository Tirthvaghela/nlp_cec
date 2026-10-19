import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import App from "@/App";
import { ConfidenceBadge, Marks, SubmissionStatusBadge } from "@/components/common";
import { AnswerWithEvidence, FeedbackPanel } from "@/components/evaluation";
import { api, ApiError, tokenStore } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";
import type { StudentConcept } from "@/lib/types";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function wrap(ui: ReactNode, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  tokenStore.set(null);
});

describe("display components", () => {
  it("shows marks as earned / maximum", () => {
    render(<Marks earned={3.5} max={5} />);
    expect(screen.getByText("3.5")).toBeInTheDocument();
    expect(screen.getByText("/ 5")).toBeInTheDocument();
  });

  it("uses student-friendly wording for submission status", () => {
    render(<SubmissionStatusBadge status="evaluated" audience="student" />);
    expect(screen.getByText("Under teacher review")).toBeInTheDocument();
  });

  it("describes review confidence without claiming certainty", () => {
    render(<ConfidenceBadge confidence="low" />);
    expect(screen.getByText("Careful review needed")).toBeInTheDocument();
  });

  it("highlights evidence inside the original answer", () => {
    const answer = "Tokens are words. Cricket is fun.";
    const concepts: StudentConcept[] = [
      { label: "Definition", description: "d", level: "matched", awarded: 1, marks: 1, evidence: { text: "Tokens are words.", start: 0, end: 17 } },
      { label: "Other", description: "d", level: "missing", awarded: 0, marks: 1, evidence: null },
    ];
    const { container } = render(<AnswerWithEvidence answer={answer} concepts={concepts} />);
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0]).toHaveTextContent("Tokens are words.");
    expect(marks[0]).toHaveAttribute("title", "Evidence for: 1. Definition");
    expect(container.textContent).toContain("Cricket is fun.");
  });

  it("handles empty answers explicitly", () => {
    render(<AnswerWithEvidence answer="   " concepts={[]} />);
    expect(screen.getByText(/No answer was written/)).toBeInTheDocument();
  });

  it("renders only non-empty feedback sections", () => {
    render(<FeedbackPanel feedback={{ summary: "Suggested score 2/4.", strengths: ["Good definition"], partial: [], missing: ["X missing"], suggestions: [], text: "" }} />);
    expect(screen.getByText("What you did well")).toBeInTheDocument();
    expect(screen.getByText("Missing points")).toBeInTheDocument();
    expect(screen.queryByText("Needs more detail")).not.toBeInTheDocument();
  });
});

describe("API client", () => {
  it("turns error responses into ApiError with the server message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(409, { detail: "Already submitted.", code: "already_submitted" }));
    await expect(api.post("/api/submissions/submit", {})).rejects.toMatchObject({ status: 409, code: "already_submitted", message: "Already submitted." });
  });

  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await api.get("/api/health").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toMatch(/Cannot reach the server/);
  });

  it("sends the bearer token when signed in", async () => {
    tokenStore.set("abc");
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, { ok: true }));
    await api.get("/api/auth/me");
    const init = spy.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer abc");
  });
});

describe("routing and login", () => {
  it("redirects anonymous users from protected pages to the login page", async () => {
    wrap(<App />, "/teacher/assessments");
    // Sign-in page heading in the redesigned auth screen.
    expect(await screen.findByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
  });

  it("validates the login form before calling the API", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    wrap(<App />, "/login");
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address.");
    expect(spy).not.toHaveBeenCalled();
  });

  it("shows the server error for wrong credentials", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(401, { detail: "Incorrect email or password.", code: "invalid_credentials" }));
    wrap(<App />, "/login");
    await userEvent.type(screen.getByLabelText("Email"), "a@b.co");
    await userEvent.type(screen.getByLabelText("Password"), "Wrong1234");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
  });

  it("sends a student to the student area and blocks the teacher area", async () => {
    const user = { id: "u1", name: "Asha Rao", email: "a@b.co", role: "student", created_at: "2026-01-01T00:00:00Z" };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) return jsonResponse(200, user);
      if (url.includes("/api/assessments")) return jsonResponse(200, []);
      if (url.includes("/api/results/mine")) return jsonResponse(200, []);
      if (url.includes("/api/analytics/student")) return jsonResponse(200, { results: [], average_percentage: null, best_percentage: null, most_missed_concepts: [] });
      return jsonResponse(404, { detail: "nope" });
    });
    tokenStore.set("token");
    wrap(<App />, "/teacher");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Hello, Asha." })).toBeInTheDocument());
  });
});
