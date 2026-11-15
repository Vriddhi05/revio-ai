import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

export default function AppShell({ children }) {
  return (
    <div className="app-frame">
      <Sidebar />
      <div className="workspace-frame">
        <Topbar />
        <main className="main-content">{children}</main>
        <footer className="app-footer">
          <span>REVIO Reputation Intelligence</span>
          <span className="footer-status"><span className="status-dot" /> Demo workspace</span>
        </footer>
      </div>
    </div>
  );
}
