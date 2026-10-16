<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errorMessage } from '../api/client'
import type { AppSettings, TelegramAccount, TelegramStatus } from '../types/api'

const telegram = ref<TelegramStatus | null>(null)
const accounts = ref<TelegramAccount[]>([])
const values = ref<AppSettings | null>(null)
const formRef = ref<FormInstance>()
const phone = ref('')
const code = ref('')
const password = ref('')
const busy = ref(false)
const accountBusy = ref('')
const saving = ref(false)
const loadError = ref('')
const immediateFields = ref<string[]>([])
const nextTaskFields = ref<string[]>([])
const restartFields = ref<string[]>([])
const logFile = ref('')
const fieldLabels: Record<keyof AppSettings, string> = {
  history_sync_enabled: '历史同步', realtime_enabled: '实时监听', startup_reconcile: '启动校准',
  reconcile_interval_minutes: '校准间隔', history_batch_size: '扫描批次', media_download_enabled: '媒体下载',
  media_save_directory: '媒体目录', export_directory: '导出目录', default_export_format: '默认格式',
  auto_export_enabled: '自动导出', log_level: '日志级别', task_concurrency_limit: '任务并发限制',
}
const labels = (fields: string[]) => fields.map((field) => fieldLabels[field as keyof AppSettings] || field).join('、')
const safeDirectory = (_rule: unknown, value: string, callback: (error?: Error) => void) => {
  const parts = value?.split(/[\\/]/) || []
  callback(parts.length && parts.every((part) => part && part !== '.' && part !== '..' && !part.includes(':')) ? undefined : new Error('请输入数据目录内的安全相对路径'))
}
const rules: FormRules<AppSettings> = {
  media_save_directory: [{ required: true, validator: safeDirectory, trigger: 'blur' }],
  export_directory: [{ required: true, validator: safeDirectory, trigger: 'blur' }],
  reconcile_interval_minutes: [{ type: 'number', min: 5, max: 10080, required: true, trigger: 'change' }],
  history_batch_size: [{ type: 'number', min: 10, max: 500, required: true, trigger: 'change' }],
  task_concurrency_limit: [{ type: 'number', min: 1, max: 4, required: true, trigger: 'change' }],
}
async function load(): Promise<void> {
  loadError.value = ''
  try {
    const [status, settings, list] = await Promise.all([api.telegramStatus(), api.settings(), api.telegramAccounts()])
    telegram.value = status; values.value = settings.values
    immediateFields.value = settings.immediate_fields; nextTaskFields.value = settings.next_task_fields; restartFields.value = settings.restart_fields
    logFile.value = settings.log_file
    accounts.value = list
  } catch (cause) { loadError.value = errorMessage(cause) }
}
async function refreshAccounts(): Promise<void> {
  try { accounts.value = await api.telegramAccounts() } catch (cause) { ElMessage.error(errorMessage(cause)) }
}
async function connect(action: 'login' | 'verify' | 'disconnect' | 'reconnect'): Promise<void> {
  busy.value = true
  try {
    if (action === 'login') telegram.value = await api.telegramLogin(phone.value)
    else if (action === 'verify') telegram.value = await api.telegramVerify(code.value || undefined, password.value || undefined)
    else if (action === 'disconnect') telegram.value = await api.telegramDisconnect()
    else telegram.value = await api.telegramReconnect()
    code.value = ''; password.value = ''
    if (action === 'verify') phone.value = ''
    await refreshAccounts()
    ElMessage.success('连接状态已更新')
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { busy.value = false }
}
/** 账号主标题：优先显示昵称，其次手机号，都没有时回落到旧版标识或内部 key。 */
function accountLabel(item: TelegramAccount): string {
  if (item.name) return item.name
  if (item.phone) return item.phone
  return item.legacy ? '旧版 session' : item.key
}
/** 账号副标题：手机号 / 用户名 / 旧版标记，用于区分同名账号。 */
function accountMeta(item: TelegramAccount): string {
  const parts: string[] = []
  if (item.phone) parts.push(item.phone)
  if (item.username) parts.push(`@${item.username}`)
  if (item.legacy) parts.push('legacy')
  return parts.length ? parts.join(' · ') : item.key
}
/** 头像占位字符：取昵称或手机号的首个有效字符。 */
function accountInitial(item: TelegramAccount): string {
  const base = item.name || item.phone || 'TG'
  return base.replace(/[^\p{L}\p{N}]/gu, '').charAt(0).toUpperCase() || 'T'
}
async function activateAccount(key: string): Promise<void> {
  accountBusy.value = key
  try {
    telegram.value = await api.telegramActivate(key)
    await refreshAccounts()
    ElMessage.success('已切换活动账号')
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { accountBusy.value = '' }
}
async function removeAccount(item: TelegramAccount): Promise<void> {
  const label = accountLabel(item)
  try {
    await ElMessageBox.confirm(`将删除 ${label} 在本机保存的 session 文件。Telegram 端的登录态不会自动退出，需要你自行到「已登录设备」里移除。`,
      '移除账号', { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' })
  } catch { return }
  accountBusy.value = item.key
  try {
    await api.telegramRemoveAccount(item.key)
    telegram.value = await api.telegramStatus()
    await refreshAccounts()
    ElMessage.success('已移除本地 session')
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { accountBusy.value = '' }
}
async function save(): Promise<void> {
  if (!values.value) return
  try { await formRef.value?.validate() }
  catch { return }
  saving.value = true
  try { const result = await api.saveSettings(values.value); values.value = result.values; ElMessage.success('设置已保存') }
  catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { saving.value = false }
}
onMounted(() => { void load() })
</script>
<template>
  <div class="page">
    <div class="page-heading">
<div><h1>系统设置</h1><p>连接当前账号并调整非敏感业务参数</p></div><el-button @click="load">
刷新状态
</el-button>
</div>
    <el-alert v-if="loadError" :title="loadError" type="error" show-icon class="panel" />
    <div class="panel">
<h2 class="section-title">
Telegram 账号连接
</h2>
      <div class="toolbar">
<el-tag :type="telegram?.authorized ? 'success' : 'warning'">
{{ telegram?.authorized ? '已授权' : telegram?.configured ? '未授权' : '未配置 API 凭证' }}
</el-tag><span v-if="telegram?.account_name || telegram?.account" class="muted">当前账号：{{ telegram?.account_name || telegram?.account }}</span><span v-if="telegram?.last_error" class="muted">最近错误：{{ telegram.last_error }}</span>
</div>
      <el-alert v-if="!telegram?.configured" title="请在后端 .env 中设置 TG_API_ID 与 TG_API_HASH，然后重启后端。" type="info" :closable="false" class="toolbar" />
      <el-alert v-if="logFile" type="info" :closable="false" class="toolbar" title="后端日志文件（登录、同步等失败会写入完整异常堆栈）" :description="logFile" />
      <section class="account-block">
        <div class="account-head">
          <h3 class="account-title">
已保存的账号
</h3>
          <el-tag size="small" type="info">
{{ accounts.length }} 个
</el-tag>
          <span class="muted">每个手机号各自一份 session，可随时切换，互不影响</span>
        </div>
        <ul v-if="accounts.length" class="account-list">
          <li v-for="item in accounts" :key="item.key" class="account-item" :class="{ 'is-active': item.active }">
            <span class="account-avatar" aria-hidden="true">{{ accountInitial(item) }}</span>
            <div class="account-main">
              <div class="account-name">
                <span>{{ accountLabel(item) }}</span>
                <el-tag v-if="item.active" size="small" type="success">
使用中
</el-tag>
                <el-tag v-else-if="item.legacy && (item.name || item.phone)" size="small" type="warning">
旧版 session
</el-tag>
              </div>
              <div class="account-meta mono">
{{ accountMeta(item) }}
</div>
            </div>
            <div class="account-actions">
              <el-button v-if="!item.active" size="small" :disabled="!!accountBusy" :loading="accountBusy === item.key" @click="activateAccount(item.key)">
切换为此账号
</el-button>
              <el-button size="small" type="danger" plain :disabled="!!accountBusy" :loading="accountBusy === item.key" @click="removeAccount(item)">
移除
</el-button>
            </div>
          </li>
        </ul>
        <p v-else class="account-empty muted">
还没有保存任何账号。在上方输入手机号完成登录后，账号会出现在这里。
</p>
      </section>
      <template v-if="telegram?.configured">
        <div v-if="!telegram.authorized" class="toolbar">
<el-input v-model="phone" placeholder="手机号，例如 +8613800000000" style="width: 260px" /><el-button :loading="busy" :disabled="!phone" @click="connect('login')">
发送验证码
</el-button>
</div>
        <div v-if="telegram.connected && !telegram.authorized" class="toolbar">
<el-input v-if="!telegram.needs_password" v-model="code" placeholder="验证码" style="width: 170px" /><el-input v-else v-model="password" type="password" show-password placeholder="两步验证密码" style="width: 220px" /><el-button type="primary" :loading="busy" :disabled="telegram.needs_password ? !password : !code" @click="connect('verify')">
提交验证
</el-button>
</div>
        <div class="toolbar">
<el-button :loading="busy" @click="connect('reconnect')">
重新连接
</el-button><el-button v-if="telegram.connected" :loading="busy" @click="connect('disconnect')">
断开网络连接
</el-button>
</div>
      </template>
    </div>
    <div v-if="values" class="panel">
<h2 class="section-title">
运行配置
</h2><el-form ref="formRef" :model="values" :rules="rules" label-position="left" label-width="175px" @submit.prevent="save">
      <el-form-item label="历史同步">
<el-switch v-model="values.history_sync_enabled" />
</el-form-item>
      <el-form-item label="实时监听">
<el-switch v-model="values.realtime_enabled" />
</el-form-item>
      <el-form-item label="启动时自动校准">
<el-switch v-model="values.startup_reconcile" />
</el-form-item>
      <el-form-item label="校准间隔（分钟）" prop="reconcile_interval_minutes">
<el-input-number v-model="values.reconcile_interval_minutes" :min="5" :max="10080" />
</el-form-item>
      <el-form-item label="历史扫描批次" prop="history_batch_size">
<el-input-number v-model="values.history_batch_size" :min="10" :max="500" />
</el-form-item>
      <el-form-item label="允许媒体下载">
<el-switch v-model="values.media_download_enabled" />
</el-form-item>
      <el-form-item label="媒体相对目录" prop="media_save_directory">
<el-input v-model="values.media_save_directory" style="max-width: 310px" />
</el-form-item>
      <el-form-item label="导出相对目录" prop="export_directory">
<el-input v-model="values.export_directory" style="max-width: 310px" />
</el-form-item>
      <el-form-item label="默认导出格式">
<el-select v-model="values.default_export_format" style="width: 170px">
<el-option label="JSON" value="json" /><el-option label="JSONL" value="jsonl" /><el-option label="ZIP" value="zip" />
</el-select>
</el-form-item>
      <el-form-item label="自动导出">
<el-switch v-model="values.auto_export_enabled" />
</el-form-item>
      <el-form-item label="日志级别">
<el-select v-model="values.log_level" style="width: 170px">
<el-option v-for="level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']" :key="level" :label="level" :value="level" />
</el-select>
</el-form-item>
      <el-form-item label="任务并发限制" prop="task_concurrency_limit">
<el-input-number v-model="values.task_concurrency_limit" :min="1" :max="4" />
</el-form-item>
      <el-form-item>
<el-button type="primary" native-type="submit" :loading="saving">
保存设置
</el-button>
</el-form-item>
    </el-form>
    <el-alert :closable="false" type="info" :title="`立即生效：${labels(immediateFields)}。下次任务或完成时生效：${labels(nextTaskFields)}。下次启动生效：${labels(restartFields)}。`" />
    </div>
  </div>
</template>
