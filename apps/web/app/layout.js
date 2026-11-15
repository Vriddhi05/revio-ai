import "./styles/tokens.css";
import "./styles/globals.css";
import AppShell from "../components/layout/AppShell";

export const metadata = {
  title: "REVIO — Reputation Intelligence",
  description: "A thoughtful workspace for customer reputation intelligence.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
