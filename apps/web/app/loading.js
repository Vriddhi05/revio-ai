export default function Loading() {
  return (
    <div className="overview-page loading-page" aria-label="Loading workspace" aria-busy="true">
      <div className="loading-title"><span /><span /><span /></div>
      <div className="loading-cards">{[1, 2, 3, 4].map((item) => <span className="loading-card" key={item} />)}</div>
      <div className="loading-panels"><span /><span /></div>
      <p className="loading-caption">Opening your workspace…</p>
    </div>
  );
}
