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
  last_chat_used_at?: string;
  last_image_used_at?: string;
  usage_last_used_at?: string;
  usage_input_tokens?: number;
  usage_cached_input_tokens?: number;
  usage_output_tokens?: number;
  usage_image_input_tokens?: number;
  usage_image_output_tokens?: number;
  usage_total_tokens?: number;
  refresh_error: string;
  tags: string[];
  notes: string;
  proxy_node_id: string;
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

export interface RefreshJob {
  job_id: string;
  action: "quota" | "token";
  total: number;
}

export interface RefreshJobEvent {
  type: "start" | "progress" | "done";
  action?: "quota" | "token";
  status?: "running" | "success" | "failed";
  index?: number;
  total?: number;
  id?: string;
  email?: string;
  quota?: number;
  plan_type?: string;
  error?: string;
  error_group?: string;
  retryable?: boolean;
  refreshed?: number;
  failed?: number;
  failed_ids?: string[];
  failed_items?: RefreshJobFailure[];
}

export interface RefreshJobFailure {
  id: string;
  email: string;
  error: string;
  error_group: string;
  retryable: boolean;
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
  fixed_password: string;
  proxy_node_id: string;
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
  proxy_mode: "single" | "pool";
  oauth_profile: string;
  oauth: Record<string, string>;
  codex_oauth: Record<string, string>;
  token_refresh: TokenRefreshConfig;
  http: HttpConfig;
  reverse_proxy: ReverseProxyConfig;
  [key: string]: unknown;
}

export interface HttpConfig {
  version: "http2" | "http1.1";
}

export interface TokenRefreshConfig {
  enabled: boolean;
  interval_minutes: number;
  expiring_days: number;
  max_workers: number;
  retry_failed_only: boolean;
}

export interface ProxyTestResult {
  ok: boolean;
  status: number;
  latency_ms: number;
  http_version: string;
  target: string;
  error?: string;
}

export interface ProxyPurityAiService {
  name: string;
  url: string;
  reachable: boolean;
  status: number;
  latency_ms: number;
  error?: string;
}

export interface ProxyPurityResult {
  score: number;
  grade: "pure" | "clean" | "moderate" | "risky" | "dirty";
  ip: string;
  country: string;
  city: string;
  isp: string;
  asn: string;
  org: string;
  lat: number;
  lon: number;
  ip_type: "residential" | "datacenter" | "mobile" | "unknown";
  is_proxy: boolean;
  is_hosting: boolean;
  is_mobile: boolean;
  tls: {
    ja3: string;
    ja4: string;
    http2_fingerprint: string;
    impersonate_ok: boolean;
    source: string;
  };
  ipv6: { leak: boolean; ipv6: string | null; note: string };
  dns: { leak: boolean; exit_ip?: string; note: string };
  ai_services: ProxyPurityAiService[];
  deductions: Array<{ reason: string; points: number }>;
  suggestions: Array<{ issue: string; guide: string }>;
  error?: string;
}

export interface UpstreamModelsResult {
  models: string[];
  source: string;
}

export interface ReverseProxyConfig {
  enabled: boolean;
  upstream_base_url: string;
  strategy: "round_robin" | "random";
  timeout_seconds: number;
  max_retries: number;
  continue_on_timeout: boolean;
  remember_keys: boolean;
  models: string[];
}

export interface ProxyStatus {
  enabled: boolean;
  base_url: string;
  v1_base_url: string;
  upstream_base_url: string;
  strategy: string;
  timeout_seconds: number;
  max_retries: number;
  continue_on_timeout: boolean;
  available_accounts: number;
  keys: number;
}

export interface ProxyKey {
  id: string;
  name: string;
  key?: string;
  enabled: boolean;
  created_at: string;
  last_used_at: string;
}

export interface ProxyKeyCreated extends ProxyKey {
  key: string;
}

