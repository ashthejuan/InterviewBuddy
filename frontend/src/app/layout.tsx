import type { Metadata } from "next";
import type { CSSProperties, ReactNode } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import { cn } from "@/lib/utils";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "InterviewBuddy",
  description: "Voice mock interviews with evidence-backed feedback",
};

const displayFontStyle = {
  "--font-display": "'SF Pro Display', var(--font-sans), Georgia, serif",
  "--font-serif": "Georgia, 'Arizona', serif",
} as CSSProperties;

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en" className={cn(inter.variable, mono.variable)} style={displayFontStyle}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
