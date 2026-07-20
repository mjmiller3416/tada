import type { NavItem } from "@/components/ui";

/** The one bottom nav, shared by every top-level screen. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Today", icon: "🏠" },
  { href: "/rooms", label: "Rooms", icon: "🛋️" },
  { href: "/tasks", label: "Tasks", icon: "🧺" },
  { href: "/supplies", label: "Supplies", icon: "🧴" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];
