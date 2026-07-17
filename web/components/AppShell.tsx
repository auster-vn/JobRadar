"use client";

import {
  BarChart3,
  Bell,
  BriefcaseBusiness,
  CircleUserRound,
  Gauge,
  Menu,
  Radar,
  Search,
  WalletCards,
  X,
} from "lucide-react";
import Link from "next/link";
import {usePathname} from "next/navigation";
import type {ReactNode} from "react";
import {useState} from "react";

const navigation = [
  {href: "/", label: "Tổng quan", icon: Gauge},
  {href: "/jobs", label: "Việc làm", icon: BriefcaseBusiness},
  {href: "/market", label: "Thị trường", icon: BarChart3},
  {href: "/salary", label: "Mức lương", icon: WalletCards},
  {href: "/alerts", label: "Thông báo", icon: Bell},
  {href: "/profile", label: "Hồ sơ", icon: CircleUserRound},
];

export function AppShell({children}: {children: ReactNode}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const current = navigation.find((item) => item.href === pathname)?.label ?? "JobRadar";

  return (
    <div className="app-shell">
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="brand">
          <span className="brand-mark"><Radar size={21} strokeWidth={2.3} /></span>
          <span>JobRadar <b>VN</b></span>
          <button className="icon-button sidebar-close" onClick={() => setOpen(false)} aria-label="Đóng menu">
            <X size={19} />
          </button>
        </div>
        <nav className="primary-nav" aria-label="Điều hướng chính">
          {navigation.map(({href, label, icon: Icon}) => {
            const active = href === "/" ? pathname === href : pathname.startsWith(href);
            return (
              <Link href={href} className={active ? "nav-item active" : "nav-item"} key={href} onClick={() => setOpen(false)}>
                <Icon size={19} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-status">
          <span className="status-dot" />
          <div><strong>Dữ liệu hoạt động</strong><small>Cập nhật 4 phút trước</small></div>
        </div>
      </aside>
      {open && <button className="sidebar-scrim" aria-label="Đóng menu" onClick={() => setOpen(false)} />}
      <div className="app-column">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setOpen(true)} aria-label="Mở menu"><Menu size={20} /></button>
          <div className="topbar-title">{current}</div>
          <Link href="/jobs" className="global-search"><Search size={17} /><span>Tìm vai trò, kỹ năng, công ty</span></Link>
          <button className="icon-button notification-button" aria-label="Thông báo"><Bell size={19} /><span /></button>
          <Link href="/profile" className="avatar" aria-label="Hồ sơ">CP</Link>
        </header>
        <main className="main-content">{children}</main>
        <nav className="mobile-nav" aria-label="Điều hướng di động">
          {navigation.slice(0, 5).map(({href, label, icon: Icon}) => {
            const active = href === "/" ? pathname === href : pathname.startsWith(href);
            return <Link href={href} className={active ? "active" : ""} key={href}><Icon size={19} /><span>{label}</span></Link>;
          })}
        </nav>
      </div>
    </div>
  );
}
