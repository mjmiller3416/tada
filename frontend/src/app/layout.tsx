import type { Metadata, Viewport } from "next";
import { Nunito } from "next/font/google";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";
import "./globals.css";

/* Two weights only (SPEC §5): regular 500, bold 800. */
const nunito = Nunito({
  subsets: ["latin"],
  weight: ["500", "800"],
  variable: "--font-nunito",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Tada",
  description: "A private household cleaning coach.",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/icons/tada.svg", type: "image/svg+xml" },
      { url: "/icons/icon-192.png", type: "image/png", sizes: "192x192" },
    ],
    apple: "/icons/icon-192.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#E15B54",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={nunito.variable}>
      <body>
        <ServiceWorkerRegister />
        {children}
      </body>
    </html>
  );
}
