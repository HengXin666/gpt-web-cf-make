/** 账号模型 */
export interface Account {
  id: string;
  email: string;
  password: string;
  access_token: string;
  refresh_token: string;
  id_token: string;
  session_token: string;
  oauth_client_id: string;
  oauth_profile: string;
  oauth_scope: string;
  plan_type: string;
  status: "normal" | "abnormal" | "limited" | "disabled";
  quota: number;
  quota_reset_at: string;
  created_at: string;
  last_refreshed_at: string;
  last_used_at: string;
  refresh_error: string;
  tags: string[];
  notes: string;
}

export interface AccountListResponse {
  items: Account[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AccountStats {
  total: number;
  normal: number;
  abnormal: number;
  limited: number;
  disabled: number;
  total_quota: number;
}

export interface TokenStats {
  total: number;
  valid: number;
  expiring_soon: number;
  expired: number;
  no_token: number;
  abnormal: number;
}

export interface BatchResult {
  refreshed: number;
  failed: number;
  errors: Array<{ id: string; error: string }>;
}

export interface RegisterConfig {
  mail: MailConfig;
  proxy: string;
  total: number;
  threads: number;
  mode: "total" | "quota" | "available";
  target_quota: number;
  target_available: number;
  check_interval: number;
  enabled: boolean;
  stats: RegisterStats;
  logs: LogEntry[];
}

export interface MailConfig {
  request_timeout: number;
  wait_timeout: number;
  wait_interval: number;
  proxy: string;
  providers: MailProvider[];
}

export interface MailProvider {
  enable: boolean;
  type: string;
  api_base?: string;
  api_key?: string;
  admin_auth?: string;
  admin_email?: string;
  admin_password?: string;
  custom_auth?: string;
  domain?: string[];
  subdomain?: string | string[];
  default_domain?: string;
  email_prefix?: string;
  enable_random_subdomain?: boolean;
  receive_mailbox_jwt?: string;
  cf_domain?: string[];
  ddg_token?: string;
  cf_inbox_jwt?: string;
  random_subdomain?: boolean;
  wildcard?: boolean;
  [key: string]: unknown;
}

export interface RegisterStats {
  job_id: string;
  success: number;
  fail: number;
  done: number;
  running: number;
  threads: number;
  elapsed_seconds: number;
  avg_seconds: number;
  success_rate: number;
  current_quota: number;
  current_available: number;
  started_at: string;
  updated_at: string;
  finished_at: string;
}

export interface LogEntry {
  time: string;
  text: string;
  level: "info" | "yellow" | "green" | "red";
}

export interface AppConfig {
  proxy: string;
  fixed_password: string;
  oauth_profile: string;
  oauth: Record<string, string>;
  codex_oauth: Record<string, string>;
  token_refresh: TokenRefreshConfig;
  chatgpt2api: Record<string, string>;
  infinite_canvas: Record<string, string>;
  [key: string]: unknown;
}

export interface TokenRefreshConfig {
  enabled: boolean;
  interval_minutes: number;
  expiring_days: number;
  max_workers: number;
  retry_failed_only: boolean;
}

export interface Chatgpt2apiExport {
  accounts: Array<Record<string, unknown>>;
  auth_keys: Array<Record<string, unknown>>;
  count: number;
}

export interface InfiniteCanvasExport {
  channels: Array<Record<string, unknown>>;
  count: number;
  pushed: boolean;
}
