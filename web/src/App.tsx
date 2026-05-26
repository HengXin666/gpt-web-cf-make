import { useEffect } from "react";
import { Button, Tooltip } from "antd";
import { AnimatePresence, motion } from "framer-motion";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  Activity,
  BarChart3,
  DatabaseZap,
  Info,
  KeyRound,
  MessageSquareText,
  Moon,
  Settings,
  ShieldCheck,
  Sun,
  Users,
} from "lucide-react";
import AccountsPage from "./pages/AccountsPage";
import AboutPage from "./pages/AboutPage";
import ChatPage from "./pages/ChatPage";
import ProxyPage from "./pages/ProxyPage";
import RegisterPage from "./pages/RegisterPage";
import SettingsPage from "./pages/SettingsPage";

const navItems = [
  { to: "/accounts", label: "账号与配额", desc: "Token 库、配额状态、批量续期", icon: Users },
  { to: "/proxy", label: "反代与用量", desc: "Base URL、API Key、请求统计", icon: BarChart3 },
  { to: "/chat", label: "对话调试", desc: "单轮 Chat、图片、流式响应", icon: MessageSquareText },
  { to: "/register", label: "注册流水线", desc: "邮箱 Provider、线程、实时日志", icon: KeyRound },
  { to: "/settings/basic", label: "系统设置", desc: "代理、OAuth、保活", icon: Settings },
  { to: "/about", label: "关于", desc: "作者与仓库信息", icon: Info },
];

function activeMeta(pathname: string) {
  return navItems.find((item) => pathname.startsWith(item.to.replace("/basic", ""))) || navItems[0];
}

export default function App({ dark, setDark }: { dark: boolean; setDark: (v: boolean) => void }) {
  const location = useLocation();
  const meta = activeMeta(location.pathname);
  const ActiveIcon = meta.icon;

  useEffect(() => {
    localStorage.setItem("gpt-cf-dark", String(dark));
  }, [dark]);

  return (
    <div className="console-shell">
      <aside className="console-rail">
        <div className="brand-lockup">
          <div className="brand-mark">
            <DatabaseZap className="size-5" />
          </div>
          <div className="brand-copy">
            <strong>Token 控制台</strong>
            <span>GPT-CF-Make</span>
          </div>
        </div>

        <nav className="console-nav" aria-label="主导航">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = item.to.startsWith("/settings") ? location.pathname.startsWith("/settings") : location.pathname === item.to;
            return (
              <NavLink key={item.to} to={item.to} className={`nav-item ${active ? "is-active" : ""}`}>
                {() => (
                  <>
                    <Icon className="size-4" />
                    <span>{item.label}</span>
                    {active && <motion.i layoutId="nav-cursor" className="nav-cursor" />}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        <div className="rail-status">
          <div className="status-led" />
          <div>
            <strong>本地 API 已接入</strong>
            <span>支持逐账号刷新日志</span>
          </div>
        </div>
      </aside>

      <main className="console-main">
        <header className="console-topbar">
          <div className="page-kicker">
            <span className="page-icon"><ActiveIcon className="size-4" /></span>
            <div>
              <h1>{meta.label}</h1>
              <p>{meta.desc}</p>
            </div>
          </div>

          <div className="topbar-actions">
            <div className="signal-chip">
              <Activity className="size-3.5" />
              <span>实时反馈</span>
            </div>
            <div className="signal-chip hide-sm">
              <ShieldCheck className="size-3.5" />
              <span>本地配置</span>
            </div>
            <Tooltip title={dark ? "切换到亮色模式" : "切换到深色模式"}>
              <Button
                className="theme-toggle"
                type="text"
                icon={dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
                onClick={() => setDark(!dark)}
              />
            </Tooltip>
          </div>
        </header>

        <section className={`console-content ${location.pathname === "/accounts" ? "is-fixed" : ""}`}>
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.16 }}
            >
              <Routes location={location}>
                <Route path="/" element={<Navigate to="/accounts" replace />} />
                <Route path="/accounts" element={<AccountsPage />} />
                <Route path="/proxy" element={<ProxyPage />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/settings" element={<Navigate to="/settings/basic" replace />} />
                <Route path="/settings/:section" element={<SettingsPage />} />
                <Route path="/about" element={<AboutPage />} />
                <Route path="*" element={<Navigate to="/accounts" replace />} />
              </Routes>
            </motion.div>
          </AnimatePresence>
        </section>
      </main>
    </div>
  );
}
