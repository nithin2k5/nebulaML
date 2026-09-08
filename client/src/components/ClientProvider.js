"use client";

import { AuthProvider } from "@/context/AuthContext";
import ChatbotWidget from "@/components/ChatbotWidget";
import { ConfirmProvider } from "@/components/ui/confirm-dialog";

export default function ClientProvider({ children }) {
  // ConfirmProvider wraps AuthProvider so the session-expiry prompt can use it too.
  return (
    <ConfirmProvider>
      <AuthProvider>
        {children}
        <ChatbotWidget />
      </AuthProvider>
    </ConfirmProvider>
  );
}

