// Sprint 6 (finding A1): in PILOT_MODE the backend refuses to save a per-question threshold override with
// 403 { code: "pilot_overrides_disabled" } (backend/app/routers/questions.py, _refuse_pilot_overrides).
// The editor must show that refusal, keep the teacher's unsaved edits and never report success or navigate away.
// fetch is mocked: no backend, database or scoring engine is involved.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { tokenStore } from "@/lib/api";
import { QuestionEditorPage } from "@/pages/teacher/QuestionEditor";

vi.mock("@/components/editor/RichTextEditor", () => import("@/test/editorStub"));

const REFUSAL = "Per-question threshold overrides are disabled in the classroom pilot: they are outside the frozen engine (faculty decision D5 is pending).";

const assessment = {
  id: "a1", title: "NLP basics", subject: "NLP", instructions: "", status: "draft", deadline: null, assigned_student_ids: [],
  question_count: 1, total_marks: 2, submission_counts: { draft: 0, submitted: 0, evaluated: 0, published: 0 },
  questions: [{
    id: "q1", assessment_id: "a1", order: 0, text: "Explain tokenization in NLP.", max_marks: 2, reference_answer: "",
    rubric: [{ id: "c1", label: "Definition", description: "Splits text into tokens", marks: 2, keywords: [] }],
    rubric_levels: { excellent: "", satisfactory: "", needs_improvement: "" }, settings: {}, rubric_version: 1,
    created_at: "2026-10-17T00:00:00Z", updated_at: "2026-10-17T00:00:00Z",
  }],
};

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/teacher/assessments/a1/questions/q1"]}>
        <Routes>
          <Route path="/teacher/assessments/:id/questions/:questionId" element={<QuestionEditorPage />} />
          <Route path="/teacher/assessments/:id" element={<p>assessment page</p>} />
        </Routes>
        <Toaster />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  tokenStore.set(null);
});

describe("question editor and the pilot override refusal", () => {
  it("shows the server's refusal, keeps unsaved edits and does not report success", async () => {
    const patches: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/api/assessments/a1")) return jsonResponse(200, assessment);
      if (url.includes("/api/submissions")) return jsonResponse(200, { items: [], total: 0, skip: 0, limit: 200 });
      if (url.includes("/api/questions/q1") && init?.method === "PATCH") {
        patches.push(JSON.parse(String(init.body)));
        return jsonResponse(403, { detail: REFUSAL, code: "pilot_overrides_disabled" });
      }
      return jsonResponse(404, { detail: "unexpected request" });
    });
    tokenStore.set("token");
    const user = userEvent.setup();
    renderEditor();

    const text = await screen.findByRole("textbox", { name: "Question text" });
    await waitFor(() => expect(text).toHaveValue("Explain tokenization in NLP."));
    await user.clear(text);
    await user.type(text, "Explain tokenization and why it matters.");
    await user.click(screen.getByRole("button", { name: "Advanced: matching thresholds" }));
    await user.type(screen.getByLabelText("Match threshold"), "0.7");
    await user.type(screen.getByLabelText("Partial threshold"), "0.6");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText(REFUSAL)).toBeInTheDocument();
    expect(patches).toHaveLength(1);
    expect(patches[0]).toMatchObject({ settings: { match_threshold: 0.7, partial_threshold: 0.6 } });
    // nothing claims success, the page stays, and every unsaved edit is still there
    expect(screen.queryByText(/Question \d+ saved|Saved as rubric version/)).not.toBeInTheDocument();
    expect(screen.queryByText("assessment page")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Question text" })).toHaveValue("Explain tokenization and why it matters.");
    expect(screen.getByLabelText("Match threshold")).toHaveValue("0.7");
    expect(screen.getByLabelText("Partial threshold")).toHaveValue("0.6");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  });
});
