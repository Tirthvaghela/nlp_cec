# Margin — Style Guide

**Version 1.0 · 18 Oct 2026**

The visual and interaction rules for Margin, the descriptive‑answer evaluation platform for teachers and students. Every screen, component and chart must be built from the tokens and patterns in this file. If something is not covered here, ask before inventing a new pattern.

> "Margin" is a working product name. Replace it everywhere when the final name is decided.

---

## 1. Principles

1. **Show the reasoning.** A suggested mark is never shown alone. It always sits next to its evidence: matched concepts, missing points and rubric lines.
2. **Calm by default.** Ink blue carries the structure. Any other colour must be earned: highlighter yellow for found concepts and student wins, status colours for state only.
3. **Feedback, not verdicts.** Students see what they did well first, then what to add. Language is specific and never scolding.
4. **Nothing browser‑default.** Every select, checkbox, radio, date, time, slider, switch and file input is a custom component from this guide. Native elements may sit underneath for accessibility but must never be visible.

---

## 2. Colour

### 2.1 Ink — primary

Used for actions, links, selection, focus and **all** data visualisation.

| Token | Hex | Use |
|---|---|---|
| `ink-50` | `#EEF2FB` | Selected row, hover on tertiary, info background |
| `ink-100` | `#DCE4F6` | Pressed tertiary, input focus halo, chips |
| `ink-200` | `#B9C8EC` | Secondary hover border |
| `ink-300` | `#8FA6DD` | Dropzone border, partial states |
| `ink-400` | `#6382CB` | Partial‑match underline |
| `ink-500` | `#3F62B5` | Focus ring, chart bars |
| **`ink-600`** | **`#2D4E9C`** | **Brand. Primary buttons, links, checked controls** |
| `ink-700` | `#233F80` | Primary hover, secondary text, nav active |
| `ink-800` | `#1B3164` | Primary pressed, heatmap top step |
| `ink-900` | `#13234A` | Headings, sidebar, student feedback card |

### 2.2 Highlighter — accent

Used **only** for: concepts found in a student answer, student encouragement (retry, practise, streaks) and positive progress badges.

| Token | Hex | Use |
|---|---|---|
| `hl-100` | `#FDF3D6` | Concept highlight background, streak panel |
| `hl-300` | `#F8D172` | Highlight button fill, chip border |
| `hl-500` | `#E9A818` | Highlight underline, streak blocks |
| `hl-700` | `#8A5B00` | Text on highlighter backgrounds (use `#6B4700` for small text) |

### 2.3 Slate — neutrals

| Token | Hex | Use |
|---|---|---|
| `slate-0` | `#FFFFFF` | Cards, inputs |
| `slate-25` | `#F8F9FB` | Page background |
| `slate-50` | `#F1F3F7` | Table headers, add‑ons, hover rows |
| `slate-100` | `#E5E8EF` | Dividers, card borders, empty bar track |
| `slate-200` | `#D3D8E2` | Input and secondary button borders |
| `slate-300` | `#B4BCCB` | Unchecked control borders, axes |
| `slate-400` | `#8A93A6` | Placeholder, disabled text |
| `slate-500` | `#646E83` | Captions, helper text (minimum for readable text) |
| `slate-600` | `#4A5368` | Secondary body text |
| `slate-800` | `#2A3142` | Labels, strong body |
| `slate-900` | `#141824` | Primary text, tooltips, toasts |

### 2.4 Status

Status colours mean state. Always pair them with an icon and a text label, never colour alone.

| State | Foreground | Background | Use |
|---|---|---|---|
| Success | `#1F7A4D` | `#E4F3EB` | Published, accepted, high confidence |
| Warning | `#B4570A` (text `#8F4508`) | `#FCEEDF` | Needs review, low confidence |
| Danger | `#B42335` | `#FBE6E8` | Errors, late, missing key points, destructive |
| Info | `ink-600` | `ink-50` | Running, neutral notices |

### 2.5 Contrast

| Pair | Ratio |
|---|---|
| `slate-900` on white | 17.9 : 1 |
| `slate-600` on white | 7.9 : 1 |
| `slate-500` on white | 5.0 : 1, the lowest allowed for text |
| White on `ink-600` | passes AA |
| `ink-900` on `hl-300` | passes AA |

