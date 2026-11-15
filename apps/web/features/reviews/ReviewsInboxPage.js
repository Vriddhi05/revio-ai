"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, CircleAlert, Search, SlidersHorizontal, Star, X } from "lucide-react";
import SectionHeading from "../../components/ui/SectionHeading";
import { apiRequest } from "../../lib/api";

const STATUSES = [["", "All statuses"], ["new", "New"], ["needs_attention", "Needs attention"], ["resolved", "Resolved"]];
const dateLabel = (value) => value ? new Date(`${value}T12:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "Date unavailable";

function Stars({ rating }) { return <span className="review-stars" aria-label={`${rating} out of 5 stars`}><Star size={14} fill="currentColor" /> {rating.toFixed(1)}</span>; }

export default function ReviewsInboxPage() {
  const [filters, setFilters] = useState({ search: "", location_id: "", rating: "", sentiment: "", date_from: "", date_to: "", status: "", sort: "newest" });
  const [page, setPage] = useState(1);
  const [locations, setLocations] = useState([]);
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [classificationNotice, setClassificationNotice] = useState(false);
  const [deepLinkReview, setDeepLinkReview] = useState("");
  const [filtersReady, setFiltersReady] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "20", sort: filters.sort });
      for (const [key, value] of Object.entries(filters)) if (value && key !== "sort") params.set(key, value);
      const [reviews, locationList] = await Promise.all([apiRequest(`/reviews?${params}`), apiRequest("/locations")]);
      setData(reviews); setLocations(locationList);
    } catch (cause) { setError(cause.message); setData(null); setLocations([]); setSelected(null); }
    finally { setLoading(false); }
  }, [filters, page]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const location = params.get("location");
    const review = params.get("review");
    if (location) setFilters((current) => ({ ...current, location_id: location }));
    if (review) setDeepLinkReview(review);
    setFiltersReady(true);
  }, []);
  useEffect(() => { if (filtersReady) load(); }, [filtersReady, load]);
  useEffect(() => { if (deepLinkReview) apiRequest(`/reviews/${deepLinkReview}`).then(setSelected).catch(() => {}); }, [deepLinkReview]);

  function updateFilter(name, value) { setPage(1); setFilters((current) => ({ ...current, [name]: value })); }
  async function chooseReview(review) {
    setSelected(review);
    try { setSelected(await apiRequest(`/reviews/${review.id}`)); } catch { /* The list item remains available as a fallback. */ }
  }
  async function updateStatus(status) {
    if (!selected) return;
    try {
      const updated = await apiRequest(`/reviews/${selected.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      setSelected(updated); await load();
    } catch (cause) { setError(cause.message); }
  }

  return <div className="inbox-page">
    <SectionHeading eyebrow="CUSTOMER VOICE" title="Reviews inbox" description="Search, sort and follow up on reviews from every location." />
    <div className="inbox-notice"><CircleAlert size={15} /><span>DEMO / SYNTHETIC DATA: all seeded reviews are fictional Indian examples. Sentiment classification is not available yet.</span></div>
    <section className="inbox-filters" aria-label="Review filters">
      <label className="search-field"><Search size={17} /><input value={filters.search} onChange={(event) => updateFilter("search", event.target.value)} placeholder="Search reviews or authors" aria-label="Search reviews or authors" /></label>
      <label className="filter-control"><span>Location</span><select value={filters.location_id} onChange={(event) => updateFilter("location_id", event.target.value)}><option value="">All locations</option>{locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}</select></label>
      <label className="filter-control"><span>Rating</span><select value={filters.rating} onChange={(event) => updateFilter("rating", event.target.value)}><option value="">All ratings</option>{[5, 4.5, 4, 3.5, 3, 2.5, 2, 1.5, 1].map((rating) => <option value={rating} key={rating}>{rating} stars</option>)}</select></label>
      <label className="filter-control"><span>Sentiment</span><select value={filters.sentiment} onChange={(event) => { updateFilter("sentiment", event.target.value); if (event.target.value) setClassificationNotice(true); }}><option value="">Any sentiment</option><option value="positive">Positive</option><option value="mixed">Mixed</option><option value="negative">Negative</option></select></label>
      <label className="filter-control"><span>From</span><input type="date" value={filters.date_from} onChange={(event) => updateFilter("date_from", event.target.value)} /></label>
      <label className="filter-control"><span>To</span><input type="date" value={filters.date_to} onChange={(event) => updateFilter("date_to", event.target.value)} /></label>
      <label className="filter-control"><span>Status</span><select value={filters.status} onChange={(event) => updateFilter("status", event.target.value)}>{STATUSES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label className="filter-control"><span>Sort by</span><select value={filters.sort} onChange={(event) => updateFilter("sort", event.target.value)}><option value="newest">Newest</option><option value="priority">Priority</option></select></label>
    </section>
    {classificationNotice && <div className="classification-note" role="status">Reviews have not been classified yet. This filter will return results once sentiment analysis is available.<button type="button" onClick={() => { setClassificationNotice(false); updateFilter("sentiment", ""); }}>Dismiss</button></div>}
    {error && <div className="inline-error" role="alert"><strong>Reviews could not be loaded.</strong> {error} <button type="button" onClick={load}>Retry</button></div>}

    <section className={`inbox-content${selected ? " has-selection" : ""}`} aria-busy={loading}>
      <div className="review-list-panel">
        <div className="inbox-list-heading"><div><p className="eyebrow">REVIEWS</p><strong>{loading ? "Loading reviews…" : error && !data ? "Reviews unavailable" : `${data?.total || 0} ${data?.total === 1 ? "review" : "reviews"}`}</strong></div><span><SlidersHorizontal size={15} /> Filtered by workspace</span></div>
        {loading ? <div className="inbox-loading" role="status"><span /><span /><span /><span /></div> : error && !data ? <div className="inbox-empty"><span className="inbox-empty-icon"><Search size={19} /></span><h2>Inbox unavailable</h2><p>{error}</p><button className="button button-secondary" type="button" onClick={load}>Try again</button></div> : !data?.items.length ? <div className="inbox-empty"><span className="inbox-empty-icon"><Search size={19} /></span><h2>No reviews found</h2><p>Try changing your search or filters. You can also import a CSV from the Overview.</p></div> : <>
          <div className="review-list">{data.items.map((review) => <button className={`review-list-item${selected?.id === review.id ? " selected" : ""}`} type="button" key={review.id} onClick={() => chooseReview(review)}>
            <div className="review-item-top"><span className="review-author">{review.author_name || "Anonymous"}</span><span className="review-date">{dateLabel(review.review_date)}</span></div>
            <div className="review-item-meta"><Stars rating={review.rating} /><span>{review.location.name}</span><span className="review-source">{review.source_name}</span></div>
            <p>{review.review_text}</p>
            <div className="review-item-bottom"><span className={`status-pill status-${review.status}`}>{review.status.replaceAll("_", " ")}</span><span className={`origin-pill${review.is_synthetic ? " origin-synthetic" : ""}`}>{review.is_synthetic ? "DEMO / SYNTHETIC DATA" : "CSV import"}</span></div>
          </button>)}</div>
          <div className="inbox-pagination"><span>Page {data.page} of {Math.max(1, data.pages)}</span><div><button type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={16} /></button><button type="button" aria-label="Next page" disabled={page >= data.pages} onClick={() => setPage((value) => value + 1)}><ChevronRight size={16} /></button></div></div>
        </>}
      </div>
      <aside className="review-detail-panel" aria-label="Review details">
        {selected ? <><div className="detail-heading"><div><p className="eyebrow">REVIEW DETAIL</p><h2>Customer feedback</h2></div><button type="button" className="detail-close" aria-label="Close review details" onClick={() => setSelected(null)}><X size={17} /></button></div>
          <div className="detail-rating"><Stars rating={selected.rating} /><span className={`status-pill status-${selected.status}`}>{selected.status.replaceAll("_", " ")}</span></div>
          <blockquote>{selected.review_text}</blockquote>
          <dl className="detail-fields"><div><dt>Customer</dt><dd>{selected.author_name || "Anonymous"}</dd></div><div><dt>Review date</dt><dd>{dateLabel(selected.review_date)}</dd></div><div><dt>Location</dt><dd>{selected.location.name}</dd></div><div><dt>Source</dt><dd>{selected.source_name}</dd></div><div><dt>Record origin</dt><dd>{selected.import_metadata.record_origin}</dd></div><div><dt>Import file</dt><dd>{selected.import_metadata.filename || "—"}</dd></div><div><dt>Imported</dt><dd>{new Date(selected.import_metadata.imported_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</dd></div><div><dt>External review ID</dt><dd>{selected.external_review_id || "—"}</dd></div></dl>
          <label className="status-update"><span>Update status</span><select value={selected.status} onChange={(event) => updateStatus(event.target.value)}><option value="new">New</option><option value="needs_attention">Needs attention</option><option value="resolved">Resolved</option></select></label>
        </> : <div className="detail-placeholder"><span className="detail-placeholder-icon"><Star size={19} /></span><h2>Select a review</h2><p>Choose a review to see its full text, source and import details.</p></div>}
      </aside>
    </section>
  </div>;
}
