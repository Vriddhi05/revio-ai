import { ArrowDownToLine, ArrowUpRight, CircleAlert, MapPin, MessageSquareText, Star } from "lucide-react";
import SectionHeading from "../../components/ui/SectionHeading";
import EmptyState from "../../components/ui/EmptyState";

const metrics = [
  { label: "Reviews received", icon: MessageSquareText, note: "Awaiting your first import" },
  { label: "Average rating", icon: Star, note: "Calculated from imported reviews" },
  { label: "Needs attention", icon: CircleAlert, note: "Urgency signals will appear here" },
  { label: "Locations", icon: MapPin, note: "Add locations through review data" },
];

export default function OverviewPage() {
  return (
    <div className="overview-page">
      <SectionHeading
        eyebrow="WORKSPACE OVERVIEW"
        title="Your reputation, in focus."
        description="A thoughtful view of what customers are saying across your locations."
        action={<button className="button button-secondary" type="button" disabled aria-disabled="true"><ArrowDownToLine size={16} /> Import reviews <span className="button-soon">SOON</span></button>}
      />

      <div className="demo-notice" role="status">
        <span className="notice-mark">i</span>
        <p><strong>You’re viewing a demo workspace.</strong> No review sources are connected, so no customer activity is shown.</p>
        <span className="notice-label">LOCAL PREVIEW</span>
      </div>

      <section className="metrics-grid" aria-label="Reputation summary">
        {metrics.map(({ label, icon: Icon, note }) => (
          <article className="metric-card" key={label}>
            <div className="metric-card-top"><span>{label}</span><Icon size={17} strokeWidth={1.7} /></div>
            <div className="metric-value" aria-label="No data yet">—</div>
            <p className="metric-note">{note}</p>
          </article>
        ))}
      </section>

      <section className="overview-grid">
        <article className="panel trend-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">YOUR PULSE</p><h2>Reputation over time</h2></div>
            <button className="period-select" type="button" disabled>Last 30 days <span>⌄</span></button>
          </div>
          <EmptyState title="Your story starts with a review" description="Once review data is available, your rating and sentiment trends will take shape here." />
        </article>

        <article className="panel attention-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">ATTENTION</p><h2>Needs your attention</h2></div>
            <span className="panel-icon coral-icon"><CircleAlert size={17} /></span>
          </div>
          <EmptyState title="All quiet for now" description="Urgent feedback and emerging issues will be surfaced here when reviews are connected." />
        </article>
      </section>

      <section className="panel locations-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">ACROSS YOUR BUSINESS</p><h2>Location pulse</h2></div>
          <button className="quiet-link" type="button" disabled>View locations <ArrowUpRight size={15} /></button>
        </div>
        <div className="location-empty-row"><MapPin size={19} /><span>Location comparisons will appear once reviews are imported.</span></div>
      </section>

      <section className="getting-started">
        <div className="getting-started-copy"><span className="step-number">01</span><div><p className="eyebrow">A GOOD PLACE TO BEGIN</p><h2>Bring your customer voice into focus.</h2><p>Import a review export to start seeing patterns across your locations.</p></div></div>
        <button className="button button-dark" type="button" disabled aria-disabled="true">CSV import is coming next <span aria-hidden="true">↗</span></button>
      </section>
    </div>
  );
}
