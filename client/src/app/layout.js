import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import ClientProvider from "@/components/ClientProvider";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-jakarta"
});

export const metadata = {
  title: "NebulaML - ML Model Training Platform",
  description: "Train and deploy models with ease",
  icons: {
    icon: '/favicon.ico',
    apple: '/apple-touch-icon.png',
  },
};

// Main root layout with providers
export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark">
      <body className={`${jakarta.variable} font-sans antialiased`}>
        <ClientProvider>
          {children}
        </ClientProvider>
      </body>
    </html>
  );
}
