"use client";

import {
  BarChart3,
  Bell,
  BriefcaseBusiness,
  CircleUserRound,
  ClipboardList,
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
import {useEffect, useRef, useState} from "react";

import {SessionControl} from "./SessionControl";

const navigation = [
  {href: "/", label: "Tổng quan", icon: Gauge},
  {href: "/jobs", label: "Việc làm", icon: BriefcaseBusiness},
  {href: "/applications", label: "Ứng tuyển", icon: ClipboardList},
  {href: "/market", label: "Thị trường", icon: BarChart3},
  {href: "/salary", label: "Mức lương", icon: WalletCards},
  {href: "/alerts", label: "Thông báo", icon: Bell},
  {href: "/profile", label: "Hồ sơ", icon: CircleUserRound},
];

const mobileNavigation = [navigation[0], navigation[1], navigation[2], navigation[5], navigation[6]];

export function AppShell({children}: {children: ReactNode}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const current = navigation.find((item) => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href))?.label ?? "JobRadar";

  useEffect(() => {
    if (!open) return;
    closeButton.current?.focus();
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        menuButton.current?.focus();
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Chuyển đến nội dung chính</a>
      <aside id="primary-sidebar" className={`sidebar ${open ? "sidebar-open" : ""}`} aria-label="Điều hướng ứng dụng">
        <div className="brand">
          <span className="brand-mark"><Radar size={21} strokeWidth={2.3} /></span>
          <span>JobRadar <b>VN</b></span>
          <button ref={closeButton} type="button" className="icon-button sidebar-close" onClick={() => { setOpen(false); menuButton.current?.focus(); }} aria-label="Đóng menu">
            <X size={19} />
          </button>
        </div>
        <nav className="primary-nav" aria-label="Điều hướng chính">
          {navigation.map(({href, label, icon: Icon}) => {
            const active = href === "/" ? pathname === href : pathname.startsWith(href);
            return (
              <Link href={href} className={active ? "nav-item active" : "nav-item"} key={href} onClick={() => setOpen(false)} aria-current={active ? "page" : undefined}>
                <Icon size={19} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-status">
          <Radar size={16} />
          <div><strong>JobRadar SaaS</strong><small>Dữ liệu từ nguồn công khai</small></div>
        </div>
      </aside>
      {open && <button type="button" className="sidebar-scrim" aria-label="Đóng menu" onClick={() => { setOpen(false); menuButton.current?.focus(); }} />}
      <div className="app-column">
        <header className="topbar">
          <button ref={menuButton} type="button" className="icon-button menu-button" onClick={() => setOpen(true)} aria-label="Mở menu" aria-expanded={open} aria-controls="primary-sidebar"><Menu size={20} /></button>
          <div className="topbar-title">{current}</div>
          <Link href="/jobs" className="global-search" aria-label="Tìm vai trò, kỹ năng hoặc công ty"><Search size={17} /><span>Tìm vai trò, kỹ năng, công ty</span></Link>
          <Link href="/alerts" className="icon-button notification-button" aria-label="Mở cảnh báo việc làm"><Bell size={19} /></Link>
          <SessionControl />
        </header>
        <main id="main-content" className="main-content">{children}</main>
        <nav className="mobile-nav" aria-label="Điều hướng di động">
          {mobileNavigation.map(({href, label, icon: Icon}) => {
            const active = href === "/" ? pathname === href : pathname.startsWith(href);
            return <Link href={href} className={active ? "active" : ""} key={href} aria-current={active ? "page" : undefined}><Icon size={19} /><span>{label}</span></Link>;
          })}
        </nav>
      </div>
    </div>
  );
}
