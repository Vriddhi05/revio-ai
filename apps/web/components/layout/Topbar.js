"use client";

import { usePathname } from "next/navigation";
import { Bell, ChevronDown, Menu } from "lucide-react";

export default function Topbar() {
  const pathname = usePathname();
  const currentPage = pathname === "/reviews" ? "Reviews inbox"
    : pathname === "/crisis-monitor" ? "Crisis monitor"
      : pathname === "/locations" ? "Location analytics"
        : pathname === "/knowledge-base" ? "Knowledge base"
        : pathname === "/" ? "Overview" : "Workspace";
  return (
    <header className="topbar">
      <button className="mobile-menu" aria-label="Open navigation" type="button"><Menu size={20} /></button>
      <div className="breadcrumbs"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{currentPage}</strong></div>
      <div className="topbar-actions">
        <span className="workspace-badge"><span className="status-dot" /> Demo workspace</span>
        <span className="topbar-divider" />
        <button className="icon-button notification-button" type="button" aria-label="Notifications are not available yet"><Bell size={18} /><span className="notification-dot" /></button>
        <button className="topbar-avatar" type="button" aria-label="Demo account menu">RD<ChevronDown size={13} /></button>
      </div>
    </header>
  );
}
