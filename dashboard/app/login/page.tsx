import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { LoginForm } from "./LoginForm";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const token = (await cookies()).get("pharmacare_csrf")?.value;
  if (!token) redirect("/api/auth/csrf?next=/login");
  return (
    <div className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-line bg-white p-8 shadow-sm">
        <p className="text-sm text-teal">PharmaCare</p>
        <h1 className="mt-1 text-2xl font-semibold">Owner sign-in</h1>
        <p className="mb-6 mt-2 text-sm text-muted">Read-only. Shop stock and prescriptions are not changed here.</p>
        <LoginForm csrf={token} />
      </div>
    </div>
  );
}
