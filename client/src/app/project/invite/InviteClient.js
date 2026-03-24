"use client";

import { useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import Link from "next/link";

export default function InviteClient() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { token: authToken, loading: authLoading } = useAuth();

  const inviteToken = searchParams.get("token");

  const [status, setStatus] = useState("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [datasetId, setDatasetId] = useState(null);

  const handleAccept = async () => {
    if (!inviteToken) return;
    setStatus("loading");

    try {
      const response = await fetch(API_ENDPOINTS.DATASETS.ACCEPT_INVITE, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ token: inviteToken }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Failed to accept invitation");
      }

      setStatus("success");
      setDatasetId(data.dataset_id);

      setTimeout(() => {
        router.push(`/project/${data.dataset_id}`);
      }, 2000);
    } catch (err) {
      console.error(err);
      setStatus("error");
      setErrorMessage(err.message || "An error occurred while accepting the invite.");
    }
  };

  if (!inviteToken) {
    return (
      <div className="flex h-screen items-center justify-center bg-black p-4">
        <Card className="w-full max-w-md bg-zinc-950/80 border-white/10 shadow-2xl backdrop-blur-xl">
          <CardHeader className="text-center">
            <AlertCircle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
            <CardTitle className="text-xl">Invalid Invite Link</CardTitle>
            <CardDescription className="text-zinc-400">
              No invitation token was found in the URL.
            </CardDescription>
          </CardHeader>
          <CardFooter className="flex justify-center">
            <Button asChild variant="outline" className="border-white/20 hover:bg-white/10">
              <Link href="/login">Go to Login</Link>
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  if (authLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-black">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!authToken) {
    return (
      <div className="flex h-screen items-center justify-center bg-black p-4">
        <Card className="w-full max-w-md bg-zinc-950/80 border-white/10 shadow-2xl backdrop-blur-xl">
          <CardHeader className="text-center">
            <CardTitle className="text-xl">Authentication Required</CardTitle>
            <CardDescription className="text-zinc-400 mt-2">
              You must be logged in to accept this invitation. If you do not have an account, please create one first.
            </CardDescription>
          </CardHeader>
          <CardFooter className="flex flex-col gap-3">
            <Button asChild className="w-full bg-indigo-600 hover:bg-indigo-700">
              <Link href={`/login?redirect=/project/invite?token=${inviteToken}`}>
                Log In
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full border-white/20 hover:bg-white/10">
              <Link href="/register">Create Account</Link>
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex h-screen items-center justify-center bg-black p-4">
      <Card className="w-full max-w-md bg-zinc-950/80 border-white/10 shadow-2xl backdrop-blur-xl">
        <CardHeader className="text-center pt-8">
          {status === "success" ? (
            <CheckCircle2 className="w-16 h-16 text-emerald-500 mx-auto mb-4 animate-in zoom-in" />
          ) : status === "error" ? (
            <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4 animate-in zoom-in" />
          ) : (
            <div className="w-16 h-16 bg-indigo-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="font-bold text-2xl text-indigo-400">N</span>
            </div>
          )}

          <CardTitle className="text-2xl font-bold tracking-tight">
            {status === "success"
              ? "Invitation Accepted!"
              : status === "error"
                ? "Failed to Join"
                : "Project Invitation"}
          </CardTitle>

          <CardDescription className="text-zinc-400 text-base mt-2">
            {status === "success"
              ? "You have successfully joined the project. Redirecting..."
              : status === "error"
                ? errorMessage
                : "You have been invited to collaborate on a NebulaML dataset. Accept below to join."}
          </CardDescription>
        </CardHeader>

        <CardFooter className="flex flex-col gap-3 pb-8 px-8">
          {status === "idle" && (
            <Button
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-base py-6 font-semibold shadow-lg shadow-indigo-500/20"
              onClick={handleAccept}
            >
              Accept Invitation
            </Button>
          )}

          {status === "loading" && (
            <Button disabled className="w-full bg-indigo-600/50 text-base py-6">
              <Loader2 className="w-5 h-5 mr-2 animate-spin" />
              Processing...
            </Button>
          )}

          {status === "success" && datasetId && (
            <Button asChild className="w-full bg-emerald-600 hover:bg-emerald-700 text-base py-6">
              <Link href={`/project/${datasetId}`}>Go to Project Now</Link>
            </Button>
          )}

          {status === "error" && (
            <Button asChild variant="outline" className="w-full border-white/20 hover:bg-white/10 py-6">
              <Link href="/dashboard">Return to Dashboard</Link>
            </Button>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}
