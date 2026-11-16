"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, BookOpenText, Check, Clock3, FileText, LoaderCircle, RefreshCw, Search, ShieldCheck, Trash2, Upload, X } from "lucide-react";
import EmptyState from "../../components/ui/EmptyState";
import SectionHeading from "../../components/ui/SectionHeading";
import { apiRequest, searchKnowledge, uploadKnowledgeDocument } from "../../lib/api";

function formatBytes(bytes) {
  if (!bytes) return "0 KB";
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusCopy(status) {
  return status === "ready" ? "Indexed" : status === "processing" ? "Processing" : status === "failed" ? "Needs attention" : "Superseded";
}

export default function KnowledgeBasePage() {
  const fileInput = useRef(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [addingDemo, setAddingDemo] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [busyDocument, setBusyDocument] = useState("");

  const loadDocuments = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    setLoadError("");
    try {
      setDocuments(await apiRequest("/knowledge/documents"));
    } catch (error) {
      setLoadError(error.message || "Knowledge documents could not be loaded.");
    } finally {
      if (initial) setLoading(false);
    }
  }, []);

  useEffect(() => { loadDocuments(true); }, [loadDocuments]);
  useEffect(() => {
    if (!documents.some((document) => document.status === "processing")) return undefined;
    const timer = window.setInterval(() => loadDocuments(false), 1600);
    return () => window.clearInterval(timer);
  }, [documents, loadDocuments]);

  async function handleFileChange(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setUploadMessage("");
    setUploadError("");
    try {
      const document = await uploadKnowledgeDocument(file);
      setUploadMessage(document.duplicate
        ? `This content is already in the workspace as “${document.title}” (version ${document.version}).`
        : `“${document.title}” was received. Text extraction and indexing are running.`);
      await loadDocuments(false);
    } catch (error) {
      setUploadError(error.message || "The document could not be uploaded.");
    } finally {
      setUploading(false);
    }
  }

  async function handleSearch(event) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setSearching(true);
    setSearchError("");
    setSearchResult(null);
    try {
      setSearchResult(await searchKnowledge(query.trim(), 5));
    } catch (error) {
      setSearchError(error.message || "Knowledge search is unavailable right now.");
    } finally {
      setSearching(false);
    }
  }

  async function handleDocumentAction(document, action) {
    setBusyDocument(document.id);
    setLoadError("");
    try {
      if (action === "delete") {
        await apiRequest(`/knowledge/documents/${document.id}`, { method: "DELETE" });
        setDocuments((current) => current.filter((item) => item.id !== document.id));
        setSearchResult(null);
      } else {
        await apiRequest(`/knowledge/documents/${document.id}/reindex`, { method: "POST" });
        await loadDocuments(false);
      }
    } catch (error) {
      setLoadError(error.message || `The document could not be ${action === "delete" ? "deleted" : "reindexed"}.`);
    } finally {
      setBusyDocument("");
    }
  }

  async function addDemoPolicies() {
    setAddingDemo(true);
    setLoadError("");
    setUploadError("");
    setUploadMessage("");
    try {
      const result = await apiRequest("/knowledge/demo-documents", { method: "POST" });
      setUploadMessage(`${result.added} synthetic Indian policy example${result.added === 1 ? "" : "s"} added; ${result.already_present} already in this workspace.`);
      await loadDocuments(false);
    } catch (error) {
      setLoadError(error.message || "Synthetic policy examples could not be added.");
    } finally {
      setAddingDemo(false);
    }
  }

  return (
    <div className="knowledge-page">
      <SectionHeading
        eyebrow="WORKSPACE KNOWLEDGE"
        title="Knowledge base"
        description="Index business guidance and search its source passages before responding to customers."
        action={<div className="knowledge-heading-actions"><button className="button button-secondary knowledge-demo-button" type="button" onClick={addDemoPolicies} disabled={addingDemo}><BookOpenText size={14} />{addingDemo ? "Adding examples…" : "Add synthetic examples"}</button><button className="button button-dark" type="button" onClick={() => fileInput.current?.click()} disabled={uploading}><Upload size={15} />{uploading ? "Uploading…" : "Upload document"}</button></div>}
      />

      <div className="demo-notice knowledge-demo-notice">
        <span className="notice-mark">i</span>
        <p><strong>Workspace-scoped knowledge.</strong> Each source is treated as untrusted evidence. Search returns citations only; response generation is not part of this milestone.</p>
        <span className="notice-label">TENANT ISOLATED</span>
      </div>

      {loadError && <div className="inline-error" role="alert"><AlertCircle size={15} />{loadError}<button type="button" onClick={() => loadDocuments(true)}>Retry</button></div>}
      {uploadError && <div className="inline-error" role="alert"><X size={15} />{uploadError}<button type="button" onClick={() => setUploadError("")}>Dismiss</button></div>}
      {uploadMessage && <div className="knowledge-success" role="status"><Check size={15} />{uploadMessage}<button type="button" aria-label="Dismiss upload message" onClick={() => setUploadMessage("")}><X size={14} /></button></div>}
      <input ref={fileInput} className="knowledge-file-input" type="file" accept=".pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown" onChange={handleFileChange} />

      <div className="knowledge-layout">
        <section className="knowledge-panel knowledge-library" aria-labelledby="knowledge-library-title">
          <div className="knowledge-panel-heading">
            <div><p className="eyebrow">YOUR SOURCES</p><h2 id="knowledge-library-title">Documents</h2></div>
            <span className="knowledge-count">{documents.length} {documents.length === 1 ? "source" : "sources"}</span>
          </div>
          <div className="knowledge-upload-card">
            <div className="knowledge-upload-icon"><Upload size={17} /></div>
            <div><strong>Add a policy or guide</strong><p>PDF with selectable text, TXT, or Markdown · up to 10 MB</p></div>
            <button type="button" className="knowledge-browse" onClick={() => fileInput.current?.click()} disabled={uploading}>{uploading ? <LoaderCircle size={16} className="icon-spinning" /> : <Upload size={16} />}<span>{uploading ? "Working" : "Browse"}</span></button>
          </div>
        <p className="knowledge-file-note">Scanned PDFs without extractable text are not supported. Files stay in this workspace; source documents are not sent to a public storage bucket. Demo policies are explicitly labeled synthetic examples.</p>

          {loading ? <div className="knowledge-state"><LoaderCircle size={18} className="icon-spinning" /><span>Loading workspace sources…</span></div>
            : documents.length === 0 ? <div className="knowledge-empty"><EmptyState title="No documents indexed yet" description="Upload a policy, FAQ, or approved response example to make its passages searchable in this workspace." /></div>
              : <div className="knowledge-documents">
                {documents.map((document) => <article className="knowledge-document" key={document.id}>
                  <div className="knowledge-document-icon"><FileText size={17} /></div>
                  <div className="knowledge-document-main">
                    <div className="knowledge-document-title"><strong title={document.title}>{document.title}</strong><span className={`knowledge-status knowledge-status-${document.status}`}><i />{statusCopy(document.status)}</span></div>
                    <p>{document.source_filename} <span>·</span> v{document.version} <span>·</span> {formatBytes(document.file_size_bytes)}</p>
                    <div className="knowledge-document-meta"><span>{document.chunk_count} passages</span><span>{document.extracted_chars.toLocaleString()} characters</span>{document.page_count ? <span>{document.page_count} pages</span> : null}</div>
                    {document.error_message && <p className="knowledge-document-error"><AlertCircle size={12} />{document.error_message}</p>}
                  </div>
                  <div className="knowledge-document-actions">
                    <button type="button" aria-label={`Reindex ${document.title}`} title="Reindex" onClick={() => handleDocumentAction(document, "reindex")} disabled={busyDocument === document.id || document.status === "processing"}><RefreshCw size={14} className={busyDocument === document.id ? "icon-spinning" : ""} /></button>
                    <button type="button" aria-label={`Delete ${document.title}`} title="Delete" onClick={() => handleDocumentAction(document, "delete")} disabled={busyDocument === document.id || document.status === "processing"}><Trash2 size={14} /></button>
                  </div>
                </article>)}
              </div>}
        </section>

        <section className="knowledge-panel knowledge-search" aria-labelledby="knowledge-search-title">
          <div className="knowledge-panel-heading">
            <div><p className="eyebrow">SEMANTIC RETRIEVAL</p><h2 id="knowledge-search-title">Search your knowledge</h2></div>
            <span className="knowledge-search-mark"><Search size={16} /></span>
          </div>
          <p className="knowledge-search-intro">Ask in English, Hindi, or Hinglish. Results include the original source and relevance score.</p>
          <form className="knowledge-search-form" onSubmit={handleSearch}>
            <label className="knowledge-query-label" htmlFor="knowledge-query">Search by question or topic</label>
            <div className="knowledge-query-box"><Search size={16} /><input id="knowledge-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. UPI refund mein kitna samay lagta hai?" maxLength={2000} /><button type="submit" className="button button-dark" disabled={searching || query.trim().length < 2}>{searching ? <LoaderCircle size={15} className="icon-spinning" /> : <Search size={15} />}<span>Search</span></button></div>
            <div className="knowledge-suggestions" aria-label="Example searches"><span>Try</span>{["UPI refund timeline", "late takeaway order", "returning an unused item"].map((suggestion) => <button key={suggestion} type="button" onClick={() => setQuery(suggestion)}>{suggestion}</button>)}</div>
          </form>
          <div className="knowledge-trust-note"><ShieldCheck size={15} /><p>Retrieved passages are untrusted source content. Instruction-like text is flagged heuristically; this is not complete prompt-injection protection.</p></div>
          {searchError && <div className="inline-error" role="alert"><AlertCircle size={15} />{searchError}</div>}
          {searching && <div className="knowledge-state"><LoaderCircle size={18} className="icon-spinning" /><span>Searching indexed passages…</span></div>}
          {!searching && searchResult && <div className="knowledge-results" aria-live="polite">
            <div className="knowledge-results-heading"><strong>{searchResult.abstained ? "No grounded passage found" : `${searchResult.results.length} source ${searchResult.results.length === 1 ? "passage" : "passages"}`}</strong><span>{searchResult.abstained ? "Insufficient evidence" : "Ordered by semantic similarity"}</span></div>
            {searchResult.abstained ? <div className="knowledge-abstention"><Clock3 size={16} /><p>{searchResult.abstention_reason || "No relevant evidence was found. Search will not invent an answer."}</p></div>
              : searchResult.results.map((result, index) => <article className="knowledge-result-card" key={`${result.document_id}-${result.source_reference}-${index}`}>
                <div className="knowledge-result-source"><BookOpenText size={14} /><strong>{result.document_title}</strong><span>{Math.round(result.similarity_score * 100)}% match</span></div>
                <p>{result.passage}</p>
                <div className="knowledge-result-citation"><FileText size={12} /><span>{result.source_filename}</span><span className="citation-separator">·</span><span>{result.page_number ? `Page ${result.page_number}` : result.source_reference}</span><small>v{result.retrieval_metadata.document_version} · passage {result.retrieval_metadata.chunk_index + 1}</small></div>
                {result.retrieval_metadata.risk_flags?.length > 0 && <div className="knowledge-risk-flag"><AlertCircle size={12} />Instruction-like text flagged for human caution</div>}
              </article>)}
            <p className="knowledge-retrieval-footnote">{searchResult.retrieval_metadata.embedding_model} · cosine similarity · tenant filter applied on the server</p>
          </div>}
        </section>
      </div>
    </div>
  );
}
