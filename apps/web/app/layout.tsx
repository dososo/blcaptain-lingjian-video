import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "灵剪 Video Studio",
  description: "可审核、可复跑、可归档的短视频生产工作台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
