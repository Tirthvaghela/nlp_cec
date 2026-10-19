// The question-authoring workflow on the real page with mocked API responses: automatic reference-answer drafting,
// gating of the next actions, regeneration with confirmation, one-time rubric generation, rubric editing and saving.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { tokenStore } from "@/lib/api";
import { AssessmentEditorPage } from "@/pages/teacher/AssessmentEditor";

vi.mock("@/components/editor/RichTextEditor", () => import("@/test/editorStub"));

const QUESTION = "Explain tokenization in NLP and why it is important.";
const REFERENCE = "Tokenization splits text into tokens.\n\n- It is the first step of the pipeline.\n- Later steps work on tokens.";
const RUBRIC = [
  { label: "Definition", description: "Tokenization splits text into tokens.", marks: 2 },
  { label: "First step", description: "It is the first step of the NLP pipeline.", marks: 2 },
];

const baseAssessment = {
  id: "a1", title: "NLP basics", subject: "NLP", instructions: "", status: "draft", deadline: null, assigned_student_ids: [],
  question_count: 0, total_marks: 0, submission_counts: { draft: 0, submitted: 0, evaluated: 0, published: 0 },
  created_at: "2026-10-17T00:00:00Z", updated_at: "2026-10-17T00:00:00Z", published_at: null, questions: [] as unknown[],
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Handler = (url: string, init: RequestInit | undefined) => Response | Promise<Response> | undefined;

function mockApi(extra: Handler, assessment = baseAssessment) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const res = await extra(url, init);
    if (res) return res;
    if (url.includes("/api/assessments/a1")) return json(200, assessment);
    if (url.includes("/api/submissions")) return json(200, { items: [], total: 0, skip: 0, limit: 200 });
    return json(404, { detail: `unexpected request ${url}` });
  });
  return calls;
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/teacher/assessments/:id/questions/new" element={<AssessmentEditorPage />} />
          <Route path="/teacher/assessments/:id/questions/:questionId" element={<AssessmentEditorPage />} />
          <Route path="/teacher/assessments/:id" element={<AssessmentEditorPage />} />
        </Routes>
        <Toaster />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const slow = { timeout: 4000 };

beforeEach(() => tokenStore.set("token"));
afterEach(() => { vi.restoreAllMocks(); tokenStore.set(null); });

