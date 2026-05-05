"use client";

import { AuthProvider } from "@/context/AuthContext";
import ChatbotWidget from "@/components/ChatbotWidget";
import CustomCursor from "@/components/CustomCursor";

export default function ClientProvider({ children }) {
  return (
    <AuthProvider>
      <CustomCursor />
      {children}
      <ChatbotWidget />
    </AuthProvider>
  );
}

