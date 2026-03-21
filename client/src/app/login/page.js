"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Zap, AlertCircle, Mail, KeyRound, ArrowRight, ArrowLeft } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function LoginPage() {
  const router = useRouter();
  const { login, verifyOtp, resendOtp } = useAuth();
  const [formData, setFormData] = useState({
    email: "",
    otp: ""
  });
  const [step, setStep] = useState("email");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendSuccess, setResendSuccess] = useState("");

  const handleResend = async () => {
    setResendLoading(true);
    setError("");
    setResendSuccess("");
    const result = await resendOtp(formData.email);
    if (result.success) {
      setResendSuccess("Code resent successfully!");
    } else {
      setError(result.error);
    }
    setResendLoading(false);
  };

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
    <div className="min-h-screen bg-[#030303] text-gray-100 flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Dynamic Background */}
      <div className="absolute top-[-10%] left-[-10%] w-[40vw] h-[40vw] rounded-full bg-indigo-600/20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40vw] h-[40vw] rounded-full bg-purple-600/20 blur-[120px] pointer-events-none" />

      <div className="w-full max-w-md relative z-10">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center p-3 bg-white/5 rounded-2xl border border-white/10 mb-6 shadow-[0_0_30px_rgba(79,70,229,0.2)]">
            <Zap className="text-3xl text-indigo-400" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent mb-2">
            Welcome Back
          </h1>
          <p className="text-gray-400 text-sm">Sign in to your account to continue</p>
        </div>

        <div className="bg-white/[0.03] backdrop-blur-2xl border border-white/10 rounded-3xl p-8 shadow-2xl relative overflow-hidden">
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
          
          <form onSubmit={handleSubmit} className="space-y-6">
            <AnimatePresence mode="wait">
              {error && (
                <motion.div 
                  initial={{ opacity: 0, y: -10 }} 
                  animate={{ opacity: 1, y: 0 }} 
                  exit={{ opacity: 0, y: -10 }}
                  className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-3 text-red-400 text-sm"
                >
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <p className="leading-relaxed">{error}</p>
                </motion.div>
              )}
              {resendSuccess && (
                <motion.div 
                  initial={{ opacity: 0, y: -10 }} 
                  animate={{ opacity: 1, y: 0 }} 
                  exit={{ opacity: 0, y: -10 }}
                  className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-start gap-3 text-emerald-400 text-sm"
                >
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <p className="leading-relaxed">{resendSuccess}</p>
                </motion.div>
              )}
            </AnimatePresence>

            <AnimatePresence mode="wait">
              {step === "email" ? (
                <motion.div 
                  key="email-step"
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  transition={{ duration: 0.3 }}
                  className="space-y-6"
                >
                  <div className="space-y-3">
                    <Label htmlFor="email" className="text-gray-300 ml-1">Email Address</Label>
                    <div className="relative group">
                      <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                        <Mail className="h-5 w-5 text-gray-500 group-focus-within:text-indigo-400 transition-colors" />
                      </div>
                      <Input
                        id="email"
                        type="email"
                        placeholder="hello@example.com"
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        required
                        className="pl-11 h-12 bg-black/40 border-white/10 text-white placeholder:text-gray-600 focus-visible:ring-indigo-500/50 focus-visible:border-indigo-500/50 rounded-xl transition-all"
                      />
                    </div>
                  </div>

                  <Button
                    type="submit"
                    className="w-full h-12 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 text-white font-medium shadow-[0_0_20px_rgba(79,70,229,0.3)] transition-all hover:scale-[1.02] active:scale-[0.98]"
                    disabled={loading}
                  >
                    {loading ? (
                      <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <>
                        Continue <ArrowRight className="w-4 h-4 ml-2" />
                      </>
                    )}
                  </Button>
                </motion.div>
              ) : (
                <motion.div 
                  key="otp-step"
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.3 }}
                  className="space-y-6"
                >
                  <div className="space-y-3">
                    <Label htmlFor="otp" className="text-gray-300 ml-1">Verification Code</Label>
                    <div className="relative group">
                      <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                        <KeyRound className="h-5 w-5 text-gray-500 group-focus-within:text-purple-400 transition-colors" />
                      </div>
                      <Input
                        id="otp"
                        type="text"
                        placeholder="6-digit code"
                        value={formData.otp}
                        onChange={(e) => setFormData({ ...formData, otp: e.target.value })}
                        required
                        maxLength={6}
                        className="pl-11 h-12 bg-black/40 border-white/10 text-white placeholder:text-gray-600 focus-visible:ring-purple-500/50 focus-visible:border-purple-500/50 rounded-xl tracking-widest transition-all"
                      />
                    </div>
                    <p className="text-xs text-gray-500 ml-1">
                      We sent a code to <span className="text-gray-300 font-medium">{formData.email}</span>
                      <br/>
                      <button 
                        type="button" 
                        onClick={handleResend}
                        disabled={resendLoading}
                        className="text-indigo-400 hover:text-indigo-300 transition-colors mt-2"
                      >
                        {resendLoading ? "Sending..." : "Resend Code"}
                      </button>
                    </p>
                  </div>

                  <div className="space-y-3">
                    <Button
                      type="submit"
                      className="w-full h-12 rounded-xl bg-gradient-to-r from-purple-600 flex items-center justify-center to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium shadow-[0_0_20px_rgba(147,51,234,0.3)] transition-all hover:scale-[1.02] active:scale-[0.98]"
                      disabled={loading || formData.otp.length < 6}
                    >
                      {loading ? (
                        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      ) : (
                        "Verify & Sign In"
                      )}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      className="w-full h-12 rounded-xl text-gray-400 hover:text-white hover:bg-white/5 transition-all"
                      onClick={() => setStep("email")}
                    >
                      <ArrowLeft className="w-4 h-4 mr-2" /> Back
                    </Button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </form>

          <div className="mt-8 text-center pt-6 border-t border-white/5">
            <p className="text-sm text-gray-400">
              Don&apos;t have an account?{' '}
              <button 
                onClick={() => router.push("/register")}
                className="font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
                type="button"
              >
                Create one
              </button>
            </p>
          </div>
        </div>

        <div className="text-center mt-8">
          <button
            onClick={() => router.push("/home")}
            className="text-sm text-gray-500 hover:text-gray-300 transition-colors inline-flex items-center"
          >
            <ArrowLeft className="w-4 h-4 mr-2" /> Return to Home
          </button>
        </div>
      </div>
    </div>
  );
}