describe("question authoring workflow", { timeout: 20_000 }, () => {
  it("drafts the reference answer automatically, then unlocks rubric generation and saving", async () => {
    let releaseDraft: () => void = () => {};
    const calls = mockApi((url, init) => {
      if (url.endsWith("/api/generation/reference-answer")) return new Promise((r) => { releaseDraft = () => r(json(200, { reference_answer: REFERENCE, model: "m" })); });
      if (url.endsWith("/api/generation/rubric")) return json(200, { rubric: RUBRIC, source: "model", model: "m" });
      if (url.endsWith("/api/questions") && init?.method === "POST") {
        return json(201, { id: "q9", assessment_id: "a1", order: 0, ...JSON.parse(String(init.body)), rubric_version: 1, created_at: "", updated_at: "" });
      }
      return undefined;
    });
    const user = userEvent.setup();
    renderAt("/teacher/assessments/a1/questions/new");

    const save = await screen.findByRole("button", { name: "Save question" });
    const generateRubric = screen.getByRole("button", { name: "Generate rubric" });
    expect(save).toBeDisabled();
    expect(generateRubric).toBeDisabled();

    await user.type(screen.getByRole("textbox", { name: "Question text" }), QUESTION);
    expect(calls.filter((c) => c.url.includes("/generation/"))).toHaveLength(0); // debounced, not per keystroke
    expect((await screen.findAllByText("Generating reference answer", undefined, slow)).length).toBeGreaterThan(0); // inline status and button label
    expect(save).toBeDisabled();
    expect(calls.filter((c) => c.url.endsWith("/generation/reference-answer"))).toHaveLength(1);
    expect(calls.find((c) => c.url.endsWith("/generation/reference-answer"))!.body).toEqual({ question: QUESTION, max_marks: 4 });

    releaseDraft();
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Reference answer text" })).toHaveValue(REFERENCE));
    expect(screen.getByText("Drafted for this question")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Regenerate reference answer" })).toBeEnabled();
    expect(save).toBeEnabled();
    expect(generateRubric).toBeEnabled();

    await user.click(generateRubric);
    expect(await screen.findByDisplayValue("Definition")).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith("/generation/rubric"))!.body).toEqual({ question: QUESTION, max_marks: 4, reference_answer: REFERENCE });
    expect(screen.getByText("Total rubric marks: 4 / 4")).toBeInTheDocument();
    // generated once: no way to regenerate the rubric
    expect(screen.queryByRole("button", { name: /generate rubric/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/regenerate rubric/i)).not.toBeInTheDocument();

    // the rubric is the teacher's: edit, add, remove
    const name = screen.getByDisplayValue("Definition");
    await user.clear(name);
    await user.type(name, "Definition of tokenization");
    await user.click(screen.getByRole("button", { name: "Add criterion" }));
    expect(screen.getByText("Total rubric marks: 5 / 4")).toBeInTheDocument();
    expect(screen.getByText("Does not match")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove criterion 3" }));
    expect(screen.getByText("Total rubric marks: 4 / 4")).toBeInTheDocument();

    await user.click(save);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/api/questions") && c.method === "POST")).toBe(true));
    const body = calls.find((c) => c.url.endsWith("/api/questions") && c.method === "POST")!.body as Record<string, unknown>;
    expect(body).toMatchObject({
      assessment_id: "a1", text: QUESTION, max_marks: 4, reference_answer: REFERENCE,
      rubric: [{ label: "Definition of tokenization", marks: 2 }, { label: "First step", marks: 2 }],
    });
  });

  it("shows a recoverable error when drafting fails and lets the teacher write the answer", async () => {
    mockApi((url) => (url.endsWith("/api/generation/reference-answer")
      ? json(503, { detail: "A reference answer could not be drafted: Drafting is not set up on this server (GROQ_API_KEY is not configured). You can write it yourself.", code: "generation_unavailable" })
      : undefined));
    const user = userEvent.setup();
    renderAt("/teacher/assessments/a1/questions/new");
    await user.type(await screen.findByRole("textbox", { name: "Question text" }), QUESTION);
    expect(await screen.findByText("The reference answer could not be generated.", undefined, slow)).toBeInTheDocument();
    expect(screen.getByText(/not set up on this server/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save question" })).toBeDisabled();

    await user.type(screen.getByRole("textbox", { name: "Reference answer text" }), "Tokens are the units of text.");
    expect(screen.getByText("Edited by you")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save question" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Generate rubric" })).toBeEnabled();
  });

  it("asks before replacing an edited reference answer and keeps it if regeneration fails", async () => {
    let n = 0;
    mockApi((url) => {
      if (!url.endsWith("/api/generation/reference-answer")) return undefined;
      n += 1;
      return n === 1 ? json(200, { reference_answer: "First draft.", model: "m" }) : json(422, { detail: "The drafting service rejected the request.", code: "generation_failed" });
    });
    const user = userEvent.setup();
    renderAt("/teacher/assessments/a1/questions/new");
    await user.type(await screen.findByRole("textbox", { name: "Question text" }), QUESTION);
    const ref = await screen.findByRole("textbox", { name: "Reference answer text" });
    await waitFor(() => expect(ref).toHaveValue("First draft."), slow);
    await user.type(ref, " With my addition.");

    await user.click(screen.getByRole("button", { name: "Regenerate reference answer" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Replace your reference answer?" });
    await user.click(within(dialog).getByRole("button", { name: "Regenerate reference answer" }));
    expect(await screen.findByText("A new reference answer could not be generated. Your current answer is unchanged.")).toBeInTheDocument();
    expect(ref).toHaveValue("First draft. With my addition.");
    expect(n).toBe(2);
  });

  it("reports an invalid drafted rubric instead of silently changing it", async () => {
    mockApi((url) => {
      if (url.endsWith("/api/generation/reference-answer")) return json(200, { reference_answer: REFERENCE, model: "m" });
      if (url.endsWith("/api/generation/rubric")) return json(200, { rubric: [{ label: "A", description: "Something", marks: 3 }], source: "model", model: "m" });
      return undefined;
    });
    const user = userEvent.setup();
    renderAt("/teacher/assessments/a1/questions/new");
    await user.type(await screen.findByRole("textbox", { name: "Question text" }), QUESTION);
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate rubric" })).toBeEnabled(), slow);
    await user.click(screen.getByRole("button", { name: "Generate rubric" }));
    expect(await screen.findByText(/The drafted rubric is not valid: Rubric total does not match/)).toBeInTheDocument();
    expect(screen.queryByDisplayValue("A")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate rubric" })).toBeEnabled(); // nothing was generated, so it may be tried again
  });

  it("flags a stale reference answer on an existing question and blocks saving until resolved", async () => {
    const question = {
      id: "q1", assessment_id: "a1", order: 0, text: QUESTION, max_marks: 4, reference_answer: REFERENCE,
      rubric: RUBRIC.map((r, i) => ({ ...r, id: `c${i + 1}`, keywords: [] })), rubric_levels: { excellent: "", satisfactory: "", needs_improvement: "" },
      settings: {}, rubric_version: 1, created_at: "", updated_at: "2026-10-17T00:00:00Z",
    };
    const calls = mockApi(() => undefined, { ...baseAssessment, question_count: 1, total_marks: 4, questions: [question] });
    const user = userEvent.setup();
    renderAt("/teacher/assessments/a1/questions/q1");
    const text = await screen.findByRole("textbox", { name: "Question text" });
    await waitFor(() => expect(text).toHaveValue(QUESTION));
    expect(screen.getByText("Saved reference answer")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate rubric" })).not.toBeInTheDocument(); // existing rubric: never regenerated

    await user.type(text, " Give one example.");
    expect(screen.getByText("The reference answer may be outdated because the question changed.")).toBeInTheDocument();
    expect(screen.getByText("The rubric may be outdated because the question or reference answer changed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await new Promise((r) => setTimeout(r, 1500));
    expect(calls.some((c) => c.url.includes("/generation/"))).toBe(false); // a saved answer is never overwritten automatically

    await user.click(screen.getByRole("button", { name: "Keep this answer" }));
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();

    // max marks changes do not redistribute rubric marks
    const marks = screen.getByLabelText("Maximum marks");
    await user.clear(marks);
    await user.type(marks, "5");
    expect(screen.getByText("Total rubric marks: 4 / 5")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue("2")).toHaveLength(2);
  });
});