Body text needs at least 4.5 : 1, and text 24px or larger needs at least 3 : 1. Never put `slate-400` or lighter on white for anything except placeholders and disabled states.

### 2.6 Colour — do / don't

- **Do** use Ink for anything the user can click or select.
- **Do** keep highlighter yellow on student‑facing screens and concept highlights.
- **Don't** use gradients as backgrounds or decoration.
- **Don't** introduce new hues (purple, teal, pink and so on) for categories or decoration.
- **Don't** use status green or red to mean "good" or "bad" in charts. Charts use Ink shades only (see §9).
- **Don't** use black (`#000`) shadows. Shadows are tinted with Ink 900.

### 2.7 CSS tokens

```css
:root {
  /* Ink */
  --ink-50:#EEF2FB; --ink-100:#DCE4F6; --ink-200:#B9C8EC; --ink-300:#8FA6DD;
  --ink-400:#6382CB; --ink-500:#3F62B5; --ink-600:#2D4E9C; --ink-700:#233F80;
  --ink-800:#1B3164; --ink-900:#13234A;
  /* Highlighter */
  --hl-100:#FDF3D6; --hl-300:#F8D172; --hl-500:#E9A818; --hl-700:#8A5B00;
  /* Slate */
  --slate-0:#FFFFFF; --slate-25:#F8F9FB; --slate-50:#F1F3F7; --slate-100:#E5E8EF;
  --slate-200:#D3D8E2; --slate-300:#B4BCCB; --slate-400:#8A93A6; --slate-500:#646E83;
  --slate-600:#4A5368; --slate-800:#2A3142; --slate-900:#141824;
  /* Status */
  --success:#1F7A4D; --success-bg:#E4F3EB;
  --warning:#B4570A; --warning-text:#8F4508; --warning-bg:#FCEEDF;
  --danger:#B42335;  --danger-bg:#FBE6E8;
  /* Semantic aliases */
  --bg-page:var(--slate-25); --bg-surface:var(--slate-0);
  --text-primary:var(--slate-900); --text-secondary:var(--slate-600); --text-muted:var(--slate-500);
  --border:var(--slate-100); --border-control:var(--slate-200);
  --brand:var(--ink-600); --brand-hover:var(--ink-700); --brand-pressed:var(--ink-800);
}
```

---

## 3. Typography

**One family: IBM Plex Sans** (Google Fonts, weights 400 / 500 / 600). No serif and no monospace fonts anywhere in the product.

```html
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
```

```css
font-family: 'IBM Plex Sans', 'Helvetica Neue', system-ui, sans-serif;
```

### 3.1 Type scale

| Style | Size / line height | Weight | Letter spacing | Use |
|---|---|---|---|---|
| Display | 48 / 56 | 600 | −0.02em | Page hero, style guide titles |
| Heading 1 | 36 / 44 | 600 | −0.01em | Page title |
| Heading 2 | 28 / 36 | 600 | 0 | Section title |
| Heading 3 | 22 / 30 | 600 | 0 | Card group title |
| Heading 4 | 18 / 26 | 600 | 0 | Card title, criterion name |
| Feedback | 18 / 30 | 400 | 0 | Student feedback, annotated answers |
| Body large | 17 / 28 | 400 | 0 | Intros, long answer input |
| Body | 15 / 24 | 400 | 0 | Default text |
| Small / label | 13 / 20 | 500 | 0 | Field labels, meta |
| Caption | 12 / 16 | 400 | 0 | Helper text, axis notes |
| Overline | 12 / 16 | 600 | +0.08em, UPPERCASE | Section eyebrows, table headers |
| Score | 28 / 36 (or 44 / 52 hero) | 500 | 0, tabular | Marks, KPIs |

### 3.2 Numbers

Marks, scores, counts, hex codes, percentages and times use **tabular figures** so they line up in columns:

```css
font-variant-numeric: tabular-nums;
```

Show the maximum in a lighter colour: `6.0` in `ink-900`, ` / 8` in `slate-400`.

### 3.3 Typography — do / don't

