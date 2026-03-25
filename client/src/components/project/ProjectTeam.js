"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Shield, ShieldAlert, ShieldCheck, Mail, UserPlus, Trash2, Activity, Clock } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

function formatDistanceToNow(isoOrDate) {
    const diffSec = (new Date(isoOrDate).getTime() - Date.now()) / 1000;
    const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
    const a = Math.abs(diffSec);
    if (a < 60) return rtf.format(Math.round(diffSec), "second");
    const diffMin = diffSec / 60;
    if (Math.abs(diffMin) < 60) return rtf.format(Math.round(diffMin), "minute");
    const diffHour = diffSec / 3600;
    if (Math.abs(diffHour) < 24) return rtf.format(Math.round(diffHour), "hour");
    const diffDay = diffSec / 86400;
    if (Math.abs(diffDay) < 7) return rtf.format(Math.round(diffDay), "day");
    const diffWeek = diffSec / 604800;
    if (Math.abs(diffWeek) < 5) return rtf.format(Math.round(diffWeek), "week");
    const diffMonth = diffSec / (30.44 * 86400);
    if (Math.abs(diffMonth) < 12) return rtf.format(Math.round(diffMonth), "month");
    return rtf.format(Math.round(diffSec / (365.25 * 86400)), "year");
}

export default function ProjectTeam({ dataset }) {
    const { token } = useAuth();
    const [members, setMembers] = useState([]);
    const [activities, setActivities] = useState([]);
    const [loading, setLoading] = useState(true);
    
    const [newMemberEmail, setNewMemberEmail] = useState("");
    const [newMemberRole, setNewMemberRole] = useState("annotator");
    const [addingMember, setAddingMember] = useState(false);

    const fetchData = async () => {
        try {
            const [memRes, actRes] = await Promise.all([
                fetch(API_ENDPOINTS.DATASETS.MEMBERS(dataset.id), { headers: { "Authorization": `Bearer ${token}` } }),
                fetch(API_ENDPOINTS.DATASETS.ACTIVITY(dataset.id), { headers: { "Authorization": `Bearer ${token}` } })
            ]);

            if (memRes.ok) {
                const md = await memRes.json();
                setMembers(md.members || []);
            }
            if (actRes.ok) {
                const ad = await actRes.json();
                setActivities(ad.activity || []);
            }
        } catch (e) {
            console.error(e);
            toast.error("Failed to load team data");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [dataset.id]);

    const handleAddMember = async (e) => {
        e.preventDefault();
        if (!newMemberEmail) return;

        setAddingMember(true);
        try {
            const res = await fetch(API_ENDPOINTS.DATASETS.MEMBERS(dataset.id), {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({ email: newMemberEmail, role: newMemberRole })
            });

            if (res.ok) {
                toast.success("Member added successfully");
                setNewMemberEmail("");
                fetchData();
            } else {
                const err = await res.json();
                toast.error(err.detail || "Failed to add member");
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        } finally {
            setAddingMember(false);
        }
    };

    const handleRemoveMember = async (userId) => {
        if (!confirm("Are you sure you want to remove this member?")) return;

        try {
            const res = await fetch(API_ENDPOINTS.DATASETS.MEMBER_REMOVE(dataset.id, userId), {
                method: "DELETE",
                headers: { "Authorization": `Bearer ${token}` }
            });

            if (res.ok) {
                toast.success("Member removed");
                fetchData();
            } else {
                const err = await res.json();
                toast.error(err.detail || "Failed to remove member");
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        }
    };

    const getRoleIcon = (role) => {
        switch (role) {
            case 'owner': return <ShieldAlert className="w-4 h-4 text-purple-500" />;
            case 'admin': return <ShieldCheck className="w-4 h-4 text-blue-500" />;
            case 'annotator': return <Shield className="w-4 h-4 text-emerald-500" />;
            default: return <Shield className="w-4 h-4 text-muted-foreground" />;
        }
    };

    const formatAction = (log) => {
        switch (log.action) {
            case 'member_added':
                return `Added ${log.details?.target_email} as ${log.details?.role}`;
            case 'member_removed':
                return `Removed user ID ${log.details?.target_user_id} from project`;
            default:
                return log.action.replace(/_/g, " ");
        }
    };

    if (loading) return <div className="p-8">Loading team data...</div>;

    return (
        <div className="h-full grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <UserPlus className="w-5 h-5" />
                            Team Members
                        </CardTitle>
                        <CardDescription>Manage who has access to this project</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <form onSubmit={handleAddMember} className="flex gap-4 items-end bg-muted/30 p-4 rounded-lg border">
                            <div className="space-y-2 flex-1">
                                <Label>Email Address</Label>
                                <Input 
                                    type="email" 
                                    placeholder="colleague@company.com" 
                                    value={newMemberEmail}
                                    onChange={e => setNewMemberEmail(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="space-y-2 w-[180px]">
                                <Label>Role</Label>
                                <Select value={newMemberRole} onValueChange={setNewMemberRole}>
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="admin">Admin</SelectItem>
                                        <SelectItem value="annotator">Annotator</SelectItem>
                                        <SelectItem value="viewer">Viewer</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <Button type="submit" disabled={addingMember}>
                                {addingMember ? "Adding..." : "Invite"}
                            </Button>
                        </form>

                        <div className="rounded-md border divide-y">
                            {members.map(member => (
                                <div key={member.id} className="p-4 flex items-center justify-between">
                                    <div className="flex items-center gap-4">
                                        <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                                            <Mail className="w-5 h-5 text-primary" />
                                        </div>
                                        <div>
                                            <p className="font-medium text-sm flex items-center gap-2">
                                                {member.username} 
                                            </p>
                                            <p className="text-xs text-muted-foreground">{member.email}</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <Badge variant="outline" className="capitalize flex items-center gap-1">
                                            {getRoleIcon(member.role)}
                                            {member.role}
                                        </Badge>
                                        {member.role !== 'owner' && (
                                            <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => handleRemoveMember(member.user_id)}>
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            ))}
                            {members.length === 0 && (
                                <div className="p-8 text-center text-muted-foreground">No team members found</div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>

            <div className="lg:col-span-1">
                <Card className="h-full">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Activity className="w-5 h-5" />
                            Activity Log
                        </CardTitle>
                        <CardDescription>Recent actions in this project</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {activities.map(log => (
                                <div key={log.id} className="flex gap-3 items-start">
                                    <div className="mt-0.5 w-2 h-2 rounded-full bg-primary ring-4 ring-primary/10" />
                                    <div className="flex-1 space-y-1">
                                        <p className="text-sm">
                                            <span className="font-medium text-foreground">{log.username || "System"}: </span>
                                            <span className="text-muted-foreground">{formatAction(log)}</span>
                                        </p>
                                        <p className="text-[10px] text-muted-foreground flex items-center gap-1">
                                            <Clock className="w-3 h-3" />
                                            {formatDistanceToNow(log.created_at)}
                                        </p>
                                    </div>
                                </div>
                            ))}
                            {activities.length === 0 && (
                                <div className="text-center text-sm text-muted-foreground py-8">
                                    No recent activity
                                </div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
