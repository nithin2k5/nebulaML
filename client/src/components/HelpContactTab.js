"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { API_BASE_URL } from "@/lib/config";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import {
  LifeBuoy,
  BookOpen,
  MessageSquare,
  Settings,
  Mail,
  ChevronDown,
  ExternalLink,
  Send,
} from "lucide-react";

const SUPPORT_EMAIL =
  process.env.NEXT_PUBLIC_SUPPORT_EMAIL || "support@nebulaml.com";

const FAQ_ITEMS = [
  {
    question: "What models does NebulaML support?",
    answer:
      "NebulaML supports the Ultralytics YOLO ecosystem (v8 and newer) for object detection, segmentation, and classification.",
  },
  {
    question: "Can I export my datasets and models?",
    answer:
      "Yes. Export datasets in standard YOLO format and download trained weights (.pt) or export to ONNX and other formats from the Models tab.",
  },
  {
    question: "How does au work?",
    answer:
      "Upload images to a project and use au tools in the annotate view. Proposed boxes and masks can be accepted or adjusted before training.",
  },
  {
    question: "Where can I check if the platform is online?",
    answer:
      "Open Settings in the sidebar to see backend health and system status.",
  },
];

function FAQItem({ question, answer }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-white/5 last:border-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full py-4 flex items-center justify-between text-left gap-4 group"
      >
        <span className="text-sm font-medium text-white group-hover:text-violet-400 transition-colors">
          {question}
        </span>
        <ChevronDown
          className={cn(
            "w-4 h-4 shrink-0 text-gray-500 transition-transform",
            open && "rotate-180"
          )}
        />
      </button>
      {open && (
        <p className="pb-4 text-sm text-gray-400 leading-relaxed">{answer}</p>
      )}
    </div>
  );
}