- **Do** use sentence case for headings, buttons and labels ("Publish marks", not "Publish Marks").
- **Do** use `text-wrap: balance` on headings and `text-wrap: pretty` on paragraphs.
- **Do** keep line length between 60 and 80 characters for reading text.
- **Don't** use any serif, monospace or decorative font.
- **Don't** use Inter, Roboto or Arial as the primary face.
- **Don't** use weights below 400 or above 600.
- **Don't** use all caps except for the Overline style.
- **Don't** set body text smaller than 13px, or helper text smaller than 12px.

---

## 4. Spacing, layout and shape

### 4.1 Spacing scale (4‑point grid)

| Token | px | Typical use |
|---|---|---|
| `space-1` | 4 | Icon to text in chips |
| `space-2` | 8 | Gap between buttons in a toolbar, icon to label |
| `space-3` | 12 | Gap between buttons in a footer, list rows |
| `space-4` | 16 | Card grid gap, field groups |
| `space-5` | 24 | Section gap inside a card, card grid gap on desktop |
| `space-6` | 32 | Card padding (large) |
| `space-7` | 48 | Between page sections (compact) |
| `space-8` | 64 | Between page sections |
| `space-9` | 96 | Page side padding on wide screens |

Use only these values. Lay out sibling elements with flex or grid and `gap`, not with margins on each element.

### 4.2 Grid

- Content max width **1200px**, a 12‑column grid with **24px** gutters.
- Page padding: 40px on desktop, 24px on tablet, **16px on phone**.
- Sidebar navigation is 232px wide and stacks above the content on phones.
- Card grids use `repeat(auto-fit, minmax(min(<min>px, 100%), 1fr))` so they drop to one column on a phone.

### 4.3 Radius

| Token | px | Use |
|---|---|---|
| `radius-xs` | 4 | Tags, status badges, heatmap cells |
| `radius-sm` | 8 | Buttons, inputs, menu items |
| `radius-md` | 12 | Cards, dropdown panels, calendars |
| `radius-lg` | 16 | Dialogs, feature cards |
| `radius-full` | 999 | Chips, switches, avatars, progress bars |

Checkboxes use 5px.

### 4.4 Control heights

| Size | Height | Horizontal padding | Font | Use |
|---|---|---|---|---|
| Small | 36px | 12px | 14 / 500 | Dense tables, inline actions |
| **Medium** | **44px** | **18px** | **15 / 500** | **Default everywhere** |
| Large | 52px | 22px | 16 / 500 | Student mobile, main call to action |

Buttons, inputs, selects and date and time triggers in the same row must share one height. Touch targets are never smaller than 44 × 44px on student screens.

### 4.5 Elevation

| Level | Shadow | Use |
|---|---|---|
| Flat | `1px solid slate-100` border, no shadow | Page sections, cards |
| e1 Raised | `0 1px 2px rgba(19,35,74,.06), 0 1px 3px rgba(19,35,74,.08)` | Segmented control thumb, hover cards |
| e2 Overlay | `0 2px 4px rgba(19,35,74,.06), 0 8px 20px rgba(19,35,74,.10)` | Dropdowns, calendars, time pickers, menus |
| e3 Modal | `0 4px 8px rgba(19,35,74,.08), 0 24px 48px rgba(19,35,74,.16)` | Dialogs, drawers, toasts |

Cards are flat by default. Do not add shadows to every card.

### 4.6 Focus

- **Buttons and clickable items:** `box-shadow: 0 0 0 2px #FFFFFF, 0 0 0 4px var(--ink-500)`.
- **Inputs:** border `ink-600` plus `box-shadow: 0 0 0 3px var(--ink-100)`.
- **Error inputs:** border `danger` plus a `danger-bg` halo.
- Show focus on keyboard focus (`:focus-visible`) only. Never remove focus without replacing it.

---

## 5. Icons

- 24px grid, **1.75px stroke**, round caps and joins, no fill.
- 20px inside medium controls, 16px inside small controls, 18px in menus and navigation.
- Icons inherit `currentColor` from their text.
- Every icon‑only button has an `aria-label` and a tooltip.
- **Don't** use emoji as icons, filled icon sets mixed with outline ones, or coloured icons outside status messages.

---

## 6. Buttons

### 6.1 Variants

