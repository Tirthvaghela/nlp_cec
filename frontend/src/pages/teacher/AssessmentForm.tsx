import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { BackLink, ErrorState, LoadingCards, PageBody, PageHeader } from "@/components/common";
import { RichTextEditor } from "@/components/editor/RichTextEditor";
import { Button } from "@/components/ui/button";
import { DateTimeField } from "@/components/ui/datetime";
import { Card, CardContent, Checkbox, Field, FieldError, Input, RadioCards } from "@/components/ui/primitives";
import { ApiError, api, errorMessage } from "@/lib/api";
import type { Assessment, AssessmentDetail, StudentBrief } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { fromLocalInput, toLocalInput } from "@/lib/utils";

export function AssessmentFormPage() {
  const { id } = useParams();
  const editing = Boolean(id);
  usePageTitle(editing ? "Edit assessment details" : "New assessment");
  const navigate = useNavigate();
  const qc = useQueryClient();

  const existing = useQuery({ queryKey: ["assessment", id], queryFn: () => api.get<AssessmentDetail>(`/api/assessments/${id}`), enabled: editing });
  const students = useQuery({ queryKey: ["students"], queryFn: () => api.get<StudentBrief[]>("/api/users/students") });

  const [form, setForm] = useState({ title: "", subject: "", instructions: "", deadline: "" });
  const [audience, setAudience] = useState<"all" | "selected">("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    const a = existing.data;
    if (!a) return;
    setForm({ title: a.title, subject: a.subject, instructions: a.instructions, deadline: toLocalInput(a.deadline) });
    setAudience(a.assigned_student_ids.length ? "selected" : "all");
    setSelected(a.assigned_student_ids);
  }, [existing.data]);

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: form.title.trim(),
        subject: form.subject.trim(),
        instructions: form.instructions.trim(),
        assigned_student_ids: audience === "all" ? [] : selected,
        ...(form.deadline ? { deadline: fromLocalInput(form.deadline) } : editing ? { clear_deadline: true } : {}),
      };
      return editing ? api.patch<Assessment>(`/api/assessments/${id}`, body) : api.post<Assessment>("/api/assessments", body);
    },
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: ["assessments"] });
      qc.invalidateQueries({ queryKey: ["assessment", a.id] });
      toast.success(editing ? "Details saved." : "Assessment created. Add the first question.");
      navigate(editing ? `/teacher/assessments/${a.id}` : `/teacher/assessments/${a.id}/questions/new`);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.fieldErrors.length) setErrors(Object.fromEntries(err.fieldErrors.map((f) => [f.field, f.message])));
      else toast.error(errorMessage(err));
    },
  });

  const validate = (only?: string) => {
    const errs: Record<string, string> = {};
    if (form.title.trim().length < 3) errs.title = "Give the assessment a title of at least 3 characters.";
    if (form.subject.trim().length < 2) errs.subject = "Enter the subject (at least 2 characters).";
    if (form.deadline && new Date(form.deadline) <= new Date()) errs.deadline = "Choose a deadline in the future.";
    if (form.instructions.trim().length > 5000) errs.instructions = "Shorten the instructions to 5,000 characters or fewer.";
    if (audience === "selected" && selected.length === 0) errs.students = "Select at least one student, or assign it to all students.";
    if (only) setErrors((e) => { const n = { ...e }; if (errs[only]) n[only] = errs[only]; else delete n[only]; return n; });
    else setErrors(errs);
    return errs;
  };

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!Object.keys(validate()).length) save.mutate();
  }

  if (editing && existing.isLoading) return <PageBody width="narrow"><LoadingCards /></PageBody>;
  if (editing && existing.isError) return <PageBody width="narrow"><ErrorState message={errorMessage(existing.error)} onRetry={() => existing.refetch()} /></PageBody>;

  const studentList = students.data ?? [];
  const allChecked = studentList.length > 0 && studentList.every((s) => selected.includes(s.id));

  return (
    <PageBody width="narrow">
      <PageHeader
        back={<BackLink to={editing ? `/teacher/assessments/${id}` : "/teacher/assessments"}>{editing ? existing.data?.title : "Assessments"}</BackLink>}
        title={editing ? "Edit details" : "New assessment"}
        description={editing ? "Questions, reference answers and rubrics are edited on the assessment page." : "Start with the details. You add questions, reference answers and rubrics next."} />
      <Card>
        <CardContent className="py-6">
          <form onSubmit={onSubmit} className="flex flex-col gap-6" noValidate>
            <Field id="title" label="Title" required error={errors.title}>
              <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} onBlur={() => validate("title")}
                placeholder="e.g. Unit 2: Text representation" maxLength={150} />
            </Field>
            <Field id="subject" label="Subject" required error={errors.subject}>
              <Input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} onBlur={() => validate("subject")}
                placeholder="e.g. Natural Language Processing" maxLength={100} />
            </Field>
            <Field id="deadline" label="Deadline" optional error={errors.deadline} hint="Submissions are refused after this time.">
              <DateTimeField value={form.deadline} onChange={(deadline) => setForm({ ...form, deadline })} />
            </Field>
            <Field id="instructions" label="Instructions to students" optional error={errors.instructions} hint="Shown before students start.">
              <RichTextEditor id="instructions" value={form.instructions} features="lists" minHeight={96} maxLength={5000}
                onChange={(instructions) => setForm((f) => ({ ...f, instructions }))} placeholder="e.g. Answer every question in full sentences." />
            </Field>

            <RadioCards name="audience" legend="Who can take this assessment?" value={audience} onChange={setAudience}
              options={[
                { value: "all", label: "All registered students" },
                { value: "selected", label: "Selected students only" },
              ]} />
            {audience === "selected" && (
              <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
                <legend className="mb-2 p-0 text-small font-medium text-slate-800">Students</legend>
                <div className="overflow-hidden rounded-md border border-slate-100 bg-white">
                  {students.isLoading ? <p className="m-0 p-4 text-body text-slate-600">Loading students</p> :
                    students.isError ? <p className="m-0 p-4 text-body text-danger">{errorMessage(students.error)}</p> :
                      studentList.length === 0 ? <p className="m-0 p-4 text-body text-slate-600">No students have registered yet.</p> : (
                        <>
                          <div className="border-b border-slate-100 bg-slate-50 px-4">
                            <Checkbox checked={allChecked} indeterminate={!allChecked && selected.length > 0}
                              onChange={(c) => setSelected(c ? studentList.map((s) => s.id) : [])} label={`Select all (${selected.length} of ${studentList.length} selected)`} />
                          </div>
                          <ul className="m-0 max-h-72 list-none overflow-y-auto p-0">
                            {studentList.map((s) => (
                              <li key={s.id} className="border-b border-slate-100 px-4 last:border-b-0">
                                <Checkbox checked={selected.includes(s.id)} label={s.name} helper={s.email}
                                  onChange={(c) => setSelected((cur) => c ? [...cur, s.id] : cur.filter((x) => x !== s.id))} />
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                </div>
                {errors.students && <FieldError>{errors.students}</FieldError>}
              </fieldset>
            )}

            <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-6 sm:flex-row sm:justify-end">
              <Button variant="secondary" onClick={() => navigate(-1)}>Cancel</Button>
              <Button type="submit" loading={save.isPending} loadingLabel="Saving">{editing ? "Save changes" : "Create assessment"}</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </PageBody>
  );
}
