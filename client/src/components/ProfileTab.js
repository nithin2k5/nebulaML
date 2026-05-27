"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
    Mail, ShieldCheck, Calendar, KeyRound,
    Pencil, Check, X, FolderOpen, Users, Tag,
    Layers, Clock, Zap, Lock, CheckCircle2
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const USERNAME_RE = /^[a-z0-9_]+$/;

const ROLE_CONFIG = {
    admin:  { label: "Admin",  gradient: "from-purple-500 to-violet-600",  ring: "ring-purple-500/30",  glow: "shadow-purple-500/20",  bg: "bg-purple-500/10 text-purple-300 border-purple-500/30" },
    user:   { label: "User",   gradient: "from-indigo-500 to-blue-600",    ring: "ring-indigo-500/30",  glow: "shadow-indigo-500/20",  bg: "bg-indigo-500/10 text-indigo-300 border-indigo-500/30" },
    viewer: { label: "Viewer", gradient: "from-zinc-500 to-slate-600",     ring: "ring-zinc-500/30",    glow: "shadow-zinc-500/20",    bg: "bg-zinc-500/10  text-zinc-300  border-zinc-500/30"  },
};

function StatCard({ icon: Icon, label, value, color }) {
    return (
        <div className={cn(
            "relative flex flex-col items-center justify-center p-5 rounded-2xl border border-white/[0.07]",
            "bg-white/[0.03] backdrop-blur-sm hover:bg-white/[0.06] transition-all duration-300 group"
        )}>
            {/* glow blob */}
            <div className={cn("absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-xl -z-10", color)} />
            <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center mb-3 border border-white/10", color)}>
                <Icon className="w-5 h-5" />
            </div>
            <p className="text-2xl font-black tabular-nums tracking-tight">{value ?? "—"}</p>
            <p className="text-[11px] text-gray-500 uppercase tracking-wider mt-1">{label}</p>
        </div>
    );
}

function InfoRow({ icon: Icon, label, children }) {
    return (
        <div className="flex items-start gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/[0.05] hover:bg-white/[0.04] transition-colors duration-200">
            <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center shrink-0 mt-0.5">
                <Icon className="w-4 h-4 text-gray-400" />
            </div>
            <div className="flex-1 min-w-0">
                <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1">{label}</p>
                {children}
            </div>
        </div>
    );
}