| Variant | Default | Hover | Pressed | Text | When to use |
|---|---|---|---|---|---|
| **Primary** | `ink-600` fill | `ink-700` | `ink-800` + inset shadow | White | The one main action in a view |
| **Secondary** | White, `slate-200` border | `ink-50` fill, `ink-200` border | `ink-100` fill, `ink-300` border | `ink-700` | Alternatives next to primary |
| **Tertiary** | Transparent | `ink-50` | `ink-100` | `ink-600` | Toolbars, low‑emphasis actions |
| **Highlight** | `hl-300` fill, `#F2C24E` border | `#F2C24E` | `hl-500` | `ink-900`, weight 600 | Student screens only: retry, practise, view progress |
| **Destructive** | `danger` fill | `#951B2B` | `#7A1623` | White | Delete, discard marks, always with confirmation |

**Disabled** (all filled variants): `slate-100` fill, `slate-400` text, `cursor: not-allowed`. Secondary and tertiary disabled use `slate-300` text.

**Loading:** keep the button's width, replace the label with a 16px spinner plus a present‑tense label ("Evaluating"), and set `aria-busy="true"`.

### 6.2 Anatomy

- Radius 8px (10px for Large).
- Icon to label gap 8px. A leading icon reduces left padding by 4px.
- Icon buttons are square: 36, 44 or 52px.
- A split button is primary plus a 40px chevron segment separated by a 1px `ink-400` line.
- Text links are underlined, offset 3px, 1px thick, `ink-600`.

### 6.3 Buttons — do / don't

- **Do** write labels as verbs that say what happens: "Evaluate answers", "Publish marks", "Accept 6.0".
- **Do** put the primary button on the right of dialog footers with secondary to its left, 12px apart.
- **Do** use full‑width Large buttons for mobile and dialog actions.
- **Don't** place two primary buttons side by side.
- **Don't** use generic labels such as "Submit", "OK", "Click here" or "Yes".
- **Don't** use Destructive for "Cancel".
- **Don't** use the Highlight variant on teacher screens.

---

## 7. Form inputs

Labels always sit **above** the field and stay visible. Placeholders are examples, never labels.

### 7.1 Text field

| Property | Value |
|---|---|
| Height | 44px |
| Padding | 0 14px (42px left with a leading icon) |
| Border | 1px `slate-200`, radius 8px |
| Background | White |
| Text | 15px `slate-900` |
| Placeholder | `slate-400` |
| Label | 13 / 500, `slate-800`, 6px above the field |
| Helper | 12 / 16, `slate-500`, 6px below the field |

**States**

| State | Treatment |
|---|---|
| Default | `slate-200` border |
| Focus | `ink-600` border + 3px `ink-100` halo |
| Filled | Same as default |
| Error | `danger` border + `danger-bg` halo; message below in `danger` with an icon, telling the user how to fix it ("Enter a value between 1 and 100.") |
| Success | `success` border + check icon on the right; message in `success` |
| Disabled | `slate-50` fill, `slate-100` border, `slate-400` text and label |

**Variants:** leading icon (search), keyboard shortcut hint on the right (`/` in a 22px bordered key), suffix add‑on (`slate-50` block with a left border, for units like %), stepper (−/+ 44px buttons either side of a centred tabular value).

### 7.2 Long answer (textarea)

- Padding 14px 16px, 17 / 28 text, resizable vertically only.
- Show the question and its marks in the label row.
- Below the field: autosave status on the left; word‑count bar (120px, 6px, `ink-500` fill) and "N / 200 words" on the right.

### 7.3 Checkbox

- 20px box, radius 5px, 1.5px `slate-300` border.
- Checked: `ink-600` fill and border, white 3px‑stroke check.
- Indeterminate: `ink-600` fill with a white bar.
- Disabled: `slate-50` fill, `slate-100` border.
- The label sits 12px to the right, with an optional 12px helper line below.
- Group checkboxes inside a `<fieldset>` with a `<legend>`.

### 7.4 Radio and radio cards

- 20px circle, 1.5px `slate-300` border; selected uses an `ink-600` ring and a 10px `ink-600` dot.
- **Radio cards** (preferred for settings with explanations): 14 × 16px padding, radius 10px, `slate-100` border; selected uses an `ink-600` border and `ink-50` fill.
- Use radios for 2 to 5 mutually exclusive options. Use a select for more than 5.

