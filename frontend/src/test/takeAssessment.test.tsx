// Student answering: autosave reports "saved" only after the server confirms, shows save failures with a retry, and
// submission keeps its existing semantics (confirmation, then read-only). fetch is mocked.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { tokenStore } from "@/lib/api";
import { TakeAssessmentPage } from "@/pages/student/TakeAssessment";

vi.mock("@/components/editor/RichTextEditor", () => import("@/test/editorStub"));

const detail = {
  id: "a1", title: "NLP basics", subject: "NLP", instructions: "- Answer **every** question.", status: "published", deadline: null,
  deadline_passed: false, question_count: 1, total_marks: 4, teacher_name: "Prof. Iyer", my_status: "not_started", submission_id: null,
  submitted_at: null, can_edit: true, answers: [],
  questions: [{ id: "q1", order: 0, text: "Explain **tokenization**.", max_marks: 4 }],
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/student/assessments/a1"]}>
        <Routes><Route path="/student/assessments/:id" element={<TakeAssessmentPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => { tokenStore.set("token"); vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); tokenStore.set(null); });

describe("student answer page", () => {
  it("autosaves the formatted answer and reports saved only after the server confirms", async () => {
    const puts: unknown[] = [];
    let failNext = true;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/api/submissions/draft") && init?.method === "PUT") {
        puts.push(JSON.parse(String(init.body)));
        if (failNext) { failNext = false; return json(500, { detail: "The server could not save the draft." }); }
        return json(200, { id: "s1" });
      }
      if (url.includes("/api/submissions/submit")) return json(200, { id: "s1", status: "submitted" });
      if (url.includes("/api/assessments/a1")) return json(200, detail);
      return json(404, { detail: "unexpected" });
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();

    expect(await screen.findByText("tokenization")).toBeInTheDocument(); // the question is rendered as rich text
    const answer = screen.getByRole("textbox");
    await user.type(answer, "- Splits text into **tokens**");
    expect(screen.getByText("Your latest changes are not saved yet")).toBeInTheDocument();
    expect(screen.getByText("4 words")).toBeInTheDocument(); // "-" and "**" are not counted

    await act(async () => { vi.advanceTimersByTime(5_000); });
    expect(await screen.findByText(/Draft not saved: The server could not save the draft\./)).toBeInTheDocument();
    expect(screen.queryByText(/Draft saved at/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/Draft saved at/)).toBeInTheDocument();
    expect(puts).toHaveLength(2);
    expect(puts[1]).toEqual({ assessment_id: "a1", answers: [{ question_id: "q1", text: "- Splits text into **tokens**" }] });

    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(screen.getByText("Answers submitted")).toBeInTheDocument());
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
