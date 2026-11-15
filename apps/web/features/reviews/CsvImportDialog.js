"use client";

import { useState } from "react";
import { ArrowUpFromLine, Check, FileSpreadsheet, X } from "lucide-react";
import { apiBaseUrl, apiRequest } from "../../lib/api";

export default function CsvImportDialog({ onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function previewFile(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError(""); setPreview(null); setJob(null);
    try {
      const form = new FormData(); form.append("file", file);
      setPreview(await apiRequest("/reviews/imports/preview", { method: "POST", body: form }));
    } catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  }

  async function importFile() {
    if (!file || !preview?.accepted_rows) return;
    setBusy(true); setError("");
    try {
      const form = new FormData(); form.append("file", file);
      const result = await apiRequest("/reviews/imports", { method: "POST", body: form });
      setJob(result); onImported?.();
    } catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="import-dialog" role="dialog" aria-modal="true" aria-labelledby="import-title">
        <div className="import-dialog-heading"><div><p className="eyebrow">CSV REVIEW IMPORT</p><h2 id="import-title">Bring reviews into focus.</h2></div><button className="icon-button" type="button" aria-label="Close import dialog" onClick={onClose}><X size={19} /></button></div>
        {job ? (
          <div className="import-complete" role="status"><span className="complete-mark"><Check size={20} /></span><h3>Import complete</h3><p><strong>{job.accepted_rows}</strong> accepted · <strong>{job.rejected_rows}</strong> rejected. Imported reviews are now saved in this workspace.</p><button className="button button-dark" type="button" onClick={onClose}>Return to overview</button></div>
        ) : (
          <>
            <p className="import-intro">Choose a UTF-8 CSV file. Review text and rating are required; author, date, location, source and external review ID are supported.</p>
            <form onSubmit={previewFile}>
              <label className="file-picker"><FileSpreadsheet size={20} /><span><strong>{file?.name || "Select a CSV file"}</strong><small>Up to 10 MB · max 10,000 rows</small></span><input type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); setError(""); }} /></label>
              <p className="import-required">Required columns: <code>review_text</code> and <code>rating</code>. Ratings must be 1–5 in half-star steps.</p>
              <a className="sample-csv-link" href={`${apiBaseUrl()}/api/v1/demo/reviews.csv`}>Download the fictional sample CSV</a>
              <div className="dialog-actions"><button className="button button-secondary" type="button" onClick={onClose}>Cancel</button><button className="button button-dark" type="submit" disabled={!file || busy}>{busy && !preview ? "Checking…" : "Preview import"} <ArrowUpFromLine size={15} /></button></div>
            </form>
            {error && <div className="form-error" role="alert"><strong>Couldn’t process this file.</strong> {error}</div>}
            {preview && <div className="import-preview" aria-live="polite">
              <div className="preview-summary"><strong>Import preview</strong><span>{preview.accepted_rows} accepted</span><span className={preview.rejected_rows ? "preview-rejected" : ""}>{preview.rejected_rows} rejected</span></div>
              <p>{preview.total_rows} rows found in <strong>{preview.filename}</strong>. Duplicate reviews are rejected before saving.</p>
              {!!preview.issue_summary.length && <div className="validation-summary"><strong>Validation issues across the full file</strong>{preview.issue_summary.map((issue) => <span key={issue.code}><b>{issue.count}</b> × {issue.message}</span>)}</div>}
              <div className="preview-rows">{preview.preview_rows.map((row) => <div className="preview-row" key={row.row_number}><span className={`preview-row-mark${row.accepted ? " is-accepted" : ""}`}>{row.accepted ? "✓" : "!"}</span><span className="preview-row-copy"><strong>Row {row.row_number}</strong><span>{row.review_text || "No review text"}</span>{row.issues.map((issue) => <small key={issue.code}>{issue.message}</small>)}</span><span className="preview-rating">{row.rating ? `${row.rating} ★` : "—"}</span></div>)}</div>
              {preview.total_rows > preview.preview_rows.length && <p className="preview-footnote">Showing the first {preview.preview_rows.length} rows; validation covered all {preview.total_rows}.</p>}
              <div className="dialog-actions"><button className="button button-secondary" type="button" onClick={() => { setPreview(null); setJob(null); }}>Choose another file</button><button className="button button-dark" type="button" onClick={importFile} disabled={!preview.accepted_rows || busy}>{busy ? "Importing…" : `Import ${preview.accepted_rows} reviews`}</button></div>
            </div>}
          </>
        )}
      </section>
    </div>
  );
}
