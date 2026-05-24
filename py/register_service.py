"""注册机编排服务 - 线程池管理、SSE 状态推送、日志记录"""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config_service import DATA_DIR
from .account_service import account_service
from .shared.models import RegisterConfig, RegisterStats, LogEntry, _now

REGISTER_STATE_FILE = DATA_DIR / "register_state.json"


class RegisterService:
    """注册机编排服务 - 管理注册配置、任务运行、统计和日志"""

    def __init__(self, store_file: Path = REGISTER_STATE_FILE):
        self._store_file = store_file
        self._lock = threading.RLock()
        self._runner: threading.Thread | None = None
        self._logs: list[LogEntry] = []
        self._config: RegisterConfig = self._load()
        if self._config.enabled:
            self.start()

    def _load(self) -> RegisterConfig:
        """从 JSON 文件加载注册配置"""
        try:
            if self._store_file.exists():
                data = json.loads(self._store_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    config_data = {k: v for k, v in data.items()
                                   if k not in ("stats", "logs", "enabled")}
                    config = RegisterConfig.from_dict(config_data)
                    # 恢复 enabled 状态
                    if data.get("enabled"):
                        config.enabled = True
                    return config
        except Exception:
            pass
        return RegisterConfig()

    def _save(self) -> None:
        """保存注册配置到 JSON 文件"""
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        config_dict = self._config.to_dict()
        self._store_file.write_text(
            json.dumps(config_dict, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self) -> dict[str, Any]:
        """获取完整的注册状态（配置 + 统计 + 日志）"""
        with self._lock:
            return {
                **self._config.to_dict(),
                "stats": self._stats.to_dict() if hasattr(self, "_stats") else {},
                "logs": [log.to_dict() for log in self._logs[-300:]],
            }

    def _init_stats(self) -> None:
        """初始化统计信息"""
        self._stats = RegisterStats(
            job_id=uuid.uuid4().hex,
            threads=self._config.threads,
            started_at=_now(),
            updated_at=_now(),
        )

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        """更新注册配置"""
        with self._lock:
            current = self._config.to_dict()
            current.update({k: v for k, v in updates.items() if k not in ("enabled", "stats", "logs")})
            self._config = RegisterConfig.from_dict(current)
            self._inject_proxy_to_mail()
            self._save()
            return self.get()

    def _inject_proxy_to_mail(self) -> None:
        """将代理注入到邮件配置中"""
        proxy = self._config.proxy
        if proxy and isinstance(self._config.mail, dict):
            self._config.mail["proxy"] = proxy

    def _pool_metrics(self) -> dict[str, int]:
        """获取当前号池指标"""
        stats = account_service.get_stats()
        return {
            "current_quota": stats["total_quota"],
            "current_available": stats["normal"],
        }

    def _target_reached(self, submitted: int) -> bool:
        """检查是否达到注册目标"""
        mode = self._config.mode
        metrics = self._pool_metrics()
        self._bump(**metrics)
        if mode == "quota":
            reached = metrics["current_quota"] >= self._config.target_quota
            log = f"检查号池：正常账号={metrics['current_available']}，剩余额度={metrics['current_quota']}，目标额度={self._config.target_quota}，{'跳过注册' if reached else '继续注册'}"
            self._append_log(log, "yellow")
            return reached
        if mode == "available":
            reached = metrics["current_available"] >= self._config.target_available
            log = f"检查号池：正常账号={metrics['current_available']}，目标账号={self._config.target_available}，剩余额度={metrics['current_quota']}，{'跳过注册' if reached else '继续注册'}"
            self._append_log(log, "yellow")
            return reached
        return submitted >= self._config.total

    def _bump(self, **updates: Any) -> None:
        """更新统计信息"""
        with self._lock:
            for key, value in updates.items():
                if hasattr(self._stats, key):
                    setattr(self._stats, key, value)
            stats = self._stats
            if stats.started_at:
                try:
                    elapsed = max(0.0, (datetime.now(timezone.utc) -
                                        datetime.fromisoformat(stats.started_at)).total_seconds())
                except Exception:
                    elapsed = 0.0
                stats.elapsed_seconds = round(elapsed, 1)
                stats.avg_seconds = round(elapsed / stats.success, 1) if stats.success else 0
                stats.success_rate = round(stats.success * 100 / max(1, stats.success + stats.fail), 1)
            stats.updated_at = _now()
            self._save()

    def _append_log(self, text: str, level: str = "info") -> None:
        """添加日志条目"""
        with self._lock:
            self._logs.append(LogEntry(time=_now(), text=str(text), level=str(level)))
            self._logs = self._logs[-300:]

    def start(self) -> dict[str, Any]:
        """启动注册任务"""
        with self._lock:
            if self._runner and self._runner.is_alive():
                self._config.enabled = True
                self._save()
                return self.get()
            self._config.enabled = True
            self._inject_proxy_to_mail()
            self._logs = []
            self._init_stats()
            metrics = self._pool_metrics()
            self._stats.current_quota = metrics["current_quota"]
            self._stats.current_available = metrics["current_available"]
            self._save()
            self._runner = threading.Thread(target=self._run, daemon=True, name="gpt-register-runner")
            self._runner.start()
            self._append_log(f"注册任务启动，模式={self._config.mode}，线程数={self._config.threads}", "yellow")
            return self.get()

    def stop(self) -> dict[str, Any]:
        """停止注册任务"""
        with self._lock:
            self._config.enabled = False
            self._stats.updated_at = _now()
            self._save()
            self._append_log("已请求停止注册任务，正在等待当前运行任务结束", "yellow")
            return self.get()

    def reset(self) -> dict[str, Any]:
        """重置统计信息"""
        with self._lock:
            self._logs = []
            self._init_stats()
            self._save()
            return self.get()

    def _worker(self, index: int) -> dict[str, Any]:
        """注册工作线程 - 执行单次注册"""
        from .register.registrar import auto_register
        from .config_service import config_service
        from .shared.models import _now

        try:
            config = config_service.get()
            proxy = config_service.get_proxy()
            fixed_password = str(config.get("fixed_password") or "").strip()
            oauth_profile = str(config.get("oauth_profile") or "platform").strip()
            token_oauth = config_service.get_oauth(oauth_profile)

            if fixed_password:
                self._append_log(f"#{index} 使用配置的固定密码", "info")
            else:
                self._append_log(f"#{index} 未配置固定密码，将随机生成", "yellow")

            result = auto_register(
                mail_config=self._config.mail,
                proxy=proxy,
                token_oauth=token_oauth,
                fixed_password=fixed_password,
                log_callback=self._append_log,
            )
            # 注册成功，添加到账号池
            account_service.add_accounts([{
                **result,
                "status": "normal",
                "last_refreshed_at": _now(),
            }])
            self._append_log(f"#{index} 注册成功: {result.get('email', '?')}", "green")
            return {"ok": True, "email": result.get("email", "")}
        except Exception as exc:
            self._append_log(f"#{index} 注册失败: {exc}", "red")
            return {"ok": False, "error": str(exc)}

    def _run(self) -> None:
        """注册任务主循环 - 在线程池中运行"""
        threads = max(1, self._config.threads)
        submitted, done, success, fail = 0, 0, 0, 0
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures: set = set()
            while True:
                cfg = self._config
                while self._config.enabled and not self._target_reached(submitted) and len(futures) < threads:
                    submitted += 1
                    futures.add(executor.submit(self._worker, submitted))
                self._bump(running=len(futures), done=done, success=success, fail=fail)
                if not futures and (not self._config.enabled or cfg.mode == "total"):
                    break
                if not futures:
                    time.sleep(max(1, self._config.check_interval))
                    continue
                finished, futures = wait(futures, return_when=FIRST_COMPLETED)
                for future in finished:
                    done += 1
                    try:
                        result = future.result()
                        success += 1 if result.get("ok") else 0
                        fail += 0 if result.get("ok") else 1
                    except Exception:
                        fail += 1
        self._bump(running=0, done=done, success=success, fail=fail, finished_at=_now())
        with self._lock:
            self._config.enabled = False
            self._save()
        self._append_log(f"注册任务结束，成功{success}，失败{fail}", "yellow")


# 全局单例
register_service = RegisterService()
