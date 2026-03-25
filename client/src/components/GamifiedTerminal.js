"use client";

import React, { useEffect, useRef, useState } from 'react';
import { Terminal as TerminalIcon, Maximize2, Minimize2, Send } from 'lucide-react';
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function GamifiedTerminal({ output, onCommand, isRunning = false }) {
    const [logs, setLogs] = useState([]);
    const [input, setInput] = useState("");
    const [isMaximized, setIsMaximized] = useState(false);
    const bottomRef = useRef(null);

    // Parse and process incoming output
    useEffect(() => {
        if (output == null || output === "") {
            setLogs([]);
            return;
        }

        const text = typeof output === "string" ? output : JSON.stringify(output, null, 2);
        const lines = text.split("\n");
        setLogs(lines);
    }, [output]);

    // Auto-scroll to bottom
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [logs]);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!input.trim()) return;

        // Allow parent to handle command, or handle locally
        if (onCommand) {
            onCommand(input);
        }
        setInput("");
    };

    return (
        <div
            className={cn(
                "relative flex flex-col bg-black/90 font-mono text-sm border border-white/10 overflow-hidden shadow-2xl transition-all duration-300",
                isMaximized ? "fixed inset-4 z-50 rounded-lg" : "rounded-xl h-[400px] w-full"
            )}
        >
            {/* Scanline Effect - using repetitive gradient */}
            <div
                className="absolute inset-0 pointer-events-none z-10"
                style={{
                    background: "linear-gradient(rgba(18,16,16,0) 50%, rgba(0,0,0,0.25) 50%), linear-gradient(90deg, rgba(255,0,0,0.06), rgba(0,255,0,0.02), rgba(0,0,255,0.06))",
                    backgroundSize: "100% 2px, 3px 100%"
                }}
            />

            {/* CRT Flicker */}
            <div className="absolute inset-0 pointer-events-none bg-white/5 opacity-[0.03] animate-pulse z-20" />

            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 bg-white/5 backdrop-blur z-30">
                <div className="flex items-center gap-2">
                    <div className="flex gap-1.5">
                        <div className="w-3 h-3 rounded-full bg-red-500/80" />
                        <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
                        <div className="w-3 h-3 rounded-full bg-green-500/80" />
                    </div>
                    <span className="ml-3 text-xs text-gray-400 flex items-center gap-2">
                        <TerminalIcon size={12} />
                        NEBULA_OS_V2.0
                        {isRunning && (
                            <span className="flex items-center gap-1 text-amber-400">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
                                running
                            </span>
                        )}
                    </span>
                </div>

                <div className="flex items-center gap-2">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-gray-400 hover:text-white"
                        onClick={() => setIsMaximized(!isMaximized)}
                    >
                        {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                    </Button>
                </div>
            </div>

            {/* Terminal Output */}
            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar relative z-0">
                <div className="space-y-1 pb-4">
                    {logs.map((line, i) => (
                        <div key={i} className="text-green-400/90 text-shadow-glow break-all flex group hover:bg-white/5 p-0.5 rounded transition-colors">
                            <span className="mr-2 text-green-600/50 select-none">➜</span>
                            <span className="font-mono tracking-wide">{line}</span>
                        </div>
                    ))}

                    {logs.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-full text-gray-600/50 italic mt-20 gap-2">
                            <span className="animate-pulse">Waiting for system output...</span>
                        </div>
                    )}

                    <div ref={bottomRef} />
                </div>
            </div>

            {/* Input Area */}
            <div className="p-2 border-t border-white/10 bg-black/40 backdrop-blur z-30">
                <form onSubmit={handleSubmit} className="flex items-center gap-2">
                    <span className="text-green-500 font-bold animate-pulse pl-2">❯</span>
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        className="flex-1 bg-transparent border-none outline-none text-green-300 placeholder-green-700/30 font-mono h-8"
                        placeholder="Enter system command..."
                    />
                    <Button
                        type="submit"
                        size="sm"
                        variant="ghost"
                        className="text-green-500 hover:text-green-300 hover:bg-green-500/10 h-8 w-8 p-0"
                    >
                        <Send size={14} />
                    </Button>
                </form>
            </div>

            <style jsx global>{`
        .text-shadow-glow {
            text-shadow: 0 0 5px rgba(74, 222, 128, 0.5);
        }
      `}</style>
        </div>
    );
}
