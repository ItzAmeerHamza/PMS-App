import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PharmaCare owner",
  description: "Read-only view of shop inventory, patients, and prescriptions.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
