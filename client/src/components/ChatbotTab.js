"use client";

import { useState, useRef, useEffect } from "react";
import { Send, User, Loader2, Plus, Mic, Sparkles, Image as ImageIcon, Video, Cpu, Code } from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

export default function ChatbotTab() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = (e, customInput = null) => {
    if (e) e.preventDefault();
    const finalInput = customInput || input;
    if (!finalInput.trim() || isLoading) return;

    const userMessage = { role: "user", content: finalInput.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "I've received your request! Our servers are processing the task and will get back to you shortly.",
        },
      ]);
      setIsLoading(false);
    }, 1500);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const isInitialState = messages.length === 0;

  const suggestions = [
    { icon: ImageIcon, text: "Annotate my latest dataset" },
    { icon: Cpu, text: "Train a YOLOv11 model" },
    { icon: Video, text: "Run inference on a video" },
    { icon: Code, text: "Generate API integration code" },
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] relative font-sans overflow-hidden w-full">
      
      {/* Background Ambience */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] rounded-full bg-indigo-600/10 blur-[120px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-violet-600/10 blur-[120px]" />
      </div>

      <AnimatePresence mode="wait">
        {isInitialState ? (
          <motion.div 
            key="initial"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -20, transition: { duration: 0.3 } }}
            className="flex-1 flex flex-col items-center justify-center p-6 w-full h-full relative z-10"
          >
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1, duration: 0.5, ease: "easeOut" }}
              className="w-full max-w-4xl flex flex-col items-center"
            >
              <div className="mb-8 flex items-center justify-center">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-[0_0_40px_rgba(99,102,241,0.4)] border border-white/20 mb-6 relative overflow-hidden">
                   <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(255,255,255,0.4),transparent_50%)]"></div>
                  <Sparkles className="w-8 h-8 text-white relative z-10" />
                </div>
              </div>
              
              <h2 className="text-4xl md:text-5xl font-bold mb-12 tracking-tight text-center">
                <span className="bg-clip-text text-transparent bg-gradient-to-r from-white via-gray-200 to-gray-500">
                  How can I accelerate your work today?
                </span>
              </h2>
              
              <div className="w-full max-w-3xl relative group mb-14">
                {/* Glow behind input */}
                <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-[2rem] blur opacity-25 group-hover:opacity-40 transition duration-1000 group-hover:duration-200"></div>
                
                <form
                  onSubmit={(e) => handleSubmit(e)}
                  className="relative flex items-center bg-zinc-900/80 backdrop-blur-xl border border-white/10 rounded-full overflow-hidden focus-within:border-indigo-500/50 focus-within:bg-zinc-900 transition-all duration-300 shadow-2xl"
                >
                  <div className="pl-6 pr-3 text-indigo-400">
                    <Sparkles className="w-6 h-6" />
                  </div>
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask Nebula AI anything..."
                    className="flex-1 bg-transparent text-gray-100 placeholder:text-gray-500 px-2 py-5 focus:outline-none text-lg"
                  />
                  <div className="pr-3 pl-2 flex items-center gap-2">
                    {input.trim() ? (
                      <button
                        type="submit"
                        className="flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-white hover:scale-105 transition-all shadow-lg shadow-indigo-500/25"
                      >
                        <Send className="w-5 h-5 ml-0.5" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/5 hover:bg-white/10 text-gray-300 transition-colors text-sm font-medium border border-white/5"
                      >
                        <Mic className="w-4 h-4 text-indigo-400" />
                        <span className="hidden sm:inline">Voice</span>
                      </button>
                    )}
                  </div>
                </form>
              </div>

              {/* Suggestions Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-3xl">
                {suggestions.map((item, i) => (
                  <motion.button
                    key={i}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 + (i * 0.1) }}
                    onClick={() => handleSubmit(null, item.text)}
                    className="flex items-center gap-4 p-4 rounded-2xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.06] hover:border-indigo-500/30 transition-all group text-left backdrop-blur-sm"
                  >
                    <div className="w-10 h-10 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-400 group-hover:bg-indigo-500/20 group-hover:scale-110 transition-all shadow-[0_0_15px_rgba(99,102,241,0)] group-hover:shadow-[0_0_15px_rgba(99,102,241,0.2)] border border-indigo-500/10">
                      <item.icon className="w-5 h-5" />
                    </div>
                    <span className="text-gray-400 group-hover:text-gray-200 text-sm font-medium transition-colors">
                      {item.text}
                    </span>
                  </motion.button>
                ))}
              </div>
            </motion.div>
          </motion.div>
        ) : (
          // Chat Interface State
          <motion.div 
            key="chat"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col h-full w-full relative z-10"
          >
            <div className="flex-1 overflow-y-auto p-4 md:p-8 custom-scrollbar space-y-8">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={cn(
                    "flex gap-4 max-w-4xl mx-auto w-full animate-in fade-in slide-in-from-bottom-4 duration-300 fill-mode-both",
                    msg.role === "assistant" ? "justify-start" : "justify-end"
                  )}
                >
                  {/* Assistant Avatar */}
                  {msg.role === "assistant" && (
                    <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shrink-0 border border-white/10 shadow-[0_0_15px_rgba(99,102,241,0.3)] mt-1">
                      <Sparkles className="w-4 h-4 text-white" />
                    </div>
                  )}

                  {/* Message Bubble */}
                  <div
                    className={cn(
                      "px-6 py-4 rounded-2xl max-w-[85%] text-[15px] leading-relaxed shadow-sm",
                      msg.role === "assistant"
                        ? "bg-white/[0.03] border border-white/[0.05] text-gray-200 rounded-tl-sm backdrop-blur-md"
                        : "bg-gradient-to-br from-indigo-500 to-violet-600 text-white rounded-tr-sm shadow-indigo-500/20"
                    )}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                </div>
              ))}

              {isLoading && (
                <div className="flex gap-4 max-w-4xl mx-auto w-full justify-start animate-in fade-in duration-300">
                   <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shrink-0 border border-white/10 shadow-[0_0_15px_rgba(99,102,241,0.3)] mt-1">
                      <Sparkles className="w-4 h-4 text-white" />
                    </div>
                   <div className="px-5 py-4 rounded-2xl bg-white/[0.03] border border-white/[0.05] flex items-center space-x-2 rounded-tl-sm backdrop-blur-md">
                      <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.5, delay: 0 }} className="w-2 h-2 bg-indigo-400 rounded-full" />
                      <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.5, delay: 0.2 }} className="w-2 h-2 bg-indigo-400 rounded-full" />
                      <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.5, delay: 0.4 }} className="w-2 h-2 bg-indigo-400 rounded-full" />
                    </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Bottom Input Area */}
            <div className="p-6">
              <div className="max-w-4xl mx-auto relative group">
                <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 to-violet-600 rounded-[2rem] blur opacity-10 group-hover:opacity-20 transition duration-500"></div>
                <form
                  onSubmit={(e) => handleSubmit(e)}
                  className="relative flex items-center bg-zinc-900/90 backdrop-blur-xl border border-white/10 hover:border-white/20 rounded-full overflow-hidden focus-within:border-indigo-500/50 focus-within:bg-zinc-900 transition-all duration-300 shadow-xl"
                >
                  <div className="pl-5 pr-2 text-indigo-400">
                    <Sparkles className="w-5 h-5" />
                  </div>
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask Nebula AI..."
                    className="flex-1 bg-transparent text-gray-100 placeholder:text-gray-500 px-2 py-4 focus:outline-none text-[15px]"
                  />
                  <div className="pr-2 pl-2">
                    {input.trim() ? (
                      <button
                        type="submit"
                        disabled={isLoading}
                        className="flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-white hover:scale-105 transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50"
                      >
                        <Send className="w-4 h-4 ml-0.5" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 hover:bg-white/10 text-gray-300 transition-colors text-sm font-medium border border-white/5"
                      >
                        <Mic className="w-4 h-4 text-indigo-400" />
                        <span className="hidden sm:inline">Voice</span>
                      </button>
                    )}
                  </div>
                </form>
                <div className="text-center mt-3">
                  <p className="text-[11px] text-gray-500 font-medium tracking-wide">
                    Nebula AI can make mistakes. Verify important information.
                  </p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
