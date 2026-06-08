import { NavLink } from "react-router-dom";
import {
  Activity,
  CalendarCheck,
  FileText,
  MessageSquare,
  GraduationCap,
} from "lucide-react";

const navItems = [
  { to: "/", label: "今日复习", icon: CalendarCheck },
  { to: "/documents", label: "复习资料", icon: FileText },
  { to: "/chat", label: "知识问答", icon: MessageSquare },
  { to: "/learning", label: "复习训练", icon: GraduationCap },
];

export function Sidebar() {
  return (
    <aside className="w-60 bg-gray-950 text-gray-100 flex flex-col min-h-screen">
      <div className="px-5 py-5 border-b border-gray-800">
        <h1 className="text-lg font-semibold">期末复习助手</h1>
        <p className="mt-1 text-xs text-gray-400">把课件变成可复习的知识库</p>
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
                  ? "bg-white text-gray-950"
                  : "text-gray-400 hover:bg-gray-900 hover:text-gray-100"
              }`
            }
          >
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-gray-800 px-5 py-4 text-xs leading-5 text-gray-500">
        先上传资料，再围绕当前科目提问、测验和复习。
        <NavLink
          to="/monitoring"
          className={({ isActive }) =>
            `mt-3 flex items-center gap-2 rounded-lg px-2 py-2 transition-colors ${
              isActive ? "bg-gray-900 text-gray-200" : "text-gray-500 hover:bg-gray-900 hover:text-gray-300"
            }`
          }
        >
          <Activity size={14} />
          系统状态
        </NavLink>
      </div>
    </aside>
  );
}
