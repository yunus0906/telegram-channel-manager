<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { errorMessage } from '../api/client'

const password = ref('')
const busy = ref(false)
const router = useRouter()
const auth = useAuthStore()
async function submit(): Promise<void> {
  if (!password.value) return
  busy.value = true
  try { await auth.login(password.value); password.value = ''; await router.push('/dashboard') }
  catch (error) { ElMessage.error(errorMessage(error)) }
  finally { busy.value = false }
}
</script>
<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <h1>管理员登录</h1>
      <p>登录后管理当前 Telegram 账号已授权的频道。</p>
      <el-form-item label="管理员密码">
<el-input v-model="password" type="password" show-password autocomplete="current-password" aria-label="管理员密码" />
</el-form-item>
      <el-button type="primary" native-type="submit" :loading="busy" :disabled="!password" style="width: 100%">
登录
</el-button>
    </form>
  </div>
</template>
