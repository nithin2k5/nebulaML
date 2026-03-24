import { Suspense } from "react";
import InviteClient from "./InviteClient";

export const dynamic = "force-dynamic";

function InviteFallback() {
  return (
    <div className="flex h-screen items-center justify-center bg-black">
      <div className="h-8 w-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
    </div>
  );
}

export default function InvitePage() {
  return (
    <Suspense fallback={<InviteFallback />}>
      <InviteClient />
    </Suspense>
  );
}
