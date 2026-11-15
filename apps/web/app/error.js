"use client";

export default function Error({ reset }) {
  return (
    <section className="error-state" role="alert">
      <span className="error-mark">!</span>
      <p className="eyebrow">SOMETHING WENT AWRY</p>
      <h1>We couldn’t open this view.</h1>
      <p>Your workspace is safe. Try loading the page again.</p>
      <button className="button button-dark" type="button" onClick={() => reset()}>Try again</button>
    </section>
  );
}