export interface ProxyUsageRecord {
  request_id?: string;
  state?: "running" | "success" | "failed";
  time: string;
  api_key: { id?: string; name?: string };
  account: { id?: string; email?: string };
  path: string;
  method: string;
  model: string;
  status_code: number;
  latency_ms: number;
  success: boolean;
  stream?: boolean;
  stream_chunks?: number;
  stream_logs?: Array<{ time: string; message: string }>;
  request_bytes: number;
  response_bytes: number;
  usage: {
    prompt_tokens?: number;
    cached_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    image_input_tokens?: number;
    image_output_tokens?: number;
    image_count?: number;
    estimated?: boolean;
  };
  cost?: ProxyUsageCost;
  error?: string;
  attempt_count?: number;
  attempts?: ProxyUsageAttempt[];
}

export interface ProxyUsageAttempt {
  account: { id?: string; email?: string };
  status_code: number;
  latency_ms: number;
  success: boolean;
  response_bytes: number;
  error?: string;
}

export interface ProxyUsageSummary {
  total: number;
  success: number;
  failed: number;
  running: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  by_key: Array<{ name: string; requests: number; success: number; failed: number; tokens: number }>;
  by_model: Array<{ model: string; requests: number; success: number; failed: number; tokens: number }>;
  by_account?: ProxyUsageAccount[];
  active: ProxyUsageRecord[];
  recent: ProxyUsageRecord[];
}

export interface ProxyUsageAccount {
  account_id: string;
  account_email: string;
  requests: number;
  success: number;
  failed: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  image_input_tokens: number;
  image_output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  last_used_at: string;
}

export interface ProxyUsageAccountSummary {
  limit: number;
  items: ProxyUsageAccount[];
}

export interface ProxyUsageCost {
  pricing_model: string;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  image_input_tokens: number;
  image_output_tokens: number;
  image_count: number;
  estimated: boolean;
  input_cost_usd: number;
  cached_input_cost_usd: number;
  output_cost_usd: number;
  image_input_cost_usd: number;
  image_output_cost_usd: number;
  total_cost_usd: number;
}

export interface ProxyUsagePoint {
  time: string;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  image_input_tokens: number;
  image_output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  estimated: boolean;
}

export interface ProxyUsageSeries {
  window_minutes: number;
  bucket_seconds: number;
  points: ProxyUsagePoint[];
  total_cost_usd: number;
}

export interface ProxyLiveLog {
  time: string;
  request_id?: string;
  level: "info" | "warn" | "error";
  message: string;
  record?: ProxyUsageRecord;
}

export interface ProxyUsageEvent {
  type: "snapshot" | "started" | "updated" | "completed" | "log";
  active?: ProxyUsageRecord[];
  logs?: ProxyLiveLog[];
  record?: ProxyUsageRecord;
  log?: ProxyLiveLog;
}

// ── 代理池 ──────────────────────────────────────────────────────

export interface ProxyNode {
  id: string;
  name: string;
  protocol: "http" | "https" | "socks5" | "ss" | "vmess" | "trojan" | "vless" | "hysteria2" | "ssr" | string;
  server: string;
  port: number;
  username: string;
  password: string;
  extra: Record<string, unknown>;
  proxy_url: string;
  subscription_id: string;
  pool: "api" | "register";
  latency_ms: number;
  score: number;
  grade: "pure" | "clean" | "moderate" | "risky" | "dirty" | "";
  country: string;
  city: string;
  isp: string;
  ip_type: "residential" | "datacenter" | "mobile" | "";
  last_tested_at: string;
  last_error: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProxyNodeListResponse {
  items: ProxyNode[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ProxySubscription {
  id: string;
  url: string;
  name: string;
  type: "clash_yaml" | "base64" | "auto";
  node_count: number;
  last_synced_at: string;
}

export interface ProxyPoolStats {
  total_nodes: number;
  enabled_nodes: number;
  tested_nodes: number;
  avg_score: number;
  by_protocol: Record<string, number>;
  by_country: Record<string, number>;
  by_pool: Record<string, number>;
  assigned_accounts: number;
}

export interface ProxyAssignment {
  account_id: string;
  email: string;
  proxy_node_id: string;
  node_name: string;
  node_latency_ms: number;
  total_tokens: number;
  requests: number;
  failed: number;
}
