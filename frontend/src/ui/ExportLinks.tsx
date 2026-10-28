// The run's downloads (spec 5.5 Export): the worksheet as Excel and the whole run record as
// JSON, both built by the server; links, so the browser saves them.

export function ExportLinks({ runId }: { runId: string }) {
  const base = `/runs/${encodeURIComponent(runId)}`;
  return (
    <ul className="export-links" aria-label="Export">
      <li>
        <a href={`${base}/export.xlsx`} download>
          Worksheet (.xlsx)
        </a>
      </li>
      <li>
        <a href={`${base}/export/run.json`} download>
          Run record (.json)
        </a>
      </li>
    </ul>
  );
}
