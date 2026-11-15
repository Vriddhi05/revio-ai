"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Check, CircleAlert, RefreshCw, ShieldAlert } from "lucide-react";
import SectionHeading from "../../components/ui/SectionHeading";
import EmptyState from "../../components/ui/EmptyState";
import { apiRequest } from "../../lib/api";

const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 };

export default function CrisisMonitorPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const result = await apiRequest("/crisis/alerts");
      setAlerts(result.sort((left, right) => severityOrder[left.severity] - severityOrder[right.severity] || right.affected_count - left.affected_count));
    } catch (cause) {
      setError(cause.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function analyzeAndScan() {
    setScanning(true); setError(""); setMessage("");
    try {
      const analysis = await apiRequest("/intelligence/analyze?limit=1000", { method: "POST" });
      const result = await apiRequest("/crisis/scan?window_days=14", { method: "POST" });
      setMessage("Analysis checked " + analysis.requested + " reviews. Signal scan found " + result.signals + " current patterns.");
      await load();
      window.dispatchEvent(new Event("revio-data-changed"));
    } catch (cause) {
      setError(cause.message);
    } finally {
      setScanning(false);
    }
  }

  async function updateStatus(alertId, status) {
    try {
      await apiRequest("/crisis/alerts/" + alertId + "/status", { method: "PATCH", body: JSON.stringify({ status }) });
      await load();
    } catch (cause) {
      setError(cause.message);
    }
  }

  const openCount = alerts.filter((alert) => alert.status === "open").length;
  const riskCount = alerts.filter((alert) => alert.severity === "critical" || alert.severity === "high").length;
  const reviewCount = alerts.reduce((sum, alert) => sum + alert.affected_count, 0);

  return <div className="intelligence-page">
    <SectionHeading eyebrow="EARLY SIGNALS" title="Crisis monitor" description="Review emerging patterns and route them to a human owner for verification." action={<button className="button button-secondary" type="button" onClick={analyzeAndScan} disabled={scanning}><RefreshCw size={15} className={scanning ? "icon-spinning" : ""} />{scanning ? "Scanning…" : "Analyze & scan"}</button>} />
    <div className="demo-notice"><span className="notice-mark">i</span><p><strong>DEMO / SYNTHETIC DATA.</strong> Alerts are automated signals from fictional Indian examples, not confirmed real-world incidents.</p><span className="notice-label">SIGNAL ONLY</span></div>
    {message && <div className="analysis-message" role="status">{message}</div>}
    {error && <div className="inline-error" role="alert"><strong>Crisis monitor unavailable.</strong> {error} <button type="button" onClick={load}>Retry</button></div>}

    <section className="metrics-grid intelligence-metrics" aria-label="Crisis monitor summary" aria-busy={loading}>
      <article className="metric-card"><div className="metric-card-top"><span>Open signals</span><ShieldAlert size={17} /></div><div className="metric-value">{loading ? "—" : openCount}</div><p className="metric-note">Awaiting human review</p></article>
      <article className="metric-card"><div className="metric-card-top"><span>High or critical</span><CircleAlert size={17} /></div><div className="metric-value metric-risk-value">{loading ? "—" : riskCount}</div><p className="metric-note">Priority review signals</p></article>
      <article className="metric-card"><div className="metric-card-top"><span>Review references</span><ArrowUpRight size={17} /></div><div className="metric-value">{loading ? "—" : reviewCount}</div><p className="metric-note">References can overlap across signals</p></article>
      <article className="metric-card"><div className="metric-card-top"><span>Detection window</span><RefreshCw size={17} /></div><div className="metric-value">14 days</div><p className="metric-note">Configured rolling comparison</p></article>
    </section>

    {loading ? <section className="intelligence-loading" aria-busy="true"><span /><span /><span /></section> : error && !alerts.length ? null : alerts.length ? <section className="signal-list" aria-label="Detected crisis signals">
      {alerts.map((alert) => <article className="signal-card" key={alert.id}>
        <div className="signal-card-top"><span className={"severity-pill severity-" + alert.severity}>{alert.severity}</span><span className="signal-status">{alert.status.replaceAll("_", " ")}</span><span className="signal-window">{alert.window_start} — {alert.window_end}</span></div>
        <div className="signal-card-heading"><div><p className="eyebrow">{alert.signal_type.replaceAll("_", " ")}</p><h2>{alert.title}</h2></div><span className="signal-count">{alert.affected_count}<small>reviews</small></span></div>
        <p className="signal-reason">{alert.reason}</p>
        <div className="signal-context"><span><strong>Location</strong>{alert.location || "Across multiple locations"}</span><span><strong>Status</strong>{alert.confirmed ? "Confirmed by a human" : "Automated signal · unconfirmed"}</span></div>
        <div className="signal-action"><strong>Recommended next step</strong><p>{alert.recommended_action}</p></div>
        <div className="signal-references"><strong>Supporting reviews</strong>{alert.supporting_reviews.map((review) => <Link key={review.id} href={"/reviews?review=" + review.id} className="signal-reference"><span><b>{review.author_name || "Anonymous"} · {review.location}</b><small>{review.text_excerpt}</small></span><ArrowUpRight size={14} /></Link>)}</div>
        <div className="signal-card-footer"><span>{alert.supporting_reviews.some((review) => review.is_synthetic) ? "Includes DEMO / SYNTHETIC DATA" : "Imported workspace reviews"}</span><div>{alert.status === "open" && <button className="button button-secondary button-compact" type="button" onClick={() => updateStatus(alert.id, "acknowledged")}><Check size={14} />Acknowledge</button>}{alert.status !== "resolved" && alert.status !== "stale" && <button className="text-action" type="button" onClick={() => updateStatus(alert.id, "resolved")}>Mark reviewed<Check size={14} /></button>}</div></div>
      </article>)}
    </section> : <section className="panel crisis-empty"><EmptyState title="No saved signals yet" description="Analyze workspace reviews and scan the rolling window. Any detected pattern remains unconfirmed until a person verifies it." actionLabel={scanning ? "Scanning…" : "Analyze and scan"} onAction={analyzeAndScan} /></section>}
  </div>;
}
