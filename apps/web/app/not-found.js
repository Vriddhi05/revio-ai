import Link from "next/link";

export default function NotFound() {
  return (
    <main className="not-found">
      <p className="eyebrow">PAGE NOT FOUND</p>
      <h1>That page is still taking shape.</h1>
      <p>This section will appear as REVIO milestones are completed.</p>
      <Link className="button button-primary" href="/">Return to overview</Link>
    </main>
  );
}
