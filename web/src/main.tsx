import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, theme, App as AntApp } from "antd";
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
        token: { borderRadius: 8, fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" },
      }}
    >
      <AntApp>
        <App dark={dark} setDark={setDark} />
      </AntApp>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><Root /></React.StrictMode>
);
