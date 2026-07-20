import type { Metadata, Viewport } from "next";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tada",
  description: "A private household cleaning coach.",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#D85A30",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0 }}>
        <ServiceWorkerRegister />
        {children}
      </body>
    </html>
  );
}
