import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "claw-assistant Dashboard",
  description: "Human-in-the-Loop AI 态势看板",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased min-h-screen bg-slate-50 text-slate-900">
        {children}
      </body>
    </html>
  );
}