export default function HelpContactTab({ onNavigate }) {
  const { user } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    name: "",
    email: "",
    subject: "",
    category: "general",
    message: "",
  });

  useEffect(() => {
    if (!user) return;
    setForm((prev) => ({
      ...prev,
      name: prev.name || user.username || "",
      email: prev.email || user.email || "",
    }));
  }, [user]);

  const quickLinks = [
    {
      icon: BookOpen,
      title: "API documentation",
      description: "Explore REST endpoints and integration examples.",
      action: () => window.open(`${API_BASE_URL}/docs`, "_blank", "noopener,noreferrer"),
    },
    {
      icon: MessageSquare,
      title: "AI assistant",
      description: "Ask questions about training, datasets, and deployment.",
      action: () => onNavigate?.("chat"),
    },
    {
      icon: Settings,
      title: "System status",
      description: "Check backend connectivity and platform health.",
      action: () => onNavigate?.("settings"),
    },
  ];

  const handleChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmedMessage = form.message.trim();
    if (!form.name.trim() || !form.email.trim() || !trimmedMessage) {
      toast.error("Please fill in your name, email, and message.");
      return;
    }

    setSubmitting(true);
    const subject =
      form.subject.trim() ||
      `[NebulaML] ${form.category.replace(/_/g, " ")} inquiry`;
    const body = [
      `Name: ${form.name.trim()}`,
      `Email: ${form.email.trim()}`,
      `Category: ${form.category}`,
      "",
      trimmedMessage,
    ].join("\n");

    const mailto = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    window.location.href = mailto;
    toast.success("Opening your email app to send the message.");
    setSubmitting(false);
  };

  return (
    <div className="space-y-10 animate-fade-in text-gray-100">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-none bg-violet-400/10 border border-violet-500/20 flex items-center justify-center">
            <LifeBuoy className="w-5 h-5 text-violet-400" />
          </div>
          <h2 className="text-3xl font-bold tracking-tight    bg-clip-text text-transparent">
            Help &amp; Contact Us
          </h2>
        </div>
        <p className="text-muted-foreground max-w-2xl">
          Find answers, open documentation, or reach our team for product support and
          feedback.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {quickLinks.map((link) => {
          const Icon = link.icon;
          return (
            <button
              key={link.title}
              type="button"
              onClick={link.action}
              className="text-left rounded-none border border-white/5 bg-card/40 backdrop-blur-md p-5 hover:bg-white/5 hover:border-violet-500/30 transition-all group"
            >
              <div className="w-9 h-9 rounded-none bg-white/5 border border-white/10 flex items-center justify-center mb-3 group-hover:border-violet-500/30">
                <Icon className="w-4 h-4 text-violet-400" />
              </div>
              <p className="font-semibold text-white mb-1 flex items-center gap-1.5">
                {link.title}
                <ExternalLink className="w-3.5 h-3.5 opacity-0 group-hover:opacity-60 transition-opacity" />
              </p>
              <p className="text-sm text-gray-400">{link.description}</p>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="rounded-none border border-white/5 bg-card/40 backdrop-blur-md p-6">
          <h3 className="text-lg font-semibold mb-1">Frequently asked questions</h3>
          <p className="text-sm text-gray-400 mb-4">Quick answers to common topics.</p>
          <div>{FAQ_ITEMS.map((item) => (
            <FAQItem key={item.question} {...item} />
          ))}</div>
        </div>

        <div className="rounded-none border border-white/5 bg-card/40 backdrop-blur-md p-6">
          <h3 className="text-lg font-semibold mb-1">Contact us</h3>
          <p className="text-sm text-gray-400 mb-6">
            Send a message and we&apos;ll respond as soon as we can. You can also email{" "}
            <a
              href={`mailto:${SUPPORT_EMAIL}`}
              className="text-violet-400 hover:text-indigo-300 underline-offset-2 hover:underline"
            >
              {SUPPORT_EMAIL}
            </a>
            .
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="help-name">Name</Label>
                <Input
                  id="help-name"
                  value={form.name}
                  onChange={(e) => handleChange("name", e.target.value)}
                  placeholder="Your name"
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="help-email">Email</Label>
                <Input
                  id="help-email"
                  type="email"
                  value={form.email}
                  onChange={(e) => handleChange("email", e.target.value)}
                  placeholder="you@example.com"
                  className="bg-white/5 border-white/10"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="help-category">Topic</Label>
              <Select
                value={form.category}
                onValueChange={(value) => handleChange("category", value)}
              >
                <SelectTrigger id="help-category" className="bg-white/5 border-white/10">
                  <SelectValue placeholder="Select a topic" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="general">General question</SelectItem>
                  <SelectItem value="billing">Billing &amp; plans</SelectItem>
                  <SelectItem value="technical">Technical support</SelectItem>
                  <SelectItem value="bug">Report a bug</SelectItem>
                  <SelectItem value="feature">Feature request</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="help-subject">Subject (optional)</Label>
              <Input
                id="help-subject"
                value={form.subject}
                onChange={(e) => handleChange("subject", e.target.value)}
                placeholder="Brief summary"
                className="bg-white/5 border-white/10"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="help-message">Message</Label>
              <textarea
                id="help-message"
                rows={5}
                value={form.message}
                onChange={(e) => handleChange("message", e.target.value)}
                placeholder="Describe your question or issue..."
                className="flex w-full rounded-none border border-white/10 bg-white/5 px-3 py-2 text-sm shadow-none placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-y min-h-[120px]"
              />
            </div>

            <Button
              type="submit"
              disabled={submitting}
              className="w-full sm:w-auto bg-violet-500 hover:bg-violet-400"
            >
              <Send className="w-4 h-4 mr-2" />
              Send message
            </Button>
          </form>

          <div className="mt-6 flex items-start gap-3 rounded-none bg-white/[0.03] border border-white/5 p-4 text-sm text-gray-400">
            <Mail className="w-4 h-4 text-violet-400 shrink-0 mt-0.5" />
            <p>
              Submitting opens your default mail client with your message pre-filled.
              For account access issues, include your username so we can help faster.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
