"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Zap, User, Lock, AlertCircle, LogIn } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { login, verifyOtp } = useAuth();
  const [formData, setFormData] = useState({
    email: "",
    otp: ""
  });
  const [step, setStep] = useState("email");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    if (step === "email") {
      const result = await login(formData.email);
      if (result.success) {
        if (result.isFastPass) {
          router.push("/dashboard");
        } else {
          setStep("otp");
        }
      } else {
        setError(result.error);
      }
    } else {
      const result = await verifyOtp(formData.email, formData.otp);
      if (result.success) {
        router.push("/dashboard");
      } else {
        setError(result.error);
      }
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Zap className="text-4xl text-primary mx-auto mb-4" />
          <h1 className="text-2xl font-bold">Welcome Back</h1>
          <p className="text-muted-foreground text-sm">Sign in to your account</p>
        </div>

        {/* Login Card */}
        <Card className="border-border">
          <CardHeader>
            <CardTitle className="text-xl">Login</CardTitle>
            <CardDescription>
              Enter your credentials to access your account
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/30 flex items-center gap-2 text-destructive text-sm">
                  <LogIn className="flex-shrink-0" />
                  <p>{error}</p>
                </div>
              )}

              {step === "email" ? (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      placeholder="Email address"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      required
                    />
                  </div>
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={loading}
                  >
                    {loading ? "Sending Code..." : "Continue"}
                  </Button>
                </>
              ) : (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="otp">Verification Code</Label>
                    <Input
                      id="otp"
                      type="text"
                      placeholder="Enter 6-digit code"
                      value={formData.otp}
                      onChange={(e) => setFormData({ ...formData, otp: e.target.value })}
                      required
                      maxLength={6}
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      We sent a code to {formData.email}
                    </p>
                  </div>
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={loading}
                  >
                    {loading ? "Verifying..." : "Verify & Sign In"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    className="w-full mt-2"
                    onClick={() => setStep("email")}
                    disabled={loading}
                  >
                    Back
                  </Button>
                </>
              )}
            </form>

            <div className="mt-6 text-center">
              <p className="mt-2 text-center text-sm text-gray-600">
                Don&apos;t have an account?{' '}
                <a href="/register" className="font-medium text-indigo-600 hover:text-indigo-500">
                  Register
                </a>
              </p>
            </div>

            {/* Demo credentials */}
            <div className="mt-8 pt-6 border-t border-border">
              <p className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider">Demo Accounts</p>
              <div className="grid grid-cols-1 gap-2">
                {['Admin', 'User', 'Viewer'].map((role) => (
                  <div key={role} className="flex items-center justify-between text-xs p-2 rounded bg-muted/50">
                    <span className="font-medium">{role}</span>
                    <span className="text-muted-foreground font-mono">{role.toLowerCase()}@example.com</span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Back to home */}
        <div className="text-center mt-6">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/home")}
            className="text-muted-foreground"
          >
            ← Back to home
          </Button>
        </div>
      </div>
    </div>
  );
}

