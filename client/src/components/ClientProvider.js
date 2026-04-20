"use client";

import { AuthProvider } from "@/context/AuthContext";
import ChatbotWidget from "@/components/ChatbotWidget";

export default function ClientProvider({ children }) {
  return (
    <AuthProvider>
      {children}
      <ChatbotWidget />
    </AuthProvider>
  );
}

