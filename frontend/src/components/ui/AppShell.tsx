"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./AppShell.module.css";

export type NavItem = {
  href: string;
  label: string;
  /** Keep icons playful and light — an emoji works great. */
  icon: React.ReactNode;
};

type AppShellProps = {
  /** Optional page title rendered in a simple top bar. */
  title?: string;
  /** Bottom nav items; omit for full-screen flows (login, sessions). */
  nav?: NavItem[];
  children: React.ReactNode;
};

/**
 * The phone-first app frame: a centered column, an optional title bar,
 * and a fixed bottom nav with big friendly targets. Screens render
 * inside; the shell stays consistent across every phase.
 */
export default function AppShell({ title, nav, children }: AppShellProps) {
  const pathname = usePathname();

  return (
    <div className={styles.shell}>
      {title && (
        <header className={styles.header}>
          <h1 className={styles.title}>{title}</h1>
        </header>
      )}

      <main className={`${styles.main} ${nav ? styles.withNav : ""}`.trim()}>
        {children}
      </main>

      {nav && (
        <nav className={styles.nav} aria-label="Main">
          <div className={styles.navInner}>
            {nav.map((item) => {
              const active =
                pathname === item.href ||
                (item.href !== "/" && pathname.startsWith(`${item.href}/`));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`${styles.navItem} ${active ? styles.active : ""}`.trim()}
                  aria-current={active ? "page" : undefined}
                >
                  <span className={styles.navIcon} aria-hidden="true">
                    {item.icon}
                  </span>
                  {item.label}
                </Link>
              );
            })}
          </div>
        </nav>
      )}
    </div>
  );
}
