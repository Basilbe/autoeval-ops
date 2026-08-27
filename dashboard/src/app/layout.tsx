import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoEvalOps",
  description: "Automated LLM prompt evaluation on every pull request.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className="bg-ink text-bone font-mono antialiased">{children}</body>
      </html>
    </ClerkProvider>
  );
}