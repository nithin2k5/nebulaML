"use client";

import { useState, useEffect } from "react";
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
    admin:  { label: "Admin",  bg: "bg-blue-500/10 text-blue-400 border-blue-500/20" },
    user:   { label: "User",   bg: "bg-zinc-500/10 text-zinc-300 border-zinc-500/20" },
    viewer: { label: "Viewer", bg: "bg-gray-500/10 text-gray-300 border-gray-500/20" },
};

function StatCard({ icon: Icon, label, value }) {
    return (
        <div className="flex flex-col p-4 rounded-lg border border-zinc-800/60 bg-zinc-900/30">
            <div className="flex items-center gap-2 mb-2">
                <Icon className="w-4 h-4 text-zinc-400" />
                <p className="text-xs font-medium text-zinc-400 uppercase tracking-wider">{label}</p>
            </div>
            <p className="text-2xl font-semibold tabular-nums text-zinc-100">{value ?? "—"}</p>
        </div>
    );
}

function InfoRow({ icon: Icon, label, children }) {
    return (
        <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-6 py-4 border-b border-zinc-800/40 last:border-0">
            <div className="flex items-center gap-2 w-48 shrink-0 text-zinc-400 sm:mt-1.5">
                <Icon className="w-4 h-4" />
                <span className="text-sm font-medium">{label}</span>
            </div>
            <div className="flex-1 min-w-0">
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
    
    // Email change state
    const [editingEmail, setEditingEmail] = useState(false);
    const [emailStep, setEmailStep]       = useState(0);
    const [newEmail, setNewEmail]         = useState("");
    const [emailOtp, setEmailOtp]         = useState("");
    const [emailSaving, setEmailSaving]   = useState(false);

    // Fetch stats
    useEffect(() => {
        if (!token) return;
        fetch(API_ENDPOINTS.AUTH.STATS, { headers: { Authorization: `Bearer ${token}` } })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => d && setStats(d))
            .catch(() => {});
    }, [token]);

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

    const startEmailEdit = () => {
        setNewEmail("");
        setEmailOtp("");
        setEmailStep(0);
        setEditingEmail(true);
    };

    const cancelEmailEdit = () => {
        setEditingEmail(false);
        setNewEmail("");
        setEmailOtp("");
        setEmailStep(0);
    };

    const requestCurrentEmailOtp = async () => {
        if (!newEmail || !newEmail.includes("@")) {
            return toast.error("Please enter a valid new email address");
        }
        if (newEmail === user?.email) {
            return toast.error("New email must be different from current email");
        }
        
        setEmailSaving(true);
        try {
            const res = await fetch(`${API_ENDPOINTS.BASE}/auth/me/change-email/request-current`, {
                method: "POST",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed to request OTP");
            toast.success("OTP sent to your current email");
            setEmailStep(1);
        } catch (err) {
            toast.error(err.message);
        } finally {
            setEmailSaving(false);
        }
    };

    const verifyCurrentEmailOtp = async () => {
        if (!emailOtp) return toast.error("Please enter the OTP");
        
        setEmailSaving(true);
        try {
            const res = await fetch(`${API_ENDPOINTS.BASE}/auth/me/change-email/verify-current`, {
                method: "POST",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({ otp: emailOtp, new_email: newEmail })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Verification failed");
            toast.success("OTP sent to your new email");
            setEmailOtp("");
            setEmailStep(2);
        } catch (err) {
            toast.error(err.message);
        } finally {
            setEmailSaving(false);
        }
    };

    const verifyNewEmailOtp = async () => {
        if (!emailOtp) return toast.error("Please enter the OTP");
        
        setEmailSaving(true);
        try {
            const res = await fetch(`${API_ENDPOINTS.BASE}/auth/me/change-email/verify-new`, {
                method: "POST",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({ otp: emailOtp })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Verification failed");
            toast.success("Email updated successfully");
            cancelEmailEdit();
            await checkAuth();
        } catch (err) {
            toast.error(err.message);
        } finally {
            setEmailSaving(false);
        }
    };

    const role        = user?.role || "user";
    const roleCfg     = ROLE_CONFIG[role] || ROLE_CONFIG.user;
    const initials    = user?.username?.slice(0, 2)?.toUpperCase() || "U";
    const memberSince = user?.created_at
        ? new Date(user.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
        : null;

    return (
        <div className="space-y-6 max-w-5xl mx-auto">
            {/* Header Section */}
            <div className="pb-5 border-b border-zinc-800">
                <h1 className="text-2xl font-semibold text-zinc-100">Profile Settings</h1>
                <p className="text-sm text-zinc-400 mt-1">Manage your account details and security preferences.</p>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                
                <div className="xl:col-span-2 space-y-6">
                    {/* User Hero Classic */}
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6 flex flex-col sm:flex-row items-center gap-6">
                        <div className="w-20 h-20 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0 shadow-inner">
                            <span className="text-zinc-300 text-2xl font-medium select-none">{initials}</span>
                        </div>
                        <div className="text-center sm:text-left space-y-1.5 flex-1">
                            <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                                <h2 className="text-xl font-semibold text-zinc-100 tracking-tight">{user?.username}</h2>
                                <Badge variant="outline" className={cn("px-2 py-0.5", roleCfg.bg)}>
                                    {roleCfg.label}
                                </Badge>
                            </div>
                            <p className="text-sm text-zinc-400">{user?.email}</p>
                            {memberSince && (
                                <p className="text-xs text-zinc-500 pt-1">Member since {memberSince}</p>
                            )}
                        </div>
                    </div>

                    {/* Account Details */}
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/30">
                        <div className="px-6 py-4 border-b border-zinc-800/60">
                            <h3 className="text-base font-medium text-zinc-100">Account Details</h3>
                        </div>
                        <div className="px-6 py-2">
                            {/* Username */}
                            <InfoRow icon={Layers} label="Username">
                                {editingUsername ? (
                                    <form onSubmit={handleSave} className="flex gap-2">
                                        <Input
                                            value={newUsername}
                                            onChange={(e) => setNewUsername(e.target.value)}
                                            placeholder="lowercase_only"
                                            className="flex-1 bg-zinc-950 border-zinc-700 text-sm h-9 max-w-xs focus:ring-zinc-600 focus:border-zinc-500"
                                            autoFocus
                                        />
                                        <Button type="submit" size="icon" className="h-9 w-9 bg-zinc-100 hover:bg-white text-zinc-900" disabled={saving}>
                                            <Check className="w-4 h-4" />
                                        </Button>
                                        <Button type="button" size="icon" variant="ghost" className="h-9 w-9 text-zinc-400 hover:text-white" onClick={cancelEdit} disabled={saving}>
                                            <X className="w-4 h-4" />
                                        </Button>
                                    </form>
                                ) : (
                                    <div className="flex items-center justify-between sm:justify-start gap-4">
                                        <span className="text-sm font-medium text-zinc-200">{user?.username}</span>
                                        <button
                                            onClick={startEdit}
                                            className="text-xs text-zinc-400 hover:text-zinc-300 flex items-center gap-1 transition-colors"
                                        >
                                            <Pencil className="w-3 h-3" /> Edit
                                        </button>
                                    </div>
                                )}
                                {editingUsername && (
                                    <p className="text-[11px] text-zinc-500 mt-1.5">Lowercase letters, digits, underscores only</p>
                                )}
                            </InfoRow>

                            {/* Email */}
                            <InfoRow icon={Mail} label="Email Address">
                                {editingEmail ? (
                                    <div className="space-y-3 max-w-sm">
                                        {emailStep === 0 && (
                                            <div className="flex flex-col gap-2">
                                                <Input
                                                    value={newEmail}
                                                    onChange={(e) => setNewEmail(e.target.value)}
                                                    placeholder="Enter new email address"
                                                    className="bg-zinc-950 border-zinc-700 text-sm h-9 focus:ring-zinc-600 focus:border-zinc-500"
                                                    autoFocus
                                                />
                                                <div className="flex gap-2 pt-1">
                                                    <Button type="button" onClick={requestCurrentEmailOtp} className="h-8 text-xs bg-zinc-100 hover:bg-white text-zinc-900" disabled={emailSaving}>
                                                        Verify Current Email
                                                    </Button>
                                                    <Button type="button" variant="ghost" onClick={cancelEmailEdit} className="h-8 text-xs text-zinc-400 hover:text-white" disabled={emailSaving}>
                                                        Cancel
                                                    </Button>
                                                </div>
                                            </div>
                                        )}
                                        {emailStep === 1 && (
                                            <div className="flex flex-col gap-2">
                                                <p className="text-xs text-zinc-400">Enter the OTP sent to {user?.email}</p>
                                                <Input
                                                    value={emailOtp}
                                                    onChange={(e) => setEmailOtp(e.target.value)}
                                                    placeholder="OTP for current email"
                                                    className="bg-zinc-950 border-zinc-700 text-sm h-9 focus:ring-zinc-600 focus:border-zinc-500"
                                                    autoFocus
                                                />
                                                <div className="flex gap-2 pt-1">
                                                    <Button type="button" onClick={verifyCurrentEmailOtp} className="h-8 text-xs bg-zinc-100 hover:bg-white text-zinc-900" disabled={emailSaving}>
                                                        Verify & Continue
                                                    </Button>
                                                    <Button type="button" variant="ghost" onClick={cancelEmailEdit} className="h-8 text-xs text-zinc-400 hover:text-white" disabled={emailSaving}>
                                                        Cancel
                                                    </Button>
                                                </div>
                                            </div>
                                        )}
                                        {emailStep === 2 && (
                                            <div className="flex flex-col gap-2">
                                                <p className="text-xs text-zinc-400">Enter the OTP sent to {newEmail}</p>
                                                <Input
                                                    value={emailOtp}
                                                    onChange={(e) => setEmailOtp(e.target.value)}
                                                    placeholder="OTP for new email"
                                                    className="bg-zinc-950 border-zinc-700 text-sm h-9 focus:ring-zinc-600 focus:border-zinc-500"
                                                    autoFocus
                                                />
                                                <div className="flex gap-2 pt-1">
                                                    <Button type="button" onClick={verifyNewEmailOtp} className="h-8 text-xs bg-zinc-100 hover:bg-white text-zinc-900" disabled={emailSaving}>
                                                        Confirm Email Change
                                                    </Button>
                                                    <Button type="button" variant="ghost" onClick={cancelEmailEdit} className="h-8 text-xs text-zinc-400 hover:text-white" disabled={emailSaving}>
                                                        Cancel
                                                    </Button>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-between sm:justify-start gap-4">
                                        <span className="text-sm text-zinc-300 truncate">{user?.email}</span>
                                        <button
                                            onClick={startEmailEdit}
                                            className="text-xs text-zinc-400 hover:text-zinc-300 flex items-center gap-1 transition-colors shrink-0"
                                        >
                                            <Pencil className="w-3 h-3" /> Edit
                                        </button>
                                    </div>
                                )}
                            </InfoRow>

                            {/* Role */}
                            <InfoRow icon={ShieldCheck} label="Role">
                                <div className="flex items-center gap-3">
                                    <Badge variant="outline" className={cn("px-2 py-0.5", roleCfg.bg)}>
                                        {roleCfg.label}
                                    </Badge>
                                    <span className="text-xs text-zinc-500">Managed by administrators</span>
                                </div>
                            </InfoRow>
                        </div>
                    </div>
                </div>

                <div className="space-y-6">
                    {/* Stats */}
                    {stats && (
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6">
                            <h3 className="text-base font-medium text-zinc-100 mb-4">Activity Overview</h3>
                            <div className="grid grid-cols-2 gap-4">
                                <StatCard icon={FolderOpen} label="Projects" value={stats.projects_owned} />
                                <StatCard icon={Tag} label="Annotations" value={stats.annotations_saved} />
                            </div>
                        </div>
                    )}

                    {/* Security */}
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6">
                        <div className="flex items-center gap-2 mb-4 text-zinc-100">
                            <KeyRound className="w-4 h-4 text-zinc-400" />
                            <h3 className="text-base font-medium">Security</h3>
                        </div>
                        
                        <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 mb-5">
                            <div className="flex items-center gap-3 mb-2">
                                <Mail className="w-4 h-4 text-zinc-400" />
                                <p className="text-sm font-medium text-zinc-200">Email OTP Authentication</p>
                            </div>
                            <p className="text-xs text-zinc-500 leading-relaxed">
                                You use passwordless login. A secure one-time code is sent to your inbox each time you sign in.
                            </p>
                        </div>

                        <div className="space-y-3">
                            {[
                                { icon: Clock,        text: "OTP codes expire after 10 minutes" },
                                { icon: Zap,          text: "Sessions auto-extend while active" },
                                { icon: Lock,         text: "Rate limited to 5 attempts per minute" },
                                { icon: CheckCircle2, text: "Tokens never stored in plain text" },
                            ].map(({ icon: Icon, text }) => (
                                <div key={text} className="flex items-center gap-3 text-xs text-zinc-400">
                                    <Icon className="w-3.5 h-3.5 text-zinc-500" />
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
