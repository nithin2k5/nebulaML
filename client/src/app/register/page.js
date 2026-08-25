"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { Zap, AlertCircle, ArrowLeft } from "lucide-react";

function GridBackground() {
  return (
    <div className="fixed inset-0 z-0 pointer-events-none opacity-20">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#a78bfa15_1px,transparent_1px),linear-gradient(to_bottom,#a78bfa15_1px,transparent_1px)] bg-[size:4rem_4rem]" />
    </div>
  );
}

function BoundingBox({ label, children, className, score = "sys.ok" }) {
  return (
    <div className={`relative border border-violet-500/40 bg-black/50 backdrop-blur-sm ${className}`}>
      <div className="absolute -top-[1px] -left-[1px] bg-violet-500 text-black text-[10px] font-mono font-bold px-2 py-0.5 flex items-center gap-2 z-10">
        <span>{label}</span>
        <span className="opacity-70">{score}</span>
      </div>
      <div className="absolute -top-1 -left-1 w-2 h-2 border-t border-l border-violet-400" />
      <div className="absolute -top-1 -right-1 w-2 h-2 border-t border-r border-violet-400" />
      <div className="absolute -bottom-1 -left-1 w-2 h-2 border-b border-l border-violet-400" />
      <div className="absolute -bottom-1 -right-1 w-2 h-2 border-b border-r border-violet-400" />
      {children}
    </div>
  );
}

export default function RegisterPage() {
  const router = useRouter();
  const { register, verifyOtp, resendOtp } = useAuth();
  const [formData, setFormData] = useState({ username: "", email: "", otp: "", role: "user" });
  const [step, setStep] = useState("details");
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

    if (step === "details") {
      const result = await register(formData.username, formData.email, formData.role);
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
    <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center p-4 relative overflow-hidden cursor-crosshair">
      <GridBackground />

      <div className="w-full max-w-md relative z-10">
        <BoundingBox label="INIT_WORKSPACE" score="1.00" className="p-8 pb-10">
          <div className="mb-10 border-b border-white/10 pb-6 mt-2">
            <h1 className="text-2xl font-bold uppercase tracking-tight flex items-center gap-2">
              <Zap className="w-5 h-5 text-violet-500" />
              CREATE_ACCOUNT
            </h1>
            <p className="text-gray-500 font-mono text-xs mt-2 uppercase">Allocate new resources for user.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6 relative z-10">
            {error && (
              <div className="p-3 border border-red-500/30 bg-red-500/10 flex items-start gap-3 text-red-400 text-xs font-mono">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <p>{error}</p>
              </div>
            )}
            
            {resendSuccess && (
              <div className="p-3 border border-violet-500/30 bg-violet-500/10 flex items-start gap-3 text-violet-400 text-xs font-mono">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <p>{resendSuccess}</p>
              </div>
            )}

            {step === "details" ? (
              <div className="space-y-6">
                <div className="space-y-2 flex flex-col">
                  <label htmlFor="username" className="text-violet-400 font-mono text-xs uppercase">Alias [Username]</label>
                  <input
                    id="username"
                    type="text"
                    placeholder="sys.admin"
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    required
                    className="h-10 bg-black border border-white/20 text-white placeholder:text-gray-600 focus:border-violet-500 focus:outline-none px-3 font-mono text-sm transition-colors"
                  />
                </div>

                <div className="space-y-2 flex flex-col">
                  <label htmlFor="email" className="text-violet-400 font-mono text-xs uppercase">Identity [Email]</label>
                  <input
                    id="email"
                    type="email"
                    placeholder="sys.admin@example.com"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    required
                    className="h-10 bg-black border border-white/20 text-white placeholder:text-gray-600 focus:border-violet-500 focus:outline-none px-3 font-mono text-sm transition-colors"
                  />
                </div>

                <div className="space-y-2 flex flex-col">
                  <label htmlFor="role" className="text-violet-400 font-mono text-xs uppercase">Privilege_Level [Role]</label>
                  <select
                    id="role"
                    value={formData.role}
                    onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                    className="h-10 bg-black border border-white/20 text-white focus:border-violet-500 focus:outline-none px-3 font-mono text-sm transition-colors cursor-pointer appearance-none"
                  >
                    <option value="user">USER [FULL_ACCESS]</option>
                    <option value="viewer">VIEWER [READ_ONLY]</option>
                  </select>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full h-10 bg-violet-500 hover:bg-violet-400 text-black font-mono font-bold text-xs uppercase transition-colors disabled:opacity-50 mt-4"
                >
                  {loading ? "[ PROCESSING... ]" : "EXECUTE"}
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="space-y-2 flex flex-col">
                  <label htmlFor="otp" className="text-violet-400 font-mono text-xs uppercase">Auth_Token [OTP]</label>
                  <input
                    id="otp"
                    type="text"
                    placeholder="000000"
                    value={formData.otp}
                    onChange={(e) => setFormData({ ...formData, otp: e.target.value })}
                    required
                    maxLength={6}
                    className="h-10 bg-black border border-white/20 text-white placeholder:text-gray-600 focus:border-violet-500 focus:outline-none px-3 font-mono text-sm tracking-[0.5em] transition-colors text-center"
                  />
                  <div className="flex justify-between items-center mt-2">
                    <span className="text-xs font-mono text-gray-500">Sent to: {formData.email}</span>
                    <button 
                      type="button" 
                      onClick={handleResend}
                      disabled={resendLoading}
                      className="text-xs font-mono text-violet-400 hover:text-white transition-colors"
                    >
                      {resendLoading ? "SENDING..." : "[ RESEND ]"}
                    </button>
                  </div>
                </div>

                <div className="flex flex-col gap-3">
                  <button
                    type="submit"
                    disabled={loading || formData.otp.length < 6}
                    className="w-full h-10 bg-violet-500 hover:bg-violet-400 text-black font-mono font-bold text-xs uppercase transition-colors disabled:opacity-50"
                  >
                    {loading ? "[ PROCESSING... ]" : "VERIFY"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setStep("details")}
                    className="w-full h-10 border border-white/20 hover:border-white/60 text-white font-mono text-xs uppercase transition-colors"
                  >
                    [ GO_BACK ]
                  </button>
                </div>
              </div>
            )}
          </form>

          <div className="mt-8 border-t border-white/10 pt-4 flex justify-between relative z-10">
            <button 
              onClick={() => router.push("/login")}
              className="font-mono text-xs text-gray-400 hover:text-white transition-colors uppercase"
            >
              [ EXISTING_ACCOUNT_LOGIN ]
            </button>
          </div>
        </BoundingBox>

        <div className="mt-6 flex justify-center">
          <button
            onClick={() => router.push("/home")}
            className="font-mono text-xs text-gray-500 hover:text-white transition-colors flex items-center gap-2 uppercase"
          >
            <ArrowLeft className="w-3 h-3" /> ABORT_TO_HOME
          </button>
        </div>
      </div>
    </div>
  );
}
