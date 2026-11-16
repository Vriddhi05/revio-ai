"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  BookOpenText,
  ChevronDown,
  CircleHelp,
  LayoutDashboard,
  MessageSquareText,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

const navigation = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Reviews inbox", href: "/reviews", icon: MessageSquareText },
  { label: "Response studio", href: "/response-studio", icon: Sparkles },
  { label: "Crisis monitor", href: "/crisis-monitor", icon: ShieldAlert },
  { label: "Location analytics", href: "/locations", icon: BarChart3 },
  { label: "Knowledge base", href: "/knowledge-base", icon: BookOpenText },
];

function BrandMark() {
  return (
    <Link href="/" className="brand-lockup" aria-label="REVIO home">
      <span className="brand-mark" aria-hidden="true"><Activity size={19} strokeWidth={2.1} /></span>
      <span className="brand-word">revio<span>.</span></span>
    </Link>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <div className="sidebar-brand"><BrandMark /><span className="sidebar-edition">INTELLIGENCE</span></div>

      <button className="workspace-switcher" type="button" aria-label="Current workspace: Demo workspace">
        <span className="workspace-avatar">R</span>
        <span className="workspace-name"><strong>Revio Demo</strong><small>Workspace</small></span>
        <ChevronDown size={15} className="workspace-chevron" />
      </button>

      <div className="nav-section-label">WORKSPACE</div>
      <nav className="primary-nav" aria-label="Primary navigation">
        {navigation.map(({ label, href, icon: Icon, disabled }) => {
          const active = pathname === href;
          const content = <><Icon size={18} strokeWidth={1.8} /><span>{label}</span>{disabled && <span className="nav-soon">SOON</span>}</>;
          return disabled ? (
            <div className="nav-item nav-item-disabled" key={label} aria-disabled="true" title="Planned for a later milestone">{content}</div>
          ) : (
            <Link className={`nav-item${active ? " nav-item-active" : ""}`} href={href} key={label} aria-current={active ? "page" : undefined}>{content}</Link>
          );
        })}
      </nav>

      <div className="sidebar-bottom">
        <div className="sidebar-note"><span className="note-star">✳</span><p>A clearer view of every customer conversation.</p></div>
        <div className="sidebar-utility"><CircleHelp size={16} /><span>Help & support</span></div>
        <div className="sidebar-profile">
          <div className="profile-avatar">RD</div>
          <div className="profile-copy"><strong>Demo account</strong><small>Local preview</small></div>
          <span className="profile-menu" aria-hidden="true">···</span>
        </div>
      </div>
    </aside>
  );
}
