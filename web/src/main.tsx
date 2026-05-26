import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, theme, App as AntApp } from "antd";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

function Root() {
  const [dark, setDark] = React.useState(() => localStorage.getItem("gpt-cf-dark") === "true");

  React.useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  return (
    <ConfigProvider
      theme={{
        algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: "#2563eb",
          colorSuccess: "#059669",
          colorWarning: "#d97706",
          colorError: "#dc2626",
          borderRadius: 8,
          fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
        components: {
          Button: { controlHeight: 34, borderRadius: 8 },
          Card: { borderRadiusLG: 10, paddingLG: 18 },
          Table: { headerBg: dark ? "#111827" : "#f8fafc", rowHoverBg: dark ? "#182133" : "#f8fbff" },
          Tag: { borderRadiusSM: 999 },
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <App dark={dark} setDark={setDark} />
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><Root /></React.StrictMode>
);
