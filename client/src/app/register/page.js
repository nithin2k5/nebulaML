"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Zap, AlertCircle } from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const { register, verifyOtp } = useAuth();
  const [formData, setFormData] = useState({
    username: "",
    email: "",
    otp: "",
    role: "user"
  });
  const [step, setStep] = useState("details"); // "details" or "otp"
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    if (step === "details") {
      const result = await register(
        formData.username,
        formData.email,
        formData.role
      );

      if (result.success) {
        setStep("otp");
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
          <h1 className="text-2xl font-bold">Create Account</h1>
          <p className="text-muted-foreground text-sm">Join YOLO Generator today</p>
        </div>

        {/* Register Card */}
        <Card className="border-border">
          <CardHeader>
            <CardTitle className="text-xl">Register</CardTitle>
            <CardDescription>
              Create your account to get started
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/30 flex items-center gap-2 text-destructive text-sm">
                  <AlertCircle className="flex-shrink-0" />
                  <p>{error}</p>
                </div>
              )}

              {step === "details" ? (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <Input
                      id="username"
                      type="text"
                      placeholder="Username"
                      value={formData.username}
                      onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      placeholder="Email"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="role">Role</Label>
                    <Select value={formData.role} onValueChange={(value) => setFormData({ ...formData, role: value })}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="user">User (Full Access)</SelectItem>
                        <SelectItem value="viewer">Viewer (Read Only)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <Button
                    type="submit"
                    className="w-full"
                    disabled={loading}
                  >
                    {loading ? "Creating account..." : "Continue"}
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
                      We sent a verification code to {formData.email}
                    </p>
                  </div>
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={loading}
                  >
                    {loading ? "Verifying..." : "Verify & Create Account"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    className="w-full mt-2"
                    onClick={() => setStep("details")}
                    disabled={loading}
                  >
                    Back
                  </Button>
                </>
              )}
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                Already have an account?{" "}
                <button
                  onClick={() => router.push("/login")}
                  className="text-primary hover:underline"
                >
                  Sign in
                </button>
              </p>
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

