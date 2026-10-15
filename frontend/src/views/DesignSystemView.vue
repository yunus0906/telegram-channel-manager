<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

/* 设计规范展示页：可视化呈现设计令牌与组件库，作为可交互的活文档。 */

const brandScale = ['--brand-50', '--brand-100', '--brand-200', '--brand-300', '--brand-400', '--brand-500', '--brand-600', '--brand-700', '--brand-800', '--brand-900']
const neutralScale = ['--ink-0', '--ink-50', '--ink-100', '--ink-200', '--ink-300', '--ink-400', '--ink-500', '--ink-600', '--ink-700', '--ink-800', '--ink-900', '--ink-950']
const semantic = [
  { label: '主色 Primary', token: '--color-primary' },
  { label: '成功 Success', token: '--color-success' },
  { label: '警示 Warning', token: '--color-warning' },
  { label: '危险 Danger', token: '--color-danger' },
  { label: '信息 Info', token: '--color-info' },
  { label: '链接 Link', token: '--color-link' },
]
const roles = [
  { label: '页面背景 bg', token: '--color-bg' },
  { label: '表面 surface', token: '--color-surface' },
  { label: '次级表面 surface-2', token: '--color-surface-2' },
  { label: '边框 border', token: '--color-border' },
  { label: '强调边框 border-strong', token: '--color-border-strong' },
  { label: '正文 text', token: '--color-text' },
  { label: '标题 text-strong', token: '--color-text-strong' },
  { label: '次要 text-muted', token: '--color-text-muted' },
]
const typeScale = [
  { label: '3xl / 标题大', token: '--text-3xl', weight: 'var(--weight-bold)' },
  { label: '2xl / 页面标题', token: '--text-2xl', weight: 'var(--weight-bold)' },
  { label: 'xl / 区块标题', token: '--text-xl', weight: 'var(--weight-semibold)' },
  { label: 'lg / 次级标题', token: '--text-lg', weight: 'var(--weight-semibold)' },
  { label: 'base / 正文', token: '--text-base', weight: 'var(--weight-regular)' },
  { label: 'sm / 辅助', token: '--text-sm', weight: 'var(--weight-regular)' },
  { label: 'xs / 标注', token: '--text-xs', weight: 'var(--weight-regular)' },
]
const spacing = ['--space-1', '--space-2', '--space-3', '--space-4', '--space-5', '--space-6', '--space-8', '--space-10', '--space-12']
const radius = [
  { token: '--radius-xs', label: 'xs' }, { token: '--radius-sm', label: 'sm' },
  { token: '--radius-md', label: 'md' }, { token: '--radius-lg', label: 'lg' },
  { token: '--radius-xl', label: 'xl' }, { token: '--radius-full', label: 'full' },
]
const shadows = [
  { token: '--shadow-xs', label: 'xs' }, { token: '--shadow-sm', label: 'sm' },
  { token: '--shadow-md', label: 'md' }, { token: '--shadow-lg', label: 'lg' },
]

const values = reactive<Record<string, string>>({})
const demoText = ref('')
const demoSwitch = ref(true)

function resolve(tokens: string[]): void {
  const root = getComputedStyle(document.documentElement)
  for (const t of tokens) values[t] = root.getPropertyValue(t).trim()
}

const principles = [
  { title: '以令牌驱动', desc: '所有颜色、间距、字号都来自 src/styles/tokens.css，组件只消费语义角色令牌，杜绝散落的魔法值。' },
  { title: '层级清晰', desc: '通过间距、字重、阴影建立信息优先级：标题 > 正文 > 辅助，面板 > 表面 > 背景。' },
  { title: '克制一致', desc: '统一圆角、阴影与过渡曲线，组件外观可预测；状态变化用同一组动效表达。' },
  { title: '明 / 暗同源', desc: '暗色主题仅翻转语义角色令牌，结构与组件无需重写，两种主题天然一致。' },
]

onMounted(() => {
  resolve([...brandScale, ...neutralScale, ...semantic.map(s => s.token), ...roles.map(r => r.token), ...typeScale.map(t => t.token), ...spacing, ...radius.map(r => r.token), ...shadows.map(s => s.token)])
})
</script>

<template>
  <div class="page">
    <div class="page-heading">
      <div>
        <h1>设计规范</h1>
        <p>产品视觉系统的令牌与组件活文档，随主题实时更新</p>
      </div>
    </div>

    <!-- 设计原则 -->
    <section class="panel">
      <h2 class="section-title">
