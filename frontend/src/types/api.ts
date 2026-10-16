export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface ApiError { error: { code: string; message: string; detail?: string } }
export interface AuthMe { authenticated: boolean; csrf_token: string }
export interface TelegramStatus { connected: boolean; authorized: boolean; configured: boolean; last_error: string | null; needs_password: boolean; account: string | null; account_name: string | null }
export interface TelegramAccount { key: string; phone: string | null; name: string | null; username: string | null; active: boolean; legacy: boolean }
export interface AvailableChannel { telegram_chat_id: string; title: string; username: string | null; access_type: 'public' | 'private'; channel_type: string; permalink: string | null }
export interface Channel {
  telegram_chat_id: string; title: string; username: string | null; access_type: string; permalink: string | null
  is_managed: boolean; history_sync_enabled: boolean; live_listener_enabled: boolean; message_count: number
  last_history_sync_at: string | null; last_message_id: string | null; last_error: string | null
  created_at: string; updated_at: string
}
export interface Message {
  telegram_message_id: string; telegram_chat_id: string; message_date: string; edit_date: string | null
  text: string; permalink: string | null; views: number | null; forwards: number | null
  reply_to_message_id: string | null; media_type: string | null; media_status: string; media_path: string | null
}
export interface Task {
  id: string; telegram_chat_id: string | null; task_type: string; status: string; cursor_message_id: string | null
  processed_count: number; total_count: number | null; error_message: string | null; retry_count: number
  started_at: string | null; finished_at: string | null; created_at: string; updated_at: string; result_available: boolean
}
export interface Dashboard {
  telegram: TelegramStatus; channel_count: number; listening_count: number; message_count: number
  running_task_count: number; last_successful_sync_at: string | null; recent_errors: Task[]
  recent_activity: { event_id: string; type: string; channel_id: string; message_id: string; timestamp: string }[]
}
export interface AppSettings {
  history_sync_enabled: boolean; realtime_enabled: boolean; startup_reconcile: boolean; reconcile_interval_minutes: number
  history_batch_size: number; media_download_enabled: boolean; media_save_directory: string; export_directory: string
  default_export_format: 'json' | 'jsonl' | 'zip'; auto_export_enabled: boolean; log_level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
  task_concurrency_limit: number
}
export interface SettingsResponse { values: AppSettings; immediate_fields: string[]; next_task_fields: string[]; restart_fields: string[]; log_file: string }
export interface LiveEvent {
  event_id: string; type: string; channel_id: string | null; message_id: string | null
  timestamp: string | null; data: Record<string, unknown>
}