export default function ProfileTab() {
    const { user, token, checkAuth } = useAuth();

    const [stats, setStats]             = useState(null);
    const [editingUsername, setEditing] = useState(false);
    const [newUsername, setNewUsername] = useState("");
    const [saving, setSaving]           = useState(false);
    const canvasRef                     = useRef(null);

    // Fetch stats
    useEffect(() => {
        if (!token) return;
        fetch(API_ENDPOINTS.AUTH.STATS, { headers: { Authorization: `Bearer ${token}` } })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => d && setStats(d))
            .catch(() => {});
    }, [token]);

    // Particle canvas animation on the hero
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        let raf;
        const W = canvas.width  = canvas.offsetWidth;
        const H = canvas.height = canvas.offsetHeight;
        const particles = Array.from({ length: 55 }, () => ({
            x: Math.random() * W,
            y: Math.random() * H,
            r: Math.random() * 1.5 + 0.4,
            vx: (Math.random() - 0.5) * 0.3,
            vy: (Math.random() - 0.5) * 0.3,
            alpha: Math.random() * 0.5 + 0.15,
        }));
        const draw = () => {
            ctx.clearRect(0, 0, W, H);
            particles.forEach((p) => {
                p.x = (p.x + p.vx + W) % W;
                p.y = (p.y + p.vy + H) % H;
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(139,92,246,${p.alpha})`;
                ctx.fill();
            });
            raf = requestAnimationFrame(draw);
        };
        draw();
        return () => cancelAnimationFrame(raf);
    }, []);

    const startEdit  = () => { setNewUsername(user?.username || ""); setEditing(true); };
    const cancelEdit = () => { setEditing(false); setNewUsername(""); };

    const handleSave = async (e) => {
        e.preventDefault();
        const trimmed = newUsername.trim();
        if (!trimmed)                  return toast.error("Username cannot be empty");
        if (!USERNAME_RE.test(trimmed)) return toast.error("Only lowercase letters, digits, and underscores allowed");
        if (trimmed === user?.username) { cancelEdit(); return; }

        setSaving(true);
        try {
            const res  = await fetch(API_ENDPOINTS.AUTH.UPDATE_PROFILE, {
                method: "PUT",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({ username: trimmed }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Update failed");
            toast.success("Username updated ✓");
            cancelEdit();
            await checkAuth();
        } catch (err) {
            toast.error(err.message);
        } finally {
            setSaving(false);
        }
    };

    const role        = user?.role || "user";
    const roleCfg     = ROLE_CONFIG[role] || ROLE_CONFIG.user;
    const initials    = user?.username?.slice(0, 2)?.toUpperCase() || "U";
    const memberSince = user?.created_at
        ? new Date(user.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
        : null;

    return (
        <div className="space-y-6 max-w-4xl mx-auto animate-fade-in">

            {/* ── Hero Card ── */}
            <div className="relative rounded-3xl overflow-hidden border border-white/[0.07] shadow-2xl">
                {/* Particle canvas background */}
                <canvas
                    ref={canvasRef}
                    className="absolute inset-0 w-full h-full pointer-events-none"
                    style={{ background: "linear-gradient(135deg, #0f0c1a 0%, #0d1225 50%, #0c0f1e 100%)" }}
                />

                {/* Gradient overlay bands */}
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute top-0 left-1/4 w-72 h-72 rounded-full bg-violet-600/20 blur-3xl" />
                    <div className="absolute bottom-0 right-1/4 w-56 h-56 rounded-full bg-indigo-600/15 blur-3xl" />
                </div>

                {/* Content */}
                <div className="relative z-10 p-8 pb-10">
                    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-6">

                        {/* Avatar */}
                        <div className="relative shrink-0">
                            <div className={cn(
                                "w-24 h-24 rounded-2xl ring-4 shadow-2xl flex items-center justify-center",
                                `bg-gradient-to-br ${roleCfg.gradient}`,
                                roleCfg.ring,
                                roleCfg.glow,
                            )}>
                                <span className="text-white text-3xl font-black tracking-tight select-none">{initials}</span>
                            </div>
                            {/* Online dot */}
                            <span className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-emerald-400 ring-2 ring-black shadow-lg shadow-emerald-500/50" />
                        </div>

                        {/* Identity */}
                        <div className="flex-1 space-y-2">
                            <div className="flex flex-wrap items-center gap-3">
                                <h1 className="text-3xl font-black text-white tracking-tight">
                                    {user?.username || "Loading…"}
                                </h1>
                                <Badge className={cn("border text-xs font-semibold capitalize px-2.5 py-0.5", roleCfg.bg)}>
                                    <ShieldCheck className="w-3 h-3 mr-1" />{roleCfg.label}
                                </Badge>
                            </div>
                            <p className="text-gray-400 text-sm flex items-center gap-2">
                                <Mail className="w-3.5 h-3.5 text-gray-500" />
                                {user?.email}
                            </p>
                            {memberSince && (
                                <p className="text-gray-500 text-xs flex items-center gap-2">
                                    <Calendar className="w-3 h-3" />
                                    Member since {memberSince}
                                </p>
                            )}
                        </div>
                    </div>

                    {/* Stat pills */}
                    {stats && (
                        <div className="grid grid-cols-3 gap-3 mt-8">
                            <StatCard icon={FolderOpen} label="Owned"       value={stats.projects_owned}    color="bg-violet-500/10 text-violet-400" />
                            <StatCard icon={Users}      label="Member Of"   value={stats.projects_member}   color="bg-indigo-500/10 text-indigo-400" />
                            <StatCard icon={Tag}        label="Annotations" value={stats.annotations_saved} color="bg-emerald-500/10 text-emerald-400" />
                        </div>
                    )}
                </div>
            </div>

            {/* ── Bottom grid ── */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">

                {/* Account Details — 3 cols */}
                <div className="lg:col-span-3 rounded-2xl border border-white/[0.07] bg-white/[0.02] backdrop-blur-sm overflow-hidden">
                    <div className="px-6 py-5 border-b border-white/[0.06]">
                        <p className="text-sm font-semibold text-white flex items-center gap-2">
                            <Pencil className="w-4 h-4 text-indigo-400" /> Account Details
                        </p>
                        <p className="text-xs text-gray-500 mt-0.5">Manage your profile information</p>
                    </div>

                    <div className="p-6 space-y-4">
                        {/* Username row */}
                        <InfoRow icon={Layers} label="Username">
                            {editingUsername ? (
                                <form onSubmit={handleSave} className="flex gap-2 mt-1">
                                    <Input
                                        value={newUsername}
                                        onChange={(e) => setNewUsername(e.target.value)}
                                        placeholder="lowercase_only"
                                        className="flex-1 bg-white/5 border-white/10 text-sm h-9 focus:border-indigo-500/60 focus:ring-indigo-500/20"
                                        autoFocus
                                    />
                                    <Button type="submit" size="icon" className="h-9 w-9 bg-indigo-600 hover:bg-indigo-500" disabled={saving}>
                                        <Check className="w-3.5 h-3.5" />
                                    </Button>
                                    <Button type="button" size="icon" variant="ghost" className="h-9 w-9 text-gray-400 hover:text-white" onClick={cancelEdit} disabled={saving}>
                                        <X className="w-3.5 h-3.5" />
                                    </Button>
                                </form>
                            ) : (
                                <div className="flex items-center justify-between mt-1">
                                    <span className="text-sm font-medium text-white">{user?.username}</span>
                                    <button
                                        onClick={startEdit}
                                        className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
                                    >
                                        <Pencil className="w-3 h-3" /> Edit
                                    </button>
                                </div>
                            )}
                            {editingUsername && (
                                <p className="text-[11px] text-gray-600 mt-1">Lowercase letters, digits, underscores only</p>
                            )}
                        </InfoRow>

                        {/* Email row */}
                        <InfoRow icon={Mail} label="Email Address">
                            <div className="flex items-center justify-between mt-1">
                                <span className="text-sm text-gray-300 truncate">{user?.email}</span>
                                <span className="text-[10px] text-gray-600 ml-3 shrink-0">Read-only</span>
                            </div>
                        </InfoRow>

                        {/* Role row */}
                        <InfoRow icon={ShieldCheck} label="Role">
                            <div className="flex items-center gap-2 mt-1">
                                <Badge className={cn("border text-xs capitalize", roleCfg.bg)}>
                                    {roleCfg.label}
                                </Badge>
                                <span className="text-[11px] text-gray-600">Managed by an admin</span>
                            </div>
                        </InfoRow>

                        {/* Join date row */}
                        {memberSince && (
                            <InfoRow icon={Calendar} label="Member Since">
                                <span className="text-sm text-gray-300 mt-1 block">{memberSince}</span>
                            </InfoRow>
                        )}
                    </div>
                </div>

                {/* Security — 2 cols */}
                <div className="lg:col-span-2 rounded-2xl border border-white/[0.07] bg-white/[0.02] backdrop-blur-sm overflow-hidden flex flex-col">
                    <div className="px-6 py-5 border-b border-white/[0.06]">
                        <p className="text-sm font-semibold text-white flex items-center gap-2">
                            <KeyRound className="w-4 h-4 text-violet-400" /> Security
                        </p>
                        <p className="text-xs text-gray-500 mt-0.5">How you authenticate</p>
                    </div>

                    <div className="p-6 flex-1 flex flex-col gap-5">
                        {/* Auth method pill */}
                        <div className="relative rounded-xl overflow-hidden border border-indigo-500/20 p-4 bg-indigo-500/[0.04]">
                            <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-500/10 rounded-full -translate-y-1/2 translate-x-1/2 blur-2xl pointer-events-none" />
                            <div className="flex items-center gap-3 mb-3">
                                <div className="w-9 h-9 rounded-xl bg-indigo-500/15 border border-indigo-500/20 flex items-center justify-center">
                                    <Mail className="w-4 h-4 text-indigo-400" />
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-white">Email OTP</p>
                                    <p className="text-[11px] text-gray-500">Passwordless login</p>
                                </div>
                            </div>
                            <p className="text-xs text-gray-400 leading-relaxed">
                                A one-time code is sent to your inbox each sign-in. No password to manage or reset.
                            </p>
                        </div>

                        {/* Security facts */}
                        <div className="space-y-3 flex-1">
                            {[
                                { icon: Clock,        text: "OTP codes expire after 10 minutes",        color: "text-emerald-400", dot: "bg-emerald-400" },
                                { icon: Zap,          text: "Sessions auto-extend while you're active", color: "text-emerald-400", dot: "bg-emerald-400" },
                                { icon: Lock,         text: "Rate limited to 5 attempts per minute",     color: "text-amber-400",   dot: "bg-amber-400"  },
                                { icon: CheckCircle2, text: "JWT tokens, never stored in plain text",    color: "text-emerald-400", dot: "bg-emerald-400" },
                            ].map(({ icon: Icon, text, color, dot }) => (
                                <div key={text} className="flex items-center gap-3 text-xs text-gray-500">
                                    <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dot)} />
                                    <span>{text}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
