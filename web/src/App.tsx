import { useState, useEffect, useCallback } from "react";
import { Layout, Tabs, Button } from "antd";
import { Users, KeyRound, Settings, Sun, Moon } from "lucide-react";
import AccountsPage from "./pages/AccountsPage";
import RegisterPage from "./pages/RegisterPage";
import SettingsPage from "./pages/SettingsPage";

const { Header, Content } = Layout;

type Page = "accounts" | "register" | "settings";

export default function App({ dark, setDark }: { dark: boolean; setDark: (v: boolean) => void }) {
  const [page, setPage] = useState<Page>(() => {
    return (localStorage.getItem("gpt-cf-page") as Page) || "accounts";
  });

  useEffect(() => {
    localStorage.setItem("gpt-cf-page", page);
  }, [page]);

  useEffect(() => {
    localStorage.setItem("gpt-cf-dark", String(dark));
  }, [dark]);

  const tabItems = [
    { key: "accounts", label: <span className="flex items-center gap-1.5"><Users className="size-3.5" />账号管理</span> },
    { key: "register", label: <span className="flex items-center gap-1.5"><KeyRound className="size-3.5" />注册机</span> },
    { key: "settings", label: <span className="flex items-center gap-1.5"><Settings className="size-3.5" />设置</span> },
  ];

  return (
    <Layout className="min-h-screen" style={{ background: dark ? "#141414" : "#fff" }}>
      <Header style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        height: 48, lineHeight: "48px", padding: "0 16px",
        background: dark ? "#1f1f1f" : "#fff",
        borderBottom: dark ? "1px solid #303030" : "1px solid #e8e8e8",
      }}>
        <div className="flex items-center gap-3">
          <span className="text-base font-bold" style={{ color: "#1677ff" }}>
            GPT-CF-Make
          </span>
          <span className="hidden sm:inline text-xs text-gray-400">
            Token 保活平台
          </span>
        </div>

        <Tabs
          activeKey={page}
          onChange={(k) => setPage(k as Page)}
          size="small"
          style={{ marginBottom: 0 }}
          items={tabItems}
        />

        <Button
          type="text"
          size="small"
          icon={dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          onClick={() => setDark(!dark)}
        />
      </Header>

      <Content style={{ padding: 16 }}>
        {page === "accounts" && <AccountsPage />}
        {page === "register" && <RegisterPage />}
        {page === "settings" && <SettingsPage />}
      </Content>
    </Layout>
  );
}