### 7.5 Switch

- Track 44 × 26px, full radius, 3px padding; thumb 20px white with an e1 shadow.
- Off: `slate-300` track. On: `ink-600` track, thumb right. 150ms transition.
- Use `role="switch"` with `aria-checked`.
- Use a switch only for settings that apply immediately. Inside a form that has a Save button, use a checkbox.

### 7.6 Slider

- 6px `slate-100` track, `ink-600` fill, 22px white thumb with a 2px `ink-600` border.
- Always show the current value next to the label (tabular), and the end labels below ("0.50 lenient", "0.95 strict").
- Use a real `<input type="range">` underneath for keyboard and screen reader support.

### 7.7 File upload

- Dropzone: 1.5px dashed `ink-300` border, `ink-50` fill, radius 12px, centred 44px icon circle.
- Copy states the action, the accepted types and the size limit.
- Upload rows: file icon tile, name, tabular percentage, a 4px progress bar and a cancel icon button.

### 7.8 Forms — do / don't

- **Do** validate on blur, not on every keystroke.
- **Do** keep one column for forms; two columns only for short, related pairs (start and end date).
- **Don't** show any native browser control: select, date, time, checkbox, radio, range or file.
- **Don't** use a placeholder as the only label.
- **Don't** mark optional fields with an asterisk. Mark required ones, or label optional ones "(optional)".

---

## 8. Dropdowns, date and time

All panels share: white background, 1px `slate-100` border, **radius 12px**, **e2 shadow**, 6px inner padding, **6px offset** from the trigger. Triggers look exactly like a text field (44px, radius 8px) with a 16 to 18px chevron or icon. An open trigger shows the focus style.

### 8.1 Select (single)

- Option rows 40px, radius 8px, 10px horizontal padding.
- Hover: `slate-50`. Selected: `ink-50` fill, `ink-900` text, weight 600, `ink-600` check on the right.
- Optional group label in Overline style (11px).
- Optional meta value on the right (counts), tabular, `slate-500`.
- The chevron rotates 180° when open.
- Keyboard: ↑ ↓ to move, Enter to pick, Esc to close, type to jump.

### 8.2 Multi‑select

- Selected values appear as chips inside the field: 28px, full radius, `ink-50` fill, `ink-800` text, 24px remove button.
- Options show a checkbox on the left.
- The panel stays open while picking and closes on Esc or outside click.

### 8.3 Date picker

- The trigger shows a calendar icon and a formatted date: **"Sat, 24 Oct 2026"** (weekday, day, short month, year).
- Header: previous and next 36px icon buttons, month and year centred (18 / 600).
- Weekday row starts on **Monday**, 12 / 600 `slate-500`.
- Day cells 40px, radius 8px. Days from other months use `slate-300`.
- Today: 1px `ink-300` border, weight 600. Selected: `ink-600` fill, white text.
- Footer: "Today" tertiary button on the left, "Set date" primary small on the right.
- Each day button carries a full `aria-label` ("Saturday 24 October 2026").

### 8.4 Time picker

- The trigger shows a clock icon, the time in tabular figures (**"11:30 PM"**) and the timezone (IST) on the right.
- Panel: three columns, Hour (01 to 12), Minute (in 5‑minute steps), AM/PM, each scrollable to 232px.
- Selected value: `ink-600` fill, white, weight 600.

### 8.5 Date range

- Presets first ("Last 7 days", "Last 30 days", "This term", "Academic year"), each with its span on the right.
- "Custom range…" sits after a divider and opens a two‑month calendar. The range between the start and end dates uses an `ink-50` fill.

### 8.6 Action menu

- Rows 40px with an 18px leading icon and an optional shortcut on the right.
- Destructive items go **last**, after a divider, in `danger` text.
- Align the menu to the trigger edge nearest the centre of the viewport.

---

## 9. Charts and infographics

**Charts use shades of Ink only.** No multicolour palettes, no status colours, no highlighter in charts.

### 9.1 Palette

