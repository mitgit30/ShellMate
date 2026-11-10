import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shellmate",
  description: "A clearer, safer way to work with your Linux servers.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return <html lang="en"><body>{children}</body></html>;
}