设计原则
</h2>
      <div class="principle-grid">
        <div v-for="p in principles" :key="p.title" class="principle">
          <div class="principle-title">
{{ p.title }}
</div>
          <div class="principle-desc">
{{ p.desc }}
</div>
        </div>
      </div>
    </section>

    <!-- 色彩：品牌色阶 -->
    <section class="panel">
      <h2 class="section-title">
品牌色阶 Brand
</h2>
      <div class="swatch-grid">
        <div v-for="t in brandScale" :key="t" class="swatch">
          <div class="swatch-color" :style="{ background: `var(${t})` }" />
          <div class="swatch-name mono">
{{ t }}
</div>
          <div class="swatch-value mono">
{{ values[t] }}
</div>
        </div>
      </div>
    </section>

    <!-- 色彩：中性墨色 -->
    <section class="panel">
      <h2 class="section-title">
中性墨色 Neutral
</h2>
      <div class="swatch-grid">
        <div v-for="t in neutralScale" :key="t" class="swatch">
          <div class="swatch-color" :style="{ background: `var(${t})` }" />
          <div class="swatch-name mono">
{{ t }}
</div>
          <div class="swatch-value mono">
{{ values[t] }}
</div>
        </div>
      </div>
    </section>

    <!-- 色彩：语义与角色 -->
    <section class="panel">
      <h2 class="section-title">
语义色 & 角色令牌
</h2>
      <div class="role-grid">
        <div v-for="s in [...semantic, ...roles]" :key="s.token" class="role">
          <div class="role-color" :style="{ background: `var(${s.token})` }" />
          <div class="role-meta">
            <div class="role-label">
{{ s.label }}
</div>
            <div class="role-token mono">
{{ s.token }}
</div>
            <div class="role-value mono">
{{ values[s.token] }}
</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 字体排版 -->
    <section class="panel">
      <h2 class="section-title">
字体排版 Typography
</h2>
      <div class="type-list">
        <div v-for="t in typeScale" :key="t.token" class="type-row">
          <div class="type-label mono">
{{ t.label }}<br />{{ t.token }}
</div>
          <div class="type-sample" :style="{ fontSize: `var(${t.token})`, fontWeight: t.weight }">
信道管理 · Channel Manager
</div>
          <div class="type-value mono">
{{ values[t.token] }}
</div>
        </div>
      </div>
    </section>

    <!-- 间距 -->
    <section class="panel">
      <h2 class="section-title">
间距 Spacing（4px 基准）
</h2>
      <div class="space-list">
        <div v-for="t in spacing" :key="t" class="space-row">
          <div class="space-label mono">
{{ t }}
</div>
          <div class="space-bar" :style="{ width: `var(${t})` }" />
          <div class="space-value mono">
{{ values[t] }}
</div>
        </div>
      </div>
    </section>

    <!-- 圆角 -->
    <section class="panel">
      <h2 class="section-title">
圆角 Radius
</h2>
      <div class="radius-grid">
        <div v-for="r in radius" :key="r.token" class="radius-item">
          <div class="radius-box" :style="{ borderRadius: `var(${r.token})` }" />
          <div class="mono">
{{ r.label }}<br />{{ r.token }}
</div>
        </div>
      </div>
    </section>

    <!-- 阴影 -->
    <section class="panel">
      <h2 class="section-title">
阴影 Elevation
</h2>
      <div class="shadow-grid">
        <div v-for="s in shadows" :key="s.token" class="shadow-item">
          <div class="shadow-box" :style="{ boxShadow: `var(${s.token})` }">
{{ s.label }}
</div>
          <div class="mono">
{{ s.token }}
</div>
        </div>
      </div>
    </section>

    <!-- 组件库 -->
    <section class="panel">
      <h2 class="section-title">
组件库 Components
</h2>

      <h3 class="group-title">
按钮 Button
</h3>
      <div class="demo-row">
        <el-button type="primary">
主要
</el-button>
        <el-button>默认</el-button>
        <el-button type="success">
成功
</el-button>
        <el-button type="warning">
警告
</el-button>
        <el-button type="danger">
危险
</el-button>
        <el-button type="info">
信息
</el-button>
        <el-button link type="primary">
链接
</el-button>
        <el-button :loading="true">
加载
</el-button>
        <el-button disabled>
禁用
</el-button>
      </div>

      <h3 class="group-title">
标签 Tag
</h3>
      <div class="demo-row">
        <el-tag type="primary">
primary
</el-tag>
        <el-tag type="success">
success
</el-tag>
        <el-tag type="warning">
warning
</el-tag>
        <el-tag type="danger">
danger
</el-tag>
        <el-tag type="info">
info
</el-tag>
      </div>

      <h3 class="group-title">
