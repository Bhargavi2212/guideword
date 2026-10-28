// Screen 7, coverage (spec 5.4): one row per question list with its served counts, the failed
// questions traced to their records, and the engineer's own questions: added here (a section and
// the text, posted) and answered here with the `answer` override.

import { useState } from "react";

import { ApiError, errorMessage, overrideBlockedReason } from "../api/client";
import { useResource } from "../api/hooks";
import type {
  AddQuestionRequest,
  Coverage as CoverageBody,
  Question,
  QuestionCreated,
  QuestionList,
  RunLabel,
  RunSections,
} from "../api/schema";
import { useApp } from "../app/context";
import { coverageTotals, failedRows, listName } from "../model/coverage";
import { Traced } from "../ui/Traced";

export function Coverage({ runId }: { runId: string }) {
  const base = `/runs/${encodeURIComponent(runId)}`;
  const coverage = useResource<CoverageBody>(`${base}/coverage`);
  const failed = useResource<QuestionList>(`${base}/questions?status=failed`);

  if (coverage.error !== null) {
    return (
      <section>
        <h2>Coverage</h2>
        <p className="error">{errorMessage(coverage.error)}</p>
      </section>
    );
  }
  if (coverage.data === null) {
    return (
      <section>
        <h2>Coverage</h2>
        <p>Loading…</p>
      </section>
    );
  }
  const { lists, failed_question_ids: failedIds, label } = coverage.data;
  const totals = coverageTotals(lists);
  const rows = failedRows(failedIds, failed.data?.questions ?? []);

  return (
    <section className="coverage">
      <h2>Coverage</h2>
      <p className="coverage-total" data-testid="coverage-total">
        {`Checked ${String(totals.questions.checked)} of ${String(totals.questions.total)} questions`}
        {totals.sections
          ? ` · ${String(totals.sections.checked)} of ${String(totals.sections.total)} sections`
          : ""}
      </p>
      <table className="coverage-table" aria-label="Coverage">
        <thead>
          <tr>
            <th scope="col">List</th>
            <th scope="col">Checked</th>
            <th scope="col">Unsure</th>
            <th scope="col">Failed</th>
          </tr>
        </thead>
        <tbody>
          {lists.map((l) => (
            <tr key={l.list} data-list={l.list}>
              <th scope="row">{listName(l.list)}</th>
              <td>
                <meter min={0} max={Math.max(l.total, 1)} value={l.checked} />{" "}
                {`${String(l.checked)} of ${String(l.total)}`}
              </td>
              <td>{String(l.unsure)}</td>
              <td className={l.failed > 0 ? "bad" : undefined}>
                {String(l.failed)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Failed questions</h3>
      {rows.length === 0 ? (
        <p className="muted">No question failed.</p>
      ) : (
        <ul className="failed-questions" aria-label="Failed questions">
          {rows.map((r) => (
            <li key={r.id}>
              <Traced id={r.id}>{r.id}</Traced>
              {r.text !== null ? <span> {r.text}</span> : null}
            </li>
          ))}
        </ul>
      )}

      <EngineerQuestions
        runId={runId}
        label={label}
        onChange={coverage.reload}
      />
    </section>
  );
}

function EngineerQuestions({
  runId,
  label,
  onChange,
}: {
  runId: string;
  label: RunLabel;
  onChange: () => void;
}) {
  const { client, engineer } = useApp();
  const base = `/runs/${encodeURIComponent(runId)}`;
  const served = useResource<QuestionList>(`${base}/questions?kind=engineer`);
  const sections = useResource<RunSections>(`${base}/sections`);
  // a mock run echoes an added question without storing it, so the page keeps what it added
  const [added, setAdded] = useState<Question[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const servedIds = new Set((served.data?.questions ?? []).map((q) => q.id));
  const questions = [
    ...(served.data?.questions ?? []),
    ...added.filter((q) => !servedIds.has(q.id)),
  ];

  const failure = (error: unknown) =>
    setMessage(error instanceof ApiError ? errorMessage(error) : String(error));

  const add = (body: AddQuestionRequest) => {
    setMessage(null);
    client.post<QuestionCreated>(`${base}/questions`, body).then((result) => {
      setAdded((list) => [...list, result.question]);
      served.reload();
      onChange();
    }, failure);
  };

  // an answer is an override, refused unsent on a recorded or mock run (P5-7)
  const answerBlocked = overrideBlockedReason(label);
  const answer = (questionId: string, text: string) => {
    setMessage(null);
    client
      .postOverride(runId, label, {
        target_id: questionId,
        action: "answer",
        new_value: { text },
        reason: "the engineer's answer to their question",
        by: engineer,
      })
      .then(() => {
        setMessage("Answer saved.");
        served.reload();
        onChange();
      }, failure);
  };

  return (
    <section className="engineer-questions">
      <h3>Engineer questions</h3>
      <AddForm
        sections={sections.data?.sections ?? []}
        blocked={
          label.kind === "recorded"
            ? "This run is recorded and read-only"
            : null
        }
        onAdd={add}
      />
      {message !== null ? <p role="status">{message}</p> : null}
      <ul aria-label="Engineer questions" className="engineer-list">
        {questions.length === 0 ? (
          <li className="muted">No engineer questions yet.</li>
        ) : null}
        {answerBlocked !== null && questions.length > 0 ? (
          <li className="blocked">{answerBlocked}</li>
        ) : null}
        {answerBlocked === null && engineer === "" && questions.length > 0 ? (
          <li className="blocked">Enter your name in the header to answer.</li>
        ) : null}
        {questions.map((q) => (
          <li key={q.id}>
            <Traced id={q.id}>{q.section_id}</Traced>{" "}
            <span className="question-status">{q.status}</span>{" "}
            <span>{q.text}</span>
            {q.status === "open" &&
            answerBlocked === null &&
            engineer !== "" ? (
              <AnswerForm onAnswer={(text) => answer(q.id, text)} />
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function AddForm({
  sections,
  blocked,
  onAdd,
}: {
  sections: readonly { id: string; name: string }[];
  blocked: string | null;
  onAdd: (body: AddQuestionRequest) => void;
}) {
  const [sectionId, setSectionId] = useState("");
  const [text, setText] = useState("");
  const ready = blocked === null && sectionId !== "" && text.trim() !== "";
  return (
    <form
      aria-label="Add a question"
      className="add-question"
      onSubmit={(e) => {
        e.preventDefault();
        if (!ready) return;
        onAdd({ section_id: sectionId, text: text.trim() });
        setText("");
      }}
    >
      {blocked !== null ? <p className="blocked">{blocked}</p> : null}
      <label>
        Section
        <select
          value={sectionId}
          disabled={blocked !== null}
          onChange={(e) => setSectionId(e.target.value)}
        >
          <option value="">Choose a section</option>
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              {`${s.id} — ${s.name}`}
            </option>
          ))}
        </select>
      </label>
      <label>
        Question
        <input
          value={text}
          disabled={blocked !== null}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      <button type="submit" disabled={!ready}>
        Add
      </button>
    </form>
  );
}

function AnswerForm({ onAnswer }: { onAnswer: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <span className="answer-form">
      <label>
        Answer
        <input value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <button
        type="button"
        disabled={text.trim() === ""}
        onClick={() => onAnswer(text.trim())}
      >
        Save answer
      </button>
    </span>
  );
}
