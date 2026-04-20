"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Sparkles, User, Loader2, MessageSquare, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { usePathname } from "next/navigation";

export default function ChatbotWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();
  
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hello! I am Nebula AI. How can I accelerate your ML pipeline today?",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen]);

  // Do not render on landing pages
  if (pathname === "/" || pathname === "/home" || pathname === "/login" || pathname === "/register") {
    return null;
  }

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = { role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    // Mock response delay
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "I'm a placeholder for the future LLM response. Currently, I just echo that I've received your message!",
        },
      ]);
      setIsLoading(false);
    }, 1200);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end font-sans">
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95, transformOrigin: "bottom right" }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="mb-6 w-[360px] sm:w-[420px] h-[550px] max-h-[calc(100vh-140px)] rounded-3xl bg-zinc-950/80 backdrop-blur-3xl overflow-hidden shadow-[0_0_80px_rgba(99,102,241,0.15)] flex flex-col border border-white/[0.08]"
          >
            {/* Header */}
            <div className="relative p-5 border-b border-white/[0.05] flex items-center justify-between bg-gradient-to-r from-indigo-500/10 to-purple-500/10 overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(99,102,241,0.15),transparent_50%)]"></div>
              <div className="relative flex items-center gap-4 z-10">
                <div className="relative">
                  <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30 border border-white/20">
                    <Sparkles className="w-5 h-5 text-white" />
                  </div>
                  <div className="absolute -bottom-1 -right-1 w-3 h-3 rounded-full bg-emerald-400 border-2 border-zinc-950"></div>
                </div>
                <div>
                  <h3 className="font-semibold text-white tracking-tight text-sm">Nebula AI</h3>
                  <p className="text-xs text-indigo-200/60 font-medium">Always active</p>
                </div>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="relative z-10 w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center text-gray-400 hover:text-white transition-colors border border-white/5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-5 custom-scrollbar space-y-6 relative">
              <div className="absolute inset-0 bg-grid-white/[0.01] bg-[length:20px_20px] pointer-events-none" />
              {messages.map((msg, idx) => (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                  key={idx}
                  className={cn(
                    "flex gap-3 w-full relative z-10",
                    msg.role === "assistant" ? "justify-start" : "justify-end"
                  )}
                >
                  {/* Assistant Avatar */}
                  {msg.role === "assistant" && (
                    <div className="w-7 h-7 rounded-full bg-indigo-500/20 flex items-center justify-center shrink-0 border border-indigo-500/30 mt-1 shadow-[0_0_15px_rgba(99,102,241,0.2)]">
                      <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                    </div>
                  )}

                  {/* Message Bubble */}
                  <div
                    className={cn(
                      "px-4 py-3 rounded-2xl max-w-[82%] text-[13px] leading-relaxed shadow-sm",
                      msg.role === "assistant"
                        ? "bg-white/[0.03] border border-white/[0.05] text-gray-200 rounded-tl-sm"
                        : "bg-gradient-to-br from-indigo-500 to-violet-600 text-white rounded-tr-sm shadow-indigo-500/20"
                    )}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                </motion.div>
              ))}

              {isLoading && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex gap-3 w-full justify-start relative z-10"
                >
                  <div className="w-7 h-7 rounded-full bg-indigo-500/20 flex items-center justify-center shrink-0 border border-indigo-500/30 mt-1 shadow-[0_0_15px_rgba(99,102,241,0.2)]">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  </div>
                  <div className="px-4 py-3 rounded-2xl bg-white/[0.03] border border-white/[0.05] flex items-center rounded-tl-sm space-x-1.5">
                    <motion.div animate={{ opacity: [0.4, 1, 0.4] }} transition={{ repeat: Infinity, duration: 1.5, delay: 0 }} className="w-1.5 h-1.5 bg-indigo-400 rounded-full" />
                    <motion.div animate={{ opacity: [0.4, 1, 0.4] }} transition={{ repeat: Infinity, duration: 1.5, delay: 0.2 }} className="w-1.5 h-1.5 bg-indigo-400 rounded-full" />
                    <motion.div animate={{ opacity: [0.4, 1, 0.4] }} transition={{ repeat: Infinity, duration: 1.5, delay: 0.4 }} className="w-1.5 h-1.5 bg-indigo-400 rounded-full" />
                  </div>
                </motion.div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="p-4 bg-black/40 border-t border-white/[0.05] backdrop-blur-md">
              <form
                onSubmit={handleSubmit}
                className="relative flex items-end bg-white/[0.03] border border-white/[0.08] rounded-2xl overflow-hidden focus-within:border-indigo-500/50 focus-within:bg-white/[0.05] transition-all shadow-inner"
              >
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask Nebula AI..."
                  className="w-full bg-transparent text-gray-200 placeholder:text-gray-500 px-4 py-3.5 focus:outline-none resize-none min-h-[52px] max-h-32 text-sm leading-relaxed"
                  rows={1}
                />
                <div className="p-2 shrink-0">
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    type="submit"
                    disabled={!input.trim() || isLoading}
                    className="w-9 h-9 rounded-xl flex items-center justify-center bg-indigo-500 text-white disabled:opacity-40 disabled:bg-white/10 transition-colors shadow-lg shadow-indigo-500/25"
                  >
                    <Send className="w-4 h-4 ml-0.5" />
                  </motion.button>
                </div>
              </form>
              <div className="mt-2 text-center">
                <span className="text-[10px] text-gray-500 font-medium tracking-wide">AI can make mistakes. Verify important info.</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Floating Action Button */}
      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setIsOpen(!isOpen)}
        className="relative group w-16 h-16 rounded-full flex items-center justify-center z-50 border border-white/10 outline-none"
      >
        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 opacity-80 blur-md group-hover:opacity-100 transition-opacity duration-500 animate-pulse" />
        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500" />
        <div className="absolute inset-[1px] rounded-full bg-zinc-950/20 backdrop-blur-sm" />
        <div className="relative text-white drop-shadow-md">
          {isOpen ? <X className="w-6 h-6" /> : <Sparkles className="w-7 h-7" />}
        </div>
      </motion.button>
    </div>
  );
}
