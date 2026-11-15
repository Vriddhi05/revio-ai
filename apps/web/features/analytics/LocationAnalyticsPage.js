"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, MapPin, RefreshCw, Sparkles } from "lucide-react";
import SectionHeading from "../../components/ui/SectionHeading";
import EmptyState from "../../components/ui/EmptyState";
import { apiRequest } from "../../lib/api";

const number = new Intl.NumberFormat("en-IN");

function DistributionBar({ label, count, total, tone }) {
  const width = total ? Math.max(count ? 4 : 0, (count / total) * 100) : 0;
  return <div className="distribution-row"><div><span>{label}</span><strong>{number.format(count)}</strong></div><span className="distribution-track"><i className={"distribution-fill " + tone} style={{ width: width + "%" }} /></span></div>;
}

export default function LocationAnalyticsPage() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [analytics, modelStatus] = await Promise.all([
        apiRequest("/analytics/location-intelligence?days=30"),
        apiRequest("/intelligence/status"),
      ]);
      setData(analytics); setStatus(modelStatus);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function analyze() {
    setAnalyzing(true); setError(""); setMessage("");
    try {
      const result = await apiRequest("/intelligence/analyze?limit=1000", { method: "POST" });
      setMessage(result.analyzed + " reviews analyzed; " + result.skipped_cached + " reused from the saved analysis cache.");
      await load();
      window.dispatchEvent(new Event("revio-data-changed"));
    } catch (cause) {
      setError(cause.message);
    } finally {
      setAnalyzing(false);
    }
  }

  const locations = data?.locations || [];
  const maxCategory = Math.max(...locations.flatMap((location) => location.top_categories.map((item) => item.count)), 1);

  return <div className="intelligence-page">
    <SectionHeading eyebrow="OPERATING PICTURE" title="Location analytics" description="Compare persisted review signals across Jaipur, Chandigarh and Ludhiana." action={<button className="button button-secondary" type="button" onClick={analyze} disabled={analyzing}><Sparkles size={15} />{analyzing ? "Analyzing…" : "Analyze reviews"}</button>} />
    <div className="demo-notice"><span className="notice-mark">i</span><p><strong>DEMO / SYNTHETIC DATA.</strong> Metrics come from stored fictional reviews and saved analyses; classification coverage is shown explicitly.</p><span className="notice-label">INDIA DEMO</span></div>
    {message && <div className="analysis-message" role="status">{message}</div>}
    {error && <div className="inline-error" role="alert"><strong>Location analytics unavailable.</strong> {error} <button type="button" onClick={load}>Retry</button></div>}

    <section className="metrics-grid intelligence-metrics" aria-label="Location analytics summary" aria-busy={loading}>
      <article className="metric-card"><div className="metric-card-top"><span>Stored reviews</span><MapPin size={17} /></div><div className="metric-value">{loading ? "—" : number.format(data?.total_reviews || 0)}</div><p className="metric-note">Across all workspace locations</p></article>
      <article className="metric-card"><div className="metric-card-top"><span>Analysis coverage</span><Sparkles size={17} /></div><div className="metric-value">{loading ? "—" : number.format(data?.analyzed_reviews || 0) + " / " + number.format(data?.total_reviews || 0)}</div><p className="metric-note">Saved classification records</p></article>
      <article className="metric-card"><div className="metric-card-top"><span>Locations</span><MapPin size={17} /></div><div className="metric-value">{loading ? "—" : locations.length}</div><p className="metric-note">From tenant location records</p></article>
      <article className="metric-card"><div className="metric-card-top"><span>Analysis method</span><RefreshCw size={17} /></div><div className="metric-method-value">{loading ? "Loading…" : status?.sentiment_provider === "transformers" ? "MuRIL · optional" : "Rules fallback"}</div><p className="metric-note">{status?.aspect_provider || "Analysis status unavailable"}</p></article>
    </section>

    {loading ? <section className="location-analytics-grid"><div className="intelligence-loading"><span /><span /></div><div className="intelligence-loading"><span /><span /></div></section> : error && !data ? null : locations.length ? <section className="location-analytics-grid" aria-label="Location comparison">
      {locations.map((location) => {
        const maxNegative = Math.max(...location.negative_trend.map((point) => point.count), 1);
        return <article className="panel location-intelligence-card" key={location.id}>
          <div className="panel-heading"><div><p className="eyebrow">LOCATION</p><h2>{location.name}</h2></div><span className="panel-icon"><MapPin size={17} /></span></div>
          <div className="location-primary-metrics"><div><small>Reviews</small><strong>{number.format(location.total_reviews)}</strong></div><div><small>Average rating</small><strong>{location.average_rating == null ? "—" : location.average_rating.toFixed(1) + " / 5"}</strong></div><div><small>Urgent issues</small><strong className={location.urgent_issue_count ? "metric-risk-value" : ""}>{number.format(location.urgent_issue_count)}</strong></div></div>
          <div className="analytics-subsection"><div className="analytics-subheading"><strong>Sentiment distribution</strong><Link href={"/reviews?location=" + location.id}>Reviews <ArrowUpRight size={13} /></Link></div>
            {location.analyzed_reviews ? <div className="distribution-list"><DistributionBar label="Positive" count={location.sentiment_counts.positive} total={location.analyzed_reviews} tone="fill-positive" /><DistributionBar label="Neutral" count={location.sentiment_counts.neutral} total={location.analyzed_reviews} tone="fill-neutral" /><DistributionBar label="Negative" count={location.sentiment_counts.negative} total={location.analyzed_reviews} tone="fill-negative" /></div> : <p className="analytics-unclassified">No saved sentiment analysis yet. Analyze reviews to populate these counts.</p>}
          </div>
          <div className="analytics-subsection"><div className="analytics-subheading"><strong>Complaint patterns</strong><span>{number.format(location.complaint_review_count)} reviews</span></div>
            {location.top_categories.length ? <div className="category-bars">{location.top_categories.map((item) => <div className="category-bar-row" key={item.category}><div><span>{item.category.replaceAll("_", " ")}</span><strong>{item.count}</strong></div><span className="distribution-track"><i className="distribution-fill fill-teal" style={{ width: Math.max(4, (item.count / maxCategory) * 100) + "%" }} /></span></div>)}</div> : <p className="analytics-unclassified">No complaint categories are saved yet.</p>}
          </div>
          <div className="analytics-subsection"><div className="analytics-subheading"><strong>Negative review trend</strong><span>30 days</span></div>
            <div className="negative-trend" aria-label={"Negative review counts for " + location.name}>{location.negative_trend.map((point) => <span key={point.day} title={point.day + ": " + point.count + " negative reviews"} style={{ height: Math.max(point.count ? 10 : 3, (point.count / maxNegative) * 100) + "%" }} />)}</div>
            <div className="trend-caption"><span>{location.negative_trend[0]?.day}</span><span>{location.negative_trend.at(-1)?.day}</span></div>
          </div>
        </article>;
      })}
    </section> : <section className="panel"><EmptyState title="No locations in this workspace" description="Locations appear when reviews are imported." /></section>}
    {!loading && data && data.analyzed_reviews === 0 && <div className="analytics-evaluation-note"><strong>Model status:</strong> {status?.sentiment_model || "Unavailable"} · {status?.sentiment_provider || "unknown"} provider. This workspace has stored reviews but none have been analyzed.</div>}
  </div>;
}
