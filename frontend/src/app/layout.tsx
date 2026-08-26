import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BRAHMO Rules Engine",
  description: "BFS Traversal + 5-Check Filter Pipeline · Zero LLM",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
