import "@fontsource-variable/manrope";
import type {Metadata} from "next";
import type {ReactNode} from "react";

import {AppShell} from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: {default: "JobRadar VN", template: "%s | JobRadar VN"},
  description: "Dữ liệu thị trường việc làm công nghệ Việt Nam",
};

export default function RootLayout({children}: Readonly<{children: ReactNode}>) {
  return (
    <html lang="vi">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