| Job | Colours |
|---|---|
| Single series (bars, lines, dots) | `ink-500` default, `ink-800` or `ink-900` on hover |
| Line charts | `ink-600` 2px line, optional `ink-50` area fill |
| Sequential / heatmap (low → high) | `ink-50` `ink-100` `ink-200` `ink-300` `ink-400` `ink-500` `ink-600` `ink-800` |
| Two series compared | `ink-300` vs `ink-700` (they must differ clearly in lightness) |
| Gridlines | `slate-100`, 1px |
| Axes and baselines | `slate-300`, 1px |
| Reference lines (e.g. perfect agreement) | `slate-300`, dashed 4/4 |
| Empty / remaining track | `slate-100` |

On heatmap steps from `ink-400` upward, put white text in the cell. Below that, use `ink-900`.

### 9.2 Marks

- Bars: rounded 4px top corners anchored to the baseline, a 2px gap between bars.
- Lines: 2px, round joins.
- Dots: at least 8px with a 2px white ring; the hit area is at least 20px.
- Keep at most 3 or 4 gridlines.

### 9.3 Labels and interaction

- Every chart has a title (16 / 600), a one‑line caption explaining what is measured, and axis labels in 11px tabular `slate-500`.
- Text is always in text colours (`slate-500` to `slate-900`), never in the series colour.
- Hover or keyboard focus on any mark shows its exact value; the chart's header note updates to show it.
- Heatmaps always show a legend ramp with low and high labels.
- Every mark has an `aria-label` with its value.

### 9.4 Standard charts

| Question | Chart |
|---|---|
| How are marks spread? | Histogram, one bar per mark band |
| Does the system agree with the teacher? | Scatter: suggested mark (x) vs teacher mark (y), with a dashed diagonal |
| Which concepts are students missing? | Heatmap: criteria (rows) × questions (columns), % coverage |
| Is reliability improving? | Line: QWK or agreement per week |
| A single headline number | KPI tile, not a chart |

### 9.5 Charts — do / don't

- **Do** start bar axes at zero.
- **Don't** use pie or donut charts for more than 2 parts. A progress ring is allowed only for a single score.
- **Don't** use dual y‑axes.
- **Don't** add 3D effects, drop shadows or gradients to chart marks.
- **Don't** put a value label on every point. Label only what matters and let hover do the rest.

---

## 10. Evaluation components

### 10.1 Concept highlighting in answers

| Meaning | Treatment |
|---|---|
| Concept matched | `hl-100` background, 2px `hl-500` underline (`box-shadow: inset 0 -2px 0`), radius 3px |
| Partially matched | 2px dashed `ink-400` underline, offset 5px |
| Missing key point | Listed below the answer in a row with a 1.5px dashed `#E2A5AD` border, minus icon in `danger`, the rubric reference and the marks it is worth |

Always show the legend under the answer. Student answers are set in Feedback style (18 / 30).

### 10.2 Suggested mark card

- Overline "Suggested mark", score in 44 / 52 tabular weight 500 with the maximum in `slate-400`.
- A confidence badge in the top right: success for high, warning for low (below 0.6).
- Three evidence tiles on `slate-50`: Semantic match, Concepts (n of m), Confidence.
- Actions: Primary "Accept 6.0" and Secondary "Adjust mark", equal width.

### 10.3 Rubric breakdown

- One row per criterion: name on the left, `awarded / max` on the right, tabular.
- Below it an 8px bar: `ink-600` for awarded marks, `slate-100` for the rest, with a 2px gap between them.

### 10.4 Student feedback card

- `ink-900` background, white text, radius 16px.
- A progress ring (`hl-300` on `ink-700`) around the score.
- A one‑sentence summary that leads with a strength.
- Two blocks on `ink-800`: **"What you did well"** (heading in `hl-300`) and **"To reach 8 / 8"** (heading in white).
- One Highlight‑variant button for the next learning step ("Practise this concept").

### 10.5 Badges and tags

- **Status badge:** 24px, radius 4px, 12 / 600, a 6px dot plus a label. Published uses success, Evaluated uses ink, Needs review uses warning, Late uses danger, Draft uses slate.
- **Concept tags:** 28px, full radius, 13 / 500.
  - Found: `hl-100` fill, `hl-300` border.
  - Partial: white fill, dashed `ink-400` border.
  - Missing: white fill, dashed `#E2A5AD` border, `danger` text.

