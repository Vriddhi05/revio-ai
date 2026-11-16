"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, BadgeCheck, BookOpenText, Check, CircleHelp, Clock3, LoaderCircle, MessageSquareText, ShieldAlert, Sparkles } from "lucide-react";
import SectionHeading from "../../components/ui/SectionHeading";
import { apiRequest } from "../../lib/api";

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "Date unavailable";
}

function ratingText(rating) {
  return `${Number(rating || 0).toFixed(1)} / 5`;
}

export default function ResponseStudioPage() {
  const [reviews, setReviews] = useState([]);
  const [reviewId, setReviewId] = useState("");
  const [review, setReview] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [draft, setDraft] = useState(null);
  const [audit, setAudit] = useState([]);
  const [text, setText] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadReviews = useCallback(async () => {
    const result = await apiRequest("/reviews?page=1&page_size=60&sort=priority");
    setReviews(result.items || []);
    return result.items || [];
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const items = await loadReviews();
        if (!active) return;
        const initial = new URLSearchParams(window.location.search).get("review") || items[0]?.id || "";
        setReviewId(initial);
        if (!initial) setLoading(false);
      } catch (cause) {
        if (active) { setError(cause.message || "Reviews could not be loaded."); setLoading(false); }
      }
    })();
    return () => { active = false; };
  }, [loadReviews]);

  const loadWorkspace = useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    setError("");
    setNotice("");
    setReview(null);
    setDraft(null);
    try {
      const [selectedReview, responseList] = await Promise.all([
        apiRequest(`/reviews/${id}`),
        apiRequest(`/reviews/${id}/responses`),
      ]);
      setReview(selectedReview);
      setDrafts(responseList);
      setDraft(responseList[0] || null);
      setAudit(responseList[0] ? await apiRequest(`/responses/${responseList[0].id}/audit`) : []);
    } catch (cause) {
      setError(cause.message || "The selected review could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (reviewId) loadWorkspace(reviewId); }, [reviewId, loadWorkspace]);
  useEffect(() => { setText(draft?.response_text || ""); }, [draft]);

  const dirty = useMemo(() => Boolean(draft && text !== draft.response_text), [draft, text]);

  async function selectReview(id) {
    setReviewId(id);
    if (id) window.history.replaceState(null, "", `/response-studio?review=${encodeURIComponent(id)}`);
  }

  async function generate() {
    if (!reviewId) return;
    setGenerating(true); setError(""); setNotice("");
    try {
      const created = await apiRequest(`/reviews/${reviewId}/responses/generate`, { method: "POST", body: "{}" });
      setDraft(created);
      setDrafts((current) => [created, ...current]);
      setAudit(await apiRequest(`/responses/${created.id}/audit`));
      setNotice(`Version ${created.version} created. Review the wording and citations before approval.`);
    } catch (cause) {
      setError(cause.message || "A response draft could not be generated.");
    } finally { setGenerating(false); }
  }

  async function save() {
    if (!draft || !dirty) return draft;
    setSaving(true); setError("");
    try {
      const updated = await apiRequest(`/responses/${draft.id}`, { method: "PATCH", body: JSON.stringify({ response_text: text }) });
      setDraft(updated);
      setDrafts((current) => current.map((item) => item.id === updated.id ? updated : item));
      setAudit(await apiRequest(`/responses/${updated.id}/audit`));
      setNotice("Your edit has been saved to the workspace audit trail.");
      return updated;
    } catch (cause) {
      setError(cause.message || "Your edit could not be saved.");
      return null;
    } finally { setSaving(false); }
  }

  async function approve() {
    if (!draft) return;
    const saved = await save();
    if (dirty && !saved) return;
    setSaving(true); setError("");
    try {
      const approved = await apiRequest(`/responses/${draft.id}/approve`, { method: "POST", body: "{}" });
      setDraft(approved);
      setDrafts((current) => current.map((item) => item.id === approved.id ? approved : item));
      setAudit(await apiRequest(`/responses/${approved.id}/audit`));
      setNotice("Approved for internal use. REVIO has not published this response.");
    } catch (cause) { setError(cause.message || "The response could not be approved."); }
    finally { setSaving(false); }
  }

  async function reject() {
    if (!draft) return;
    const saved = await save();
    if (dirty && !saved) return;
    setSaving(true); setError("");
    try {
      const rejected = await apiRequest(`/responses/${draft.id}/reject`, { method: "POST", body: JSON.stringify({ reason: rejectReason || null }) });
      setDraft(rejected);
      setDrafts((current) => current.map((item) => item.id === rejected.id ? rejected : item));
      setAudit(await apiRequest(`/responses/${rejected.id}/audit`));
      setNotice("This draft was rejected and retained in the audit trail.");
    } catch (cause) { setError(cause.message || "The response could not be rejected."); }
    finally { setSaving(false); }
  }

  const canDecide = draft && ["draft", "edited"].includes(draft.status);

  return <div className="response-studio-page">
    <SectionHeading eyebrow="CUSTOMER CARE" title="Response studio" description="Turn an individual review into a grounded draft your team can inspect, edit and approve." action={<Link className="studio-back-link" href="/reviews"><ArrowLeft size={14} /> Reviews inbox</Link>} />
    <div className="response-demo-notice"><ShieldAlert size={16} /><span><strong>Human approval required.</strong> Drafts are not published externally. Review the evidence and edit before approving.</span><b>DEMO WORKSPACE</b></div>
    {error && <div className="response-error" role="alert"><AlertCircle size={16} /><span>{error}</span><button type="button" onClick={() => reviewId ? loadWorkspace(reviewId) : loadReviews().then((items) => items[0] && selectReview(items[0].id))}>Retry</button></div>}
    {notice && <div className="response-notice" role="status"><Check size={15} /><span>{notice}</span></div>}
    <div className="response-review-picker">
      <label htmlFor="response-review">Review to respond to</label>
      <select id="response-review" value={reviewId} onChange={(event) => selectReview(event.target.value)} disabled={!reviews.length}>
        <option value="">Choose a review</option>
        {reviews.map((item) => <option value={item.id} key={item.id}>{item.author_name || "Anonymous"} · {ratingText(item.rating)} · {item.location?.name || "Location"}</option>)}
      </select>
      {review && <span className={`response-review-origin${review.is_synthetic ? "" : " response-review-origin-import"}`}>{review.is_synthetic ? "DEMO / SYNTHETIC DATA" : "CSV IMPORT"}</span>}
    </div>

    {!reviewId && !loading && <div className="response-empty"><span><MessageSquareText size={19} /></span><h2>No reviews in this workspace yet</h2><p>Import reviews from the Overview or Reviews inbox to start a response draft.</p><Link className="button button-dark" href="/reviews">Open Reviews inbox</Link></div>}
    {loading && <div className="response-loading" role="status"><LoaderCircle size={19} className="spin" /> Loading review and response history…</div>}
    {review && !loading && <div className="response-studio-grid">
      <section className="response-panel response-source-panel">
        <div className="response-panel-heading"><div><p className="eyebrow">SOURCE REVIEW</p><h2>Customer feedback</h2></div><span className="response-rating">{ratingText(review.rating)}</span></div>
        <blockquote>{review.review_text}</blockquote>
        <div className="response-review-meta"><span>{review.author_name || "Anonymous"}</span><span>{review.location?.name || "Location unavailable"}</span><span>{formatDate(review.review_date)}</span><span>{review.source_name}</span></div>
        {review.analysis ? <div className="response-analysis"><div><small>Sentiment</small><strong className={`sentiment-${review.analysis.sentiment}`}>{review.analysis.sentiment}</strong></div><div><small>Urgency</small><strong className={`severity-${review.analysis.severity}`}>{review.analysis.severity}</strong></div><div><small>Language</small><strong>{review.analysis.language}</strong></div></div> : <p className="response-muted-note">Review intelligence is prepared as part of the response workflow.</p>}
        {draft?.needs_human_escalation && <div className="response-escalation"><ShieldAlert size={15} /><span>High-priority review. Route this case to a human reviewer before customer use.</span></div>}
        <div className="response-source-footer"><span>Private workspace evidence only</span><Link href={`/reviews?review=${encodeURIComponent(review.id)}`}>Open full review <ArrowLeft size={12} /></Link></div>
      </section>

      <section className="response-panel response-draft-panel">
        <div className="response-panel-heading"><div><p className="eyebrow">AI RESPONSE DRAFT</p><h2>{draft ? `Version ${draft.version}` : "Start with a draft"}</h2></div>
          {draft && <span className={`response-status response-status-${draft.status}`}>{draft.status}</span>}
        </div>
        {!draft ? <div className="response-start"><span><Sparkles size={19} /></span><h3>Grounded in your workspace guidance</h3><p>REVIO will analyze this review, retrieve relevant policy passages and check the draft for unsupported promises.</p><button className="button button-dark" type="button" onClick={generate} disabled={generating}><Sparkles size={14} />{generating ? "Building draft…" : "Generate response draft"}</button></div> : <>
          <div className="response-provider-note"><Sparkles size={13} /><span>{draft.generation_provider.startsWith("demo_fallback") ? "DEMO DRAFT · deterministic safe template" : `Hosted model · ${draft.generation_model}`}</span><span className="response-language-tag">{draft.language}</span></div>
          {draft.generation_provider.startsWith("demo_fallback") && <p className="response-fallback-explainer">This draft was created with REVIO’s deterministic demo template. It is not an LLM-generated response.</p>}
          <label className="response-editor-label" htmlFor="response-editor">Response text <span>{dirty ? "Unsaved changes" : "Saved"}</span></label>
          <textarea id="response-editor" className="response-editor" value={text} onChange={(event) => setText(event.target.value)} maxLength={4000} readOnly={!canDecide} aria-describedby="response-editor-help" />
          <p id="response-editor-help" className="response-editor-help">Read the reply aloud and check it against the cited policy before approval.</p>
          {draft.validation?.scope_note && <div className="response-validation"><BadgeCheck size={14} /><span>{draft.validation.fallback_applied ? "A guardrail replaced a draft containing unsupported claims. " : "Selected checks passed. "}{draft.validation.scope_note}</span></div>}
          <div className="response-workflow">
            <div className="response-subheading"><strong>Workflow steps</strong><span>LangGraph StateGraph execution</span></div>
            {draft.workflow_trace.map((step) => <div className="response-workflow-row" key={step.node}><span className={`workflow-mark workflow-${step.status}`}>{step.status === "completed" ? <Check size={12} /> : step.status === "failed" ? <AlertCircle size={12} /> : <Clock3 size={12} />}</span><strong>{step.node.replaceAll("_", " ")}</strong><small>{step.status}</small><small>{step.duration_ms} ms</small></div>)}
          </div>
          <div className="response-citations">
            <div className="response-subheading"><strong><BookOpenText size={14} /> Policy evidence</strong><span>{draft.citations.length} cited passage{draft.citations.length === 1 ? "" : "s"}</span></div>
            {draft.citations.length ? draft.citations.map((citation, index) => <article className="response-citation-card" key={`${citation.document_id}-${citation.source_reference}-${index}`}>
              <div className="response-citation-title"><strong>{citation.document_title}</strong><span>{Math.round(citation.similarity_score * 100)}% similarity</span></div>
              <p>{citation.passage}</p>
              <div><BookOpenText size={12} /><span>{citation.source_reference}</span>{citation.page_number && <span>Page {citation.page_number}</span>}<small>Untrusted source · verify before use</small></div>
            </article>) : <div className="response-no-evidence"><CircleHelp size={15} /><span>No policy passage met the retrieval threshold. The draft avoids policy-specific claims and does not confirm an outcome or timeline.</span></div>}
          </div>
          {canDecide && <>
            <label className="response-reject-reason" htmlFor="response-reject-reason">Rejection note <span>Optional</span><input id="response-reject-reason" value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} maxLength={500} placeholder="Why should this draft be revised?" /></label>
            <div className="response-actions"><button type="button" className="button button-secondary" onClick={save} disabled={saving || !dirty}>{saving ? "Saving…" : "Save edit"}</button><button type="button" className="button button-reject" onClick={reject} disabled={saving}>Reject</button><button type="button" className="button button-dark" onClick={approve} disabled={saving || !text.trim()}><Check size={14} />{saving ? "Saving…" : "Approve draft"}</button></div>
          </>}
          {!canDecide && <div className={`response-final-state response-final-${draft.status}`}>{draft.status === "approved" ? "Approved for internal use. No external response was sent." : "Rejected. The draft and decision remain in the audit trail."}</div>}
          <div className="response-audit">
            <div className="response-subheading"><strong>Human approval audit</strong><span>{audit.length} event{audit.length === 1 ? "" : "s"}</span></div>
            {audit.map((event) => <div className="response-audit-row" key={event.id}><span>{event.action}</span><strong>{event.from_status ? `${event.from_status} → ` : ""}{event.to_status}</strong><small>{event.actor} · {new Date(event.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}{event.reason ? ` · ${event.reason}` : ""}</small></div>)}
          </div>
          {drafts.length > 1 && <div className="response-version-list"><strong>Earlier versions</strong>{drafts.slice(1).map((item) => <button type="button" key={item.id} onClick={async () => { setDraft(item); setAudit(await apiRequest(`/responses/${item.id}/audit`)); }}>{`Version ${item.version} · ${item.status}`}</button>)}</div>}
        </>}
      </section>
    </div>}
  </div>;
}
