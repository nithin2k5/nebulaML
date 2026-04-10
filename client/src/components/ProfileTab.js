"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
    Mail, ShieldCheck, Calendar, KeyRound,
    Pencil, Check, X, FolderOpen, Users, Tag
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from "sonner";

const USERNAME_RE = /^[a-z0-9_]+$/;

const ROLE_STYLES = {
    admin:  "bg-purple-500/20 text-purple-400 border-purple-500/30",
    user:   "bg-indigo-500/20 text-indigo-400 border-indigo-500/30",
    viewer: "bg-zinc-500/20  text-zinc-400  border-zinc-500/30",
};

export default function ProfileTab() {
    const { user, token, checkAuth } = useAuth();

    const [stats, setStats]               = useState(null);
    const [editingUsername, setEditing]   = useState(false);
    const [newUsername, setNewUsername]   = useState("");
    const [saving, setSaving]             = useState(false);

    useEffect(() => {
        if (!token) return;
        fetch(API_ENDPOINTS.AUTH.STATS, {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => d && setStats(d))
            .catch(() => {});
    }, [token]);

    const startEdit = () => {
        setNewUsername(user?.username || "");
        setEditing(true);
    };

    const cancelEdit = () => {
        setEditing(false);
        setNewUsername("");
    };

    const handleSave = async (e) => {
        e.preventDefault();
        const trimmed = newUsername.trim();
        if (!trimmed)               return toast.error("Username cannot be empty");
        if (!USERNAME_RE.test(trimmed))
            return toast.error("Only lowercase letters, digits, and underscores allowed");
        if (trimmed === user?.username) { cancelEdit(); return; }

        setSaving(true);
        try {
            const res = await fetch(API_ENDPOINTS.AUTH.UPDATE_PROFILE, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ username: trimmed }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Update failed");
            toast.success("Username updated");
            cancelEdit();
            await checkAuth();
        } catch (err) {
            toast.error(err.message);
        } finally {
            setSaving(false);
        }
    };

    const initials = user?.username?.charAt(0)?.toUpperCase() || "U";
    const memberSince = user?.created_at
        ? new Date(user.created_at).toLocaleDateString("en-US", {
              year: "numeric", month: "long", day: "numeric",
          })
        : null;

    return (
        <div className="space-y-6">
            {/* ── Hero ── */}
            <Card className="overflow-hidden">
                {/* Banner */}
                <div className="h-28 bg-gradient-to-r from-indigo-600 via-violet-600 to-purple-700 relative">
                    <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black/40" />
                </div>

                <CardContent className="px-6 pb-6">
                    {/* Avatar row */}
                    <div className="flex items-end gap-4 -mt-10 mb-4">
                        <div className="w-20 h-20 rounded-full ring-4 ring-card bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-3xl font-bold shadow-lg shrink-0">
                            {initials}
                        </div>
                    </div>

                    {/* Identity + stats */}
                    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                        <div className="space-y-1.5">
                            <h2 className="text-2xl font-bold leading-tight">{user?.username}</h2>
                            <p className="text-sm text-muted-foreground">{user?.email}</p>
                            <div className="flex items-center gap-2 flex-wrap">
                                <Badge className={`capitalize text-xs ${ROLE_STYLES[user?.role] || ROLE_STYLES.user}`}>
                                    {user?.role}
                                </Badge>
                                {memberSince && (
                                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                                        <Calendar className="w-3 h-3" /> Joined {memberSince}
                                    </span>
                                )}
                            </div>
                        </div>

                        {/* Stats */}
                        {stats && (
                            <div className="flex gap-6 shrink-0 sm:pt-1">
                                {[
                                    { icon: FolderOpen, label: "Owned",       value: stats.projects_owned },
                                    { icon: Users,      label: "Member of",   value: stats.projects_member },
                                    { icon: Tag,        label: "Annotations", value: stats.annotations_saved },
                                ].map(({ icon: Icon, label, value }) => (
                                    <div key={label} className="text-center">
                                        <p className="text-xl font-bold">{value}</p>
                                        <p className="text-[11px] text-muted-foreground flex items-center gap-1 justify-center mt-0.5">
                                            <Icon className="w-3 h-3" /> {label}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* ── Bottom two-column grid ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Account details */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Account Details</CardTitle>
                        <CardDescription>Manage your profile information</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-5">
                        {/* Username */}
                        <div className="space-y-2">
                            <Label>Username</Label>
                            {editingUsername ? (
                                <form onSubmit={handleSave} className="flex gap-2">
                                    <Input
                                        value={newUsername}
                                        onChange={(e) => setNewUsername(e.target.value)}
                                        placeholder="lowercase_only"
                                        className="flex-1"
                                        autoFocus
                                    />
                                    <Button type="submit" size="icon" disabled={saving}>
                                        <Check className="w-4 h-4" />
                                    </Button>
                                    <Button type="button" size="icon" variant="ghost" onClick={cancelEdit} disabled={saving}>
                                        <X className="w-4 h-4" />
                                    </Button>
                                </form>
                            ) : (
                                <div className="flex gap-2">
                                    <Input value={user?.username || ""} readOnly className="flex-1 text-muted-foreground cursor-default" />
                                    <Button type="button" size="icon" variant="outline" onClick={startEdit}>
                                        <Pencil className="w-4 h-4" />
                                    </Button>
                                </div>
                            )}
                            <p className="text-xs text-muted-foreground">
                                Lowercase letters, digits, and underscores only
                            </p>
                        </div>

                        {/* Email */}
                        <div className="space-y-2">
                            <Label>Email</Label>
                            <div className="relative">
                                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                <Input value={user?.email || ""} readOnly className="pl-9 text-muted-foreground cursor-default" />
                            </div>
                            <p className="text-xs text-muted-foreground">
                                Email cannot be changed. Contact an admin if needed.
                            </p>
                        </div>

                        {/* Role */}
                        <div className="space-y-2">
                            <Label>Role</Label>
                            <div className="flex items-center gap-2 h-9 px-3 rounded-md border border-input bg-transparent text-sm text-muted-foreground">
                                <ShieldCheck className="w-4 h-4 shrink-0" />
                                <span className="capitalize">{user?.role}</span>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Auth / security */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            <KeyRound className="w-4 h-4" />
                            Security
                        </CardTitle>
                        <CardDescription>How you authenticate</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex items-start gap-3 p-4 rounded-xl bg-indigo-500/5 border border-indigo-500/15">
                            <div className="w-9 h-9 rounded-lg bg-indigo-500/10 flex items-center justify-center shrink-0">
                                <Mail className="w-4 h-4 text-indigo-400" />
                            </div>
                            <div>
                                <p className="text-sm font-medium">Passwordless — Email OTP</p>
                                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                                    A one-time code is sent to your email each time you sign in.
                                    There is no password to manage or reset.
                                </p>
                            </div>
                        </div>

                        <div className="text-xs text-muted-foreground space-y-2 pt-1">
                            <div className="flex items-center gap-2">
                                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                OTP codes expire after 10 minutes
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                Sessions auto-extend while you&apos;re active
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                Rate limited to 5 sign-in attempts per minute
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
