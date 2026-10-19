// Editable rubric: one structured row per criterion (name, what a good answer says, marks, optional keywords), with
// reorder and remove controls and a live total. The rubric is teacher-owned once it exists: there is deliberately no
// way to regenerate it here.
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { FieldError, InputWithSuffix, Input, Label, StatusBadge, Textarea } from "@/components/ui/primitives";
import { conceptId } from "@/lib/status";
import { cn, fmtMarks } from "@/lib/utils";
import { MAX_CRITERIA, newRow, rubricTotal, type RubricErrors, type RubricRow } from "@/pages/teacher/question/rubric";

export function RubricTotal({ rows, maxMarks }: { rows: RubricRow[]; maxMarks: number }) {
  const total = rubricTotal(rows);
  const ok = rows.length > 0 && Number.isFinite(maxMarks) && Math.abs(total - maxMarks) < 1e-9;
  return (
    <span className="flex flex-wrap items-center gap-2" aria-live="polite">
      <span className="tabular text-small font-medium text-slate-800">
        Total rubric marks: {fmtMarks(total)} / {Number.isFinite(maxMarks) ? fmtMarks(maxMarks) : "—"}
      </span>
      {rows.length > 0 && <StatusBadge tone={ok ? "success" : "warning"}>{ok ? "Matches maximum" : "Does not match"}</StatusBadge>}
    </span>
  );
}

export function RubricEditor({ rows, onChange, errors, showErrors, disabled }: {
  rows: RubricRow[];
  onChange: (rows: RubricRow[]) => void;
  errors: RubricErrors;
  showErrors: boolean;
  disabled?: boolean;
}) {
  const update = (i: number, patch: Partial<RubricRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const move = (i: number, d: -1 | 1) => {
    const c = [...rows];
    [c[i], c[i + d]] = [c[i + d], c[i]];
    onChange(c);
  };
  const remove = (i: number) => {
    const removed = rows[i];
    const before = rows;
    onChange(rows.filter((_, j) => j !== i));
    if (removed.label.trim() || removed.description.trim()) {
      toast(`Criterion ${conceptId(i + 1)} removed`, { action: { label: "Undo", onClick: () => onChange(before) } });
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <ol className="m-0 flex list-none flex-col gap-3 p-0">
        {rows.map((r, i) => {
          const e = showErrors ? errors.rows[r.key] ?? {} : {};
          const base = `crit-${r.key}`;
          return (
            <li key={r.key}>
              <fieldset className="m-0 flex min-w-0 flex-col gap-3 rounded-md border border-slate-100 bg-white p-4" disabled={disabled}>
                <legend className="sr-only">Criterion {i + 1}</legend>
                <div className="flex items-center justify-between gap-2">
                  <span className="tabular text-small font-semibold text-slate-500" aria-hidden>{conceptId(i + 1)}</span>
                  <div className="flex items-center gap-1">
                    <Button variant="tertiary" size="icon-sm" disabled={i === 0} onClick={() => move(i, -1)}
                      aria-label={`Move criterion ${i + 1} up`} data-tooltip="Move up"><ArrowUp aria-hidden /></Button>
                    <Button variant="tertiary" size="icon-sm" disabled={i === rows.length - 1} onClick={() => move(i, 1)}
                      aria-label={`Move criterion ${i + 1} down`} data-tooltip="Move down"><ArrowDown aria-hidden /></Button>
                    <Button variant="tertiary" size="icon-sm" className="text-danger hover:text-danger" onClick={() => remove(i)}
                      aria-label={`Remove criterion ${i + 1}`} data-tooltip="Remove criterion"><Trash2 aria-hidden /></Button>
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px]">
                  <div className="flex min-w-0 flex-col gap-[6px]">
                    <Label htmlFor={`${base}-label`}>Criterion name<span className="sr-only"> (criterion {i + 1})</span></Label>
                    <Input id={`${base}-label`} value={r.label} maxLength={120} placeholder="e.g. Definition of tokenization"
                      aria-invalid={e.label ? true : undefined}
                      aria-describedby={e.label ? `${base}-label-err` : undefined} onChange={(ev) => update(i, { label: ev.target.value })} />
                    {e.label && <FieldError id={`${base}-label-err`}>{e.label}</FieldError>}
                  </div>
                  <div className="flex min-w-0 flex-col gap-[6px]">
                    <Label htmlFor={`${base}-marks`}>Marks<span className="sr-only"> (criterion {i + 1})</span></Label>
                    <InputWithSuffix id={`${base}-marks`} suffix="marks" inputMode="decimal" value={r.marks}
                      aria-invalid={e.marks ? true : undefined}
                      aria-describedby={e.marks ? `${base}-marks-err` : undefined} onChange={(ev) => update(i, { marks: ev.target.value })} />
                    {e.marks && <FieldError id={`${base}-marks-err`}>{e.marks}</FieldError>}
                  </div>
                </div>
                <div className="flex min-w-0 flex-col gap-[6px]">
                  <Label htmlFor={`${base}-desc`}>What a good answer says<span className="sr-only"> (criterion {i + 1})</span></Label>
                  <Textarea id={`${base}-desc`} value={r.description} maxLength={600} rows={2} className="min-h-[72px]"
                    placeholder="e.g. Tokenization splits raw text into smaller units such as words or subwords."
                    aria-invalid={e.description ? true : undefined}
                    aria-describedby={`${base}-desc-help${e.description ? ` ${base}-desc-err` : ""}`}
                    onChange={(ev) => update(i, { description: ev.target.value })} />
                  {e.description && <FieldError id={`${base}-desc-err`}>{e.description}</FieldError>}
                  <p id={`${base}-desc-help`} className="m-0 text-caption text-slate-500">Each sentence of a student's answer is compared with this statement.</p>
                </div>
                <div className="flex min-w-0 flex-col gap-[6px]">
                  <Label htmlFor={`${base}-kw`}>Keywords or synonyms<span className="sr-only"> (criterion {i + 1})</span> <span className="font-normal text-slate-500">(optional)</span></Label>
                  <Input id={`${base}-kw`} value={r.keywords} placeholder="Comma-separated, e.g. tokens, word pieces"
                    onChange={(ev) => update(i, { keywords: ev.target.value })} />
                </div>
              </fieldset>
            </li>
          );
        })}
      </ol>
      {showErrors && errors.summary && <FieldError>{errors.summary}</FieldError>}
      <Button variant="tertiary" className={cn("self-start")} icon={<Plus aria-hidden />} disabled={disabled || rows.length >= MAX_CRITERIA}
        onClick={() => onChange([...rows, newRow()])}>
        Add criterion
      </Button>
    </div>
  );
}
