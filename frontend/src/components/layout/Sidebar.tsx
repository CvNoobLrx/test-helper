import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  MessageSquare,
  GraduationCap,
  Activity,
} from "lucide-react";

const navItems = [
  { to: "/", label: "总览", icon: LayoutDashboard },
  { to: "/documents", label: "复习资料", icon: FileText },
  { to: "/chat", label: "知识问答", icon: MessageSquare },
  { to: "/learning", label: "复习计划", icon: GraduationCap },
  { to: "/monitoring", label: "运行状态", icon: Activity },
];

export function Sidebar() {
  return (
    <aside className="w-56 bg-gray-900 text-gray-100 flex flex-col min-h-screen">
      <div className="px-4 py-5 border-b border-gray-700">
        <h1 className="text-lg font-semibold">期末复习助手</h1>
      </div>
      <nav className="flex-1 px-2 py-4 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
              }`
            }
          >
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
