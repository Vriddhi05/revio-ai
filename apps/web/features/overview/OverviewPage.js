"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDownToLine, ArrowUpRight, CircleAlert, MapPin, MessageSquareText, Star } from "lucide-react";
import SectionHeading from "../../components/ui/SectionHeading";
import EmptyState from "../../components/ui/EmptyState";
import CsvImportDialog from "../reviews/CsvImportDialog";
import { apiRequest } from "../../lib/api";

const number = new Intl.NumberFormat("en-IN");

export default function OverviewPage() {
  const [summary, setSummary] = useState(null);
  const [locations, setLocations] = useState([]);
  const [attention, setAttention] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [importOpen, setImportOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [analytics, locationList, needsAttention] = await Promise.all([
        apiRequest("/analytics/summary?days=30"), apiRequest("/locations"),
        apiRequest("/reviews?status=needs_attention&sort=priority&page_size=3"),
      ]);
      setSummary(analytics); setLocations(locationList); setAttention(needsAttention.items);
    } catch (cause) { setError(cause.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const refresh = () => load();
    window.addEventListener("revio-data-changed", refresh);
    return () => window.removeEventListener("revio-data-changed", refresh);
  }, [load]);

  const metrics = [
    { label: "Reviews received", icon: MessageSquareText, value: summary ? number.format(summary.total_reviews) : "—", note: "Stored in this workspace" },
    { label: "Average rating", icon: Star, value: summary?.average_rating == null ? "—" : `${summary.average_rating.toFixed(1)} / 5`, note: "Across all stored reviews" },
    { label: "Needs attention", icon: CircleAlert, value: summary ? number.format(summary.needs_attention) : "—", note: "Low-rated reviews to follow up" },
    { label: "Locations", icon: MapPin, value: summary ? number.format(summary.locations) : "—", note: "Represented in review data" },
  ];

  return (
    <div className="overview-page">
      <SectionHeading eyebrow="WORKSPACE OVERVIEW" title="Your reputation, in focus." description="A thoughtful view of what customers are saying across your locations." action={<button className="button button-secondary" type="button" onClick={() => setImportOpen(true)}><ArrowDownToLine size={16} /> Import reviews</button>} />

      <div className="demo-notice" role="status"><span className="notice-mark">i</span><p><strong>Fictional demo workspace.</strong> Seeded records are synthetic examples; CSV imports are labelled separately. No live review integrations are connected.</p><span className="notice-label">SAMPLE DATA</span></div>
      {error && <div className="inline-error" role="alert"><strong>Workspace data could not be loaded.</strong> {error} <button type="button" onClick={load}>Retry</button></div>}

      <section className="metrics-grid" aria-label="Reputation summary" aria-busy={loading}>
        {metrics.map(({ label, icon: Icon, value, note }) => <article className="metric-card" key={label}>
          <div className="metric-card-top"><span>{label}</span><Icon size={17} strokeWidth={1.7} /></div>
          <div className="metric-value">{loading ? <span className="metric-skeleton" aria-label="Loading" /> : value}</div><p className="metric-note">{note}</p>
        </article>)}
      </section>

      <section className="overview-grid">
        <article className="panel trend-panel"><div className="panel-heading"><div><p className="eyebrow">YOUR PULSE</p><h2>Reputation over time</h2></div><span className="trend-range">Last 30 days</span></div>
          {loading ? <div className="dashboard-loading" role="status">Loading review trends…</div> : error ? <EmptyState title="Trend unavailable" description="We couldn’t retrieve the stored review trend. Try again when the API is available." /> : summary?.total_reviews ? <div className="trend-chart" aria-label="Daily review volume for the last 30 days">{summary.trend.map((point) => <div className="trend-day" key={point.day} title={`${point.day}: ${point.count} reviews`}><span className="trend-bar" style={{ height: `${Math.max(point.count ? 12 : 3, (point.count / Math.max(...summary.trend.map((entry) => entry.count), 1)) * 100)}%` }} /><small>{new Date(`${point.day}T12:00:00`).getDate()}</small></div>)}</div> : <EmptyState title="Your story starts with a review" description="Import reviews to see daily activity across your locations." />}
        </article>
        <article className="panel attention-panel"><div className="panel-heading"><div><p className="eyebrow">ATTENTION</p><h2>Needs your attention</h2></div><span className="panel-icon coral-icon"><CircleAlert size={17} /></span></div>
          {loading ? <div className="dashboard-loading">Loading priority reviews…</div> : error ? <EmptyState title="Attention list unavailable" description="Review details will appear when the API connection is restored." /> : attention.length ? <div className="attention-list">{attention.map((review) => <Link className="attention-item" href={`/reviews?review=${review.id}`} key={review.id}><span className="attention-rating">{review.rating.toFixed(1)} ★</span><span><strong>{review.location.name}</strong><small>{review.review_text}</small></span><ArrowUpRight size={14} /></Link>)}</div> : <EmptyState title="All quiet for now" description="There are no low-rated reviews that need attention." />}
        </article>
      </section>

      <section className="panel locations-panel"><div className="panel-heading"><div><p className="eyebrow">ACROSS YOUR BUSINESS</p><h2>Location pulse</h2></div><Link className="quiet-link" href="/reviews">View reviews <ArrowUpRight size={15} /></Link></div>
        {loading ? <div className="dashboard-loading">Loading locations…</div> : locations.length ? <div className="location-list">{locations.map((location) => <div className="location-row" key={location.id}><MapPin size={17} /><span>{location.name}</span><Link href={`/reviews?location=${location.id}`}>Explore reviews <ArrowUpRight size={13} /></Link></div>)}</div> : <div className="location-empty-row"><MapPin size={19} /><span>Locations appear automatically as reviews are imported.</span></div>}
      </section>

      <section className="getting-started"><div className="getting-started-copy"><span className="step-number">01</span><div><p className="eyebrow">A GOOD PLACE TO BEGIN</p><h2>Bring your customer voice into focus.</h2><p>Import a review export to start seeing patterns across your locations.</p></div></div><button className="button button-dark" type="button" onClick={() => setImportOpen(true)}>Import a CSV <span aria-hidden="true">↗</span></button></section>
      {importOpen && <CsvImportDialog onClose={() => setImportOpen(false)} onImported={() => { window.dispatchEvent(new Event("revio-data-changed")); }} />}
    </div>
  );
}
