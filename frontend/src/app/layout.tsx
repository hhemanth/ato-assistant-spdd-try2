import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { PredominantDisclaimer } from "@/components/PredominantDisclaimer";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ATO Assistant",
  description:
    "Cited answers to Australian tax questions, grounded in ato.gov.au.",
};

/**
 * T055 [US1] Root layout mounts the predominant disclaimer above every
 * page's `{children}` slot so users see the APP 8 / cross-border /
 * "not personal advice" notice before any chat input is possible
 * (FR-002, US1 acceptance scenario 3). A skip-to-main link plus a
 * `<main id="main">` landmark prep for WCAG 2.4.1 + 2.2 AA (FR-011a).
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-white focus:dark:bg-zinc-900 focus:text-zinc-900 focus:dark:text-zinc-100 focus:px-3 focus:py-1 focus:rounded-md focus:outline focus:outline-2 focus:outline-blue-500"
        >
          Skip to main content
        </a>
        <div className="max-w-3xl mx-auto w-full px-4">
          <PredominantDisclaimer />
        </div>
        <main id="main" className="flex-1 flex flex-col">
          {children}
        </main>
      </body>
    </html>
  );
}
