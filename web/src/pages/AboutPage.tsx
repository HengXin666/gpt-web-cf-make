import { Card } from "antd";
import { ExternalLink, UserRound } from "lucide-react";

export default function AboutPage() {
  return (
    <div className="settings-stack">
      <div className="section-head">
        <div>
          <h2 className="section-title">关于</h2>
          <p className="section-desc">项目作者与代码仓库信息。</p>
        </div>
      </div>

      <Card className="surface about-card">
        <div className="about-row">
          <UserRound className="size-5" />
          <div>
            <strong>作者</strong>
            <span>Heng_Xin</span>
          </div>
        </div>
        <div className="about-row">
          <ExternalLink className="size-5" />
          <div>
            <strong>GitHub</strong>
            <a href="https://github.com/HengXin666/gpt-web-cf-make" target="_blank" rel="noreferrer">
              https://github.com/HengXin666/gpt-web-cf-make
            </a>
          </div>
        </div>
      </Card>
    </div>
  );
}
