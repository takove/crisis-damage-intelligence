import type { Metadata, Viewport } from "next";
import { Analytics } from "@vercel/analytics/next";
import AnalyticsEvents from "@/components/AnalyticsEvents";
import InstallPrompt from "@/components/InstallPrompt";
import OpenPanelAnalytics from "@/components/OpenPanelAnalytics";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";
import "./globals.css";
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

export const metadata: Metadata = {
  metadataBase: new URL("https://respuestavenezuela.org"),
  applicationName: "Respuesta Venezuela",
  title: "Respuesta Venezuela",
  description: "Bilingual geospatial earthquake response and damage triage platform for Venezuela",
  alternates: {
    canonical: "/",
  },
  appleWebApp: {
    capable: true,
    title: "Respuesta VE",
    statusBarStyle: "default",
  },
  formatDetection: {
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e7e2d8" },
    { media: "(prefers-color-scheme: dark)", color: "#11120f" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className={cn("font-sans", geist.variable)}>
      <body>
        {children}
        <ServiceWorkerRegister />
        <InstallPrompt />
        <AnalyticsEvents />
        <OpenPanelAnalytics />
        <Analytics />
      </body>
    </html>
  );
}