输入 Input & 控件
</h3>
      <div class="demo-row">
        <el-input v-model="demoText" placeholder="搜索频道名称" style="max-width: 240px" />
        <el-select placeholder="访问类型" clearable style="width: 150px">
          <el-option label="公开" value="public" /><el-option label="私有" value="private" />
        </el-select>
        <el-switch v-model="demoSwitch" />
        <el-button :icon="Search">
操作
</el-button>
      </div>

      <h3 class="group-title">
警示 Alert
</h3>
      <div class="demo-col">
        <el-alert title="成功状态示例" type="success" show-icon :closable="false" />
        <el-alert title="警告状态示例" type="warning" show-icon :closable="false" />
        <el-alert title="错误状态示例" type="error" show-icon :closable="false" />
        <el-alert title="提示信息示例" type="info" show-icon :closable="false" />
      </div>

      <h3 class="group-title">
进度 Progress
</h3>
      <div class="demo-row">
        <el-progress :percentage="68" style="max-width: 280px" />
        <el-progress type="circle" :percentage="42" :width="64" />
      </div>

      <h3 class="group-title">
表格 Table
</h3>
      <el-table :data="[{ a: 'TG_Public', b: '已授权', c: '1,284' }, { a: 'TG_Private', b: '监听中', c: '512' }]" empty-text="暂无数据" style="width: 100%">
        <el-table-column prop="a" label="频道" min-width="160" />
        <el-table-column prop="b" label="状态" width="140">
          <template #default="{ row }">
<el-tag size="small" type="success">
{{ row.b }}
</el-tag>
</template>
        </el-table-column>
        <el-table-column prop="c" label="本地消息" width="140" />
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.principle-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4); }
.principle { background: var(--color-surface-2); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-4); }
.principle-title { font-weight: var(--weight-semibold); color: var(--color-text-strong); margin-bottom: var(--space-1); }
.principle-desc { color: var(--color-text-muted); font-size: var(--text-sm); line-height: var(--leading-relaxed); }

.swatch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: var(--space-3); }
.swatch-color { height: 56px; border-radius: var(--radius-md); border: 1px solid var(--color-border); }
.swatch-name { margin-top: var(--space-2); color: var(--color-text-strong); }
.swatch-value { color: var(--color-text-subtle); }

.role-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: var(--space-3); }
.role { display: flex; align-items: center; gap: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-3); }
.role-color { width: 40px; height: 40px; border-radius: var(--radius-sm); border: 1px solid var(--color-border); flex: none; }
.role-label { color: var(--color-text-strong); font-weight: var(--weight-medium); }
.role-token, .role-value { color: var(--color-text-subtle); }

.type-list { display: flex; flex-direction: column; gap: var(--space-4); }
.type-row { display: grid; grid-template-columns: 180px 1fr 80px; align-items: baseline; gap: var(--space-4); border-bottom: 1px dashed var(--color-border); padding-bottom: var(--space-3); }
.type-label { color: var(--color-text-muted); }
.type-sample { color: var(--color-text-strong); line-height: var(--leading-tight); }
.type-value { color: var(--color-text-subtle); text-align: right; }

.space-list { display: flex; flex-direction: column; gap: var(--space-2); }
.space-row { display: grid; grid-template-columns: 100px 1fr 64px; align-items: center; gap: var(--space-4); }
.space-label { color: var(--color-text-muted); }
.space-bar { height: 16px; background: linear-gradient(90deg, var(--brand-400), var(--brand-600)); border-radius: var(--radius-full); }
.space-value { color: var(--color-text-subtle); text-align: right; }

.radius-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: var(--space-4); }
.radius-item { text-align: center; color: var(--color-text-muted); }
.radius-box { height: 64px; background: var(--color-primary-soft); border: 1px solid var(--color-primary-soft-2); margin-bottom: var(--space-2); }

.shadow-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: var(--space-6); }
.shadow-item { text-align: center; color: var(--color-text-muted); }
.shadow-box { height: 80px; display: grid; place-items: center; background: var(--color-surface); border-radius: var(--radius-md); margin-bottom: var(--space-2); color: var(--color-text-muted); }

.group-title { margin: var(--space-6) 0 var(--space-3); font-size: var(--text-md); font-weight: var(--weight-semibold); color: var(--color-text-strong); }
.group-title:first-child { margin-top: 0; }
.demo-row { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
.demo-col { display: flex; flex-direction: column; gap: var(--space-3); }

@media (max-width: 700px) {
  .principle-grid { grid-template-columns: 1fr; }
  .type-row { grid-template-columns: 120px 1fr; }
  .type-value { display: none; }
}
</style>
