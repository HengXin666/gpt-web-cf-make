import { useEffect, useMemo, useState } from "react";
import { Button, Tooltip } from "antd";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  DatabaseZap,
  KeyRound,
  Moon,
  Settings,
  ShieldCheck,
  Sun,
  Users,
} from "lucide-react";
import AccountsPage from "./pages/AccountsPage";
import RegisterPage from "./pages/RegisterPage";
import SettingsPage from "./pages/SettingsPage";

type Page = "accounts" | "register" | "settings";

const pageMeta: Record<Page, {
  label: string;
  desc: string;
  icon: React.ComponentType<{ className?: string }>;
}> = {
  accounts: {
    label: "账号与配额",
    desc: "Token 库、配额状态、批量续期",
    icon: Users,
  },
  register: {
    label: "注册流水线",
    desc: "邮箱 Provider、线程、实时日志",
    icon: KeyRound,
  },
  settings: {
    label: "系统策略",
    desc: "OAuth、保活、外部导出",
    icon: Settings,
  },
};

export default function App({ dark, setDark }: { dark: boolean; setDark: (v: boolean) => void }) {
  const [page, setPage] = useState<Page>(() => {
    const stored = localStorage.getItem("gpt-cf-page") as Page | null;
    return stored && stored in pageMeta ? stored : "accounts";
  });

  useEffect(() => {
    localStorage.setItem("gpt-cf-page", page);
  }, [page]);

  useEffect(() => {
    localStorage.setItem("gpt-cf-dark", String(dark));
  }, [dark]);

  const ActiveIcon = pageMeta[page].icon;
  const pageBody = useMemo(() => {
    if (page === "accounts") return <AccountsPage />;
    if (page === "register") return <RegisterPage />;
    return <SettingsPage />;
  }, [page]);

  return (
    <div className="console-shell">
      <aside className="console-rail">
        <div className="brand-lockup">
          <div className="brand-mark">
            <DatabaseZap className="size-5" />
          </div>
          <div className="brand-copy">
            <strong>GPT-CF-Make</strong>
            <span>Token Ops Console</span>
          </div>
        </div>

        <nav className="console-nav" aria-label="主导航">
          {(Object.keys(pageMeta) as Page[]).map((key) => {
            const item = pageMeta[key];
            const Icon = item.icon;
            const active = page === key;
            return (
              <button
                key={key}
                className={`nav-item ${active ? "is-active" : ""}`}
                type="button"
                onClick={() => setPage(key)}
              >
                <Icon className="size-4" />
                <span>{item.label}</span>
                {active && <motion.i layoutId="nav-cursor" className="nav-cursor" />}
              </button>
            );
          })}
        </nav>

        <div className="rail-status">
          <div className="status-led" />
          <div>
            <strong>运行面板在线</strong>
            <span>实时读写本地 API</span>
          </div>
        </div>
      </aside>

      <main className="console-main">
        <header className="console-topbar">
          <div className="page-kicker">
            <span className="page-icon"><ActiveIcon className="size-4" /></span>
            <div>
              <h1>{pageMeta[page].label}</h1>
              <p>{pageMeta[page].desc}</p>
            </div>
          </div>

          <div className="topbar-actions">
            <div className="signal-chip">
              <Activity className="size-3.5" />
              <span>Token telemetry</span>
            </div>
            <div className="signal-chip hide-sm">
              <ShieldCheck className="size-3.5" />
              <span>Local first</span>
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

        <section className="console-content">
          <AnimatePresence mode="wait">
            <motion.div
              key={page}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
              {pageBody}
            </motion.div>
          </AnimatePresence>
        </section>
      </main>
    </div>
  );
}
