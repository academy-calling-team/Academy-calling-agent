import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: '학원의신 | AI 상담',
  description: '학원의신 AI 상담과 회원 관리',
  icons: { icon: '/brand-mark.svg' },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="antialiased">{children}</body>
    </html>
  );
}