### 10.6 Alerts and toasts

- **Inline alert:** padding 14 × 16px, radius 10px, the status background with a 1px tinted border, a 20px icon, a bold title and one line of body text. **No coloured left‑border stripe.**
- Use `role="alert"` for warnings and errors and `role="status"` for everything else.
- **Toast:** `slate-900` background, white text, e3 shadow, bottom centre, auto‑dismiss after 5s, always with an Undo for reversible actions.
- **Tooltip:** `slate-900` background, 13 / 18 white text, radius 8px, max width 220px.

### 10.7 Progress

- **Linear:** 8px, full radius, `slate-100` track, `ink-600` fill, with a label and a tabular count above.
- **Stepped (test progress):** one 6px segment per question with 6px gaps. Done uses `ink-600`, current uses `ink-300`, upcoming uses `slate-100`.
- **Streak (students):** a `hl-100` panel with `hl-500` blocks and a dashed outline for the next week.

### 10.8 Tables

- Header row: `slate-50`, Overline style.
- Rows 56px (44px dense), separated by `slate-100` dividers. Selected or hovered rows use `ink-50`.
- Numbers are right‑aligned or centred and tabular. Show an empty value as "—".
- Wide tables scroll horizontally inside their card, never the page.

### 10.9 Tabs, segmented control, breadcrumb

- **Tabs:** 44px, 24px apart, a 2px `ink-600` underline on the active tab, active text `ink-900` 600, inactive `slate-600` 500. Counts go in an `ink-50` pill.
- **Segmented control:** `slate-50` track with 4px padding, radius 10px; the active segment is white with an e1 shadow. Use it for switching views of the same content.
- **Breadcrumb:** 13px `slate-600`, `/` separators in `slate-300`, the current page in `slate-900` 500.

---

## 11. Writing and voice

| Do | Don't |
|---|---|
| "6 answers need your review" | "Attention required!" |
| "Name the Calvin cycle to reach full marks." | "Incorrect. Missing information." |
| "Enter a value between 1 and 100." | "Invalid input." |
| "Marks published to 10-B" | "Success!" |
| "Evaluating 32 of 48 answers" | "Please wait…" |

- Feedback to students: strength first, then one specific next step. Address the student as "you".
- Never use exclamation marks in system messages.
- Use the student's or class's name instead of generic words where possible.
- Dates: "24 Oct 2026". Times: "11:30 PM IST". Marks: "6.0 / 8".
- **Don't** write filler or marketing copy, and don't use lorem ipsum in shipped screens. Missing facts become visible placeholders, like `[DUE DATE]`.

---

## 12. Accessibility checklist

- [ ] Text contrast is at least 4.5 : 1 (or 3 : 1 at 24px+).
- [ ] Every interactive element is a real `<button>`, `<a href>` or `<input>` with a `<label>`.
- [ ] Custom controls keep a native input underneath, or use the correct ARIA role (`listbox`, `option`, `switch`, `dialog`, `menu`).
- [ ] Icon‑only buttons have `aria-label`.
- [ ] Focus is visible on every interactive element.
- [ ] Status is never shown by colour alone: there is always an icon and a label.
- [ ] Chart marks have `aria-label` values and can be reached by keyboard.
- [ ] Touch targets are at least 44 × 44px on student screens.
- [ ] Layouts work at 360px wide with a 16px gutter and no horizontal page scroll.

---

## 13. Never use

- Browser‑default selects, date pickers, time pickers, checkboxes, radios, sliders or file inputs.
- Serif, monospace, script or display fonts.
- Gradient backgrounds, glassmorphism, glows or neon effects.
- Cards with a coloured left‑border accent stripe.
- Emoji in the interface.
- More than one primary button per view.
- Multicolour or rainbow charts, or status colours inside charts.
- Pure black (`#000`) text or shadows.
- Radii outside the scale (for example 6px or 20px on cards).
- Spacing values outside the 4‑point scale.
- Placeholder text used as a label.
- Vague, cheerful or robotic copy ("Oops!", "Something went wrong", "Your AI‑powered results are ready ✨").
