import Link from "next/link";
import { cookies } from "next/headers";

const LINKS = [
  ["/", "Home"],
  ["/shops", "Shops"],
  ["/inventory", "Inventory"],
  ["/patients", "Patients"],
  ["/prescriptions", "Prescriptions"],
  ["/sync", "Sync"],
];

export async function Shell({ children }: { children: React.ReactNode }) {
  const csrf = (await cookies()).get("pharmacare_csrf")?.value || "";
  return (
    <div className="grid min-h-screen grid-cols-1 md:grid-cols-[220px_1fr]">
      <aside className="bg-[#123c3a] text-white">
        <div className="px-5 py-6">
          <p className="text-lg font-semibold">PharmaCare</p>
          <p className="text-sm text-teal-100">Owner</p>
        </div>
        <nav className="flex flex-col gap-1 px-3">
          {LINKS.map(([href, label]) => (
            <Link key={href} href={href} className="rounded-lg px-3 py-2 text-sm hover:bg-white/10">{label}</Link>
          ))}
        </nav>
        <form action="/api/auth/logout" method="post" className="px-3 py-6">
          <input type="hidden" name="csrf" value={csrf} />
          <button className="w-full rounded-lg border border-white/30 px-3 py-2 text-sm" type="submit">Sign out</button>
        </form>
      </aside>
      <main className="px-5 py-6 md:px-8">{children}</main>
    </div>
  );
}
