import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "ResolveOS · Operations workbench", description: "Evidence-backed synthetic operations, employee review and independently verified outcomes." };
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}</body></html>; }
