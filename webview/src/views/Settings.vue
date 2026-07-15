<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import { useProfileStore } from '@/stores/profile'
import * as api from '@/api/backend'
import type { HealthResponse } from '@/api/backend'
import EmotionAvatar from '@/components/EmotionAvatar.vue'

defineOptions({ name: 'Settings' })

const router = useRouter()
const chat = useChatStore()
const settings = useSettingsStore()
const profile = useProfileStore()

const health = ref<HealthResponse | null>(null)
const healthErr = ref('')
const resetting = ref(false)
const resetMsg = ref('')
const showResetConfirm = ref(false)
const showThemePicker = ref(false)

const themeOptions: { value: 'auto' | 'light' | 'dark'; label: string }[] = [
  { value: 'auto', label: '跟随系统' },
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
]
const themeLabel = () => themeOptions.find((t) => t.value === settings.theme)?.label || '跟随系统'

async function refreshHealth() {
  healthErr.value = ''
  try {
    health.value = await api.health()
  } catch (e) {
    healthErr.value = (e as Error).message
  }
}

async function onReset() {
  if (resetting.value) return
  resetting.value = true
  resetMsg.value = ''
  try {
    await chat.reset()
    resetMsg.value = '已清空对话历史'
  } catch (e) {
    resetMsg.value = '清空失败：' + (e as Error).message
  } finally {
    resetting.value = false
    setTimeout(() => (resetMsg.value = ''), 3000)
  }
}

onMounted(refreshHealth)
</script>

<template>
  <div class="page">
    <header class="nav"><span class="nav-title">设置</span></header>

    <div class="list">
      <!-- 账号区 -->
      <div class="section">
        <button class="cell account" @click="router.push('/contacts/detail')">
          <EmotionAvatar :src="profile.avatarUrl" :size="48" class="acc-avatar" />
          <div class="acc-info">
            <div class="acc-name">{{ profile.name }}</div>
            <div class="acc-wx">微信号：lijialing_ai</div>
          </div>
          <span class="cell-arrow">›</span>
        </button>
      </div>

      <!-- 后端状态 -->
      <div class="section-head">后端状态</div>
      <div class="section">
        <div class="cell">
          <span class="cell-text">服务</span>
          <span class="cell-value" :class="health ? 'ok' : 'err'">
            {{ health ? (health.status === 'ok' ? '在线' : health.status) : '离线' }}
          </span>
        </div>
        <div class="cell">
          <span class="cell-text">记忆检索 (FAISS)</span>
          <span class="cell-value">{{ health ? (health.memory ? '✓' : '✗') : '—' }}</span>
        </div>
        <div class="cell">
          <span class="cell-text">对话DB (SQLite)</span>
          <span class="cell-value">{{ health ? (health.db ? '✓' : '✗') : '—' }}</span>
        </div>
        <div class="cell">
          <span class="cell-text">user_id</span>
          <span class="cell-value">{{ health ? health.user_id : '—' }}</span>
        </div>
        <button class="cell clickable" @click="refreshHealth">
          <span class="cell-text">刷新</span>
          <span class="cell-arrow">↻</span>
        </button>
        <div v-if="healthErr" class="cell-err">{{ healthErr }}</div>
      </div>

      <!-- 通用 -->
      <div class="section-head">通用</div>
      <div class="section">
        <button class="cell clickable" @click="showThemePicker = true">
          <span class="cell-text">深色模式</span>
          <span class="cell-value">{{ themeLabel() }}</span>
          <span class="cell-arrow">›</span>
        </button>
        <div class="cell">
          <span class="cell-text">字体大小</span>
          <div class="font-scale">
            <button class="scale-btn" :class="{ active: settings.fontScale === 0.85 }" @click="settings.fontScale = 0.85">小</button>
            <button class="scale-btn" :class="{ active: settings.fontScale === 1 }" @click="settings.fontScale = 1">标准</button>
            <button class="scale-btn" :class="{ active: settings.fontScale === 1.15 }" @click="settings.fontScale = 1.15">大</button>
            <button class="scale-btn" :class="{ active: settings.fontScale === 1.3 }" @click="settings.fontScale = 1.3">超大</button>
          </div>
        </div>
        <div class="cell">
          <span class="cell-text">自动播放 TTS 语音</span>
          <label class="switch">
            <input type="checkbox" v-model="settings.autoTts" />
            <span class="slider" />
          </label>
        </div>
      </div>

      <!-- 引擎信息（只读） -->
      <div class="section-head">引擎（阶段1固定）</div>
      <div class="section">
        <div class="cell static">
          <span class="cell-text">TTS 引擎</span>
          <span class="cell-value">GPT-SoVITS :8880</span>
        </div>
        <div class="cell static">
          <span class="cell-text">LLM 模型</span>
          <span class="cell-value">MiniMax-M3</span>
        </div>
        <div class="cell static">
          <span class="cell-text">后端地址</span>
          <span class="cell-value">dev proxy → :8765</span>
        </div>
      </div>

      <!-- 聊天 -->
      <div class="section-head">聊天</div>
      <div class="section">
        <button class="cell clickable" @click="showResetConfirm = true" :disabled="resetting">
          <span class="cell-text danger">清空聊天记录</span>
          <span class="cell-arrow">{{ resetting ? '…' : '›' }}</span>
        </button>
        <div v-if="resetMsg" class="cell-msg">{{ resetMsg }}</div>
        <div class="cell static">
          <span class="cell-text">聊天背景</span>
          <span class="cell-value">默认</span>
          <span class="cell-arrow">›</span>
        </div>
      </div>

      <!-- 关于 -->
      <div class="section-head">关于</div>
      <div class="section">
        <div class="cell static">
          <span class="cell-text">关于刘嘉玲客户端</span>
          <span class="cell-arrow">›</span>
        </div>
      </div>

      <div class="foot">刘嘉玲 微信调试客户端 · 阶段1</div>
    </div>

    <!-- 主题选择弹窗 -->
    <Transition name="sheet">
      <div v-if="showThemePicker" class="sheet-mask" @click="showThemePicker = false">
        <div class="sheet" @click.stop>
          <button
            v-for="t in themeOptions"
            :key="t.value"
            class="sheet-item"
            :class="{ active: settings.theme === t.value }"
            @click="settings.theme = t.value; showThemePicker = false"
          >
            {{ t.label }}
            <span v-if="settings.theme === t.value" class="check-mark">✓</span>
          </button>
          <button class="sheet-cancel" @click="showThemePicker = false">取消</button>
        </div>
      </div>
    </Transition>

    <!-- 清空确认弹窗 -->
    <Transition name="dialog">
      <div v-if="showResetConfirm" class="dialog-mask" @click="showResetConfirm = false">
        <div class="dialog" @click.stop>
          <div class="dialog-title">清空聊天记录</div>
          <div class="dialog-body">确定要清空与{{ profile.name }}的聊天记录吗？清空后不可恢复。</div>
          <div class="dialog-actions">
            <button class="dialog-btn" @click="showResetConfirm = false">取消</button>
            <button class="dialog-btn danger" :disabled="resetting" @click="showResetConfirm = false; onReset()">
              {{ resetting ? '清空中…' : '清空' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped lang="scss">
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--wx-bg);
}
.nav {
  height: var(--wx-navbar-height);
  display: flex;
  align-items: center;
  justify-content: center;
  // 导航栏毛玻璃
  background: var(--wx-glass-bg);
  backdrop-filter: blur(var(--wx-glass-blur));
  -webkit-backdrop-filter: blur(var(--wx-glass-blur));
  border-bottom: 0.5px solid var(--wx-glass-border);
  flex-shrink: 0;
}
.nav-title {
  font-size: 17px;
  font-weight: 600;
}
.list {
  flex: 1;
  overflow-y: auto;
}
.section-head {
  padding: 12px 14px 6px;
  font-size: 13px;
  color: var(--wx-text-tips);
}
.section {
  background: var(--wx-bg-white);
  border-top: 0.5px solid var(--wx-line);
  border-bottom: 0.5px solid var(--wx-line);
  // 现代质感：分组卡片微阴影 + 圆角
  box-shadow: var(--wx-shadow-sm);
  border-radius: var(--wx-radius-md);
  margin: 0 8px 8px;
  overflow: hidden;
}
.cell {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 0.5px solid var(--wx-line);
  background: var(--wx-bg-white);
  text-align: left;
  &:last-child {
    border-bottom: none;
  }
  &.clickable:active {
    background: var(--wx-bg-active);
  }
  &.static .cell-value {
    font-size: 13px;
  }
}
.cell-text {
  font-size: 16px;
  color: var(--wx-text);
  &.danger {
    color: var(--wx-danger);
  }
}
.cell-value {
  font-size: 15px;
  color: var(--wx-text-desc);
  &.ok {
    color: var(--wx-brand);
  }
  &.err {
    color: var(--wx-danger);
  }
}
.cell-arrow {
  color: var(--wx-text-tips);
  font-size: 18px;
  margin-left: 8px;
}
.cell-err,
.cell-msg {
  padding: 4px 14px 10px;
  font-size: 12px;
  color: var(--wx-danger);
}
.foot {
  text-align: center;
  font-size: 12px;
  color: var(--wx-text-tips);
  padding: 24px 0;
}

// 账号卡
.account {
  padding: 14px !important;
  gap: 12px;
}
.acc-avatar {
  width: 56px;
  height: 56px;
  border-radius: var(--wx-radius-md);
  background: var(--wx-emo-flirt);
  flex-shrink: 0;
}
.acc-info {
  flex: 1;
}
.acc-name {
  font-size: 18px;
  font-weight: 500;
  color: var(--wx-text);
}
.acc-wx {
  font-size: 13px;
  color: var(--wx-text-tips);
  margin-top: 4px;
}

// 字体大小选择
.font-scale {
  display: flex;
  gap: 6px;
}
.scale-btn {
  padding: 5px 10px;
  font-size: 13px;
  border-radius: var(--wx-radius-sm);
  background: var(--wx-bg-input);
  color: var(--wx-text-desc);
  &.active {
    background: var(--wx-brand);
    color: var(--wx-text-white);
  }
}

// 主题选择 ActionSheet
.sheet-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 100;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}
.sheet {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--wx-glass-bg);
  backdrop-filter: blur(var(--wx-glass-blur));
  -webkit-backdrop-filter: blur(var(--wx-glass-blur));
  padding-bottom: var(--wx-safe-bottom);
  box-shadow: var(--wx-shadow-lg);
}
.sheet-item {
  background: rgba(255, 255, 255, 0.85);
  padding: 14px;
  font-size: 16px;
  color: var(--wx-text);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  &.active {
    color: var(--wx-brand);
  }
}
.check-mark {
  color: var(--wx-brand);
}
.sheet-cancel {
  background: rgba(255, 255, 255, 0.85);
  padding: 14px;
  font-size: 16px;
  color: var(--wx-text);
  margin-top: 8px;
  font-weight: 500;
}
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.2s;
}
.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}

// 确认弹窗
.dialog-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 40px;
}
.dialog {
  width: 100%;
  max-width: 280px;
  background: var(--wx-glass-bg);
  backdrop-filter: blur(var(--wx-glass-blur));
  -webkit-backdrop-filter: blur(var(--wx-glass-blur));
  border: 1px solid var(--wx-glass-border);
  border-radius: var(--wx-radius-lg);
  overflow: hidden;
  box-shadow: var(--wx-shadow-lg);
}
.dialog-title {
  padding: 20px 20px 8px;
  text-align: center;
  font-size: 17px;
  font-weight: 500;
}
.dialog-body {
  padding: 0 20px 20px;
  text-align: center;
  font-size: 14px;
  color: var(--wx-text-desc);
  line-height: 1.5;
}
.dialog-actions {
  display: flex;
  border-top: 0.5px solid var(--wx-line);
}
.dialog-btn {
  flex: 1;
  padding: 13px 0;
  font-size: 16px;
  color: var(--wx-text);
  & + .dialog-btn {
    border-left: 0.5px solid var(--wx-line);
  }
  &.danger {
    color: var(--wx-danger);
  }
  &:active {
    background: var(--wx-bg-active);
  }
  &:disabled {
    opacity: 0.5;
  }
}
.dialog-enter-active,
.dialog-leave-active {
  transition: opacity 0.18s;
}
.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}

// 开关
.switch {
  position: relative;
  display: inline-block;
  width: 46px;
  height: 28px;
  flex-shrink: 0;
  input {
    opacity: 0;
    width: 0;
    height: 0;
  }
  .slider {
    position: absolute;
    inset: 0;
    background: #e5e5e5;
    border-radius: 28px;
    transition: background var(--wx-duration-normal) var(--wx-ease);
    &::before {
      content: '';
      position: absolute;
      width: 24px;
      height: 24px;
      left: 2px;
      top: 2px;
      background: var(--wx-text-white);
      border-radius: 50%;
      transition: transform var(--wx-duration-normal) var(--wx-ease);
      box-shadow: var(--wx-shadow-sm);
    }
  }
  input:checked + .slider {
    background: var(--wx-brand);
    &::before {
      transform: translateX(18px);
    }
  }
}
</style>
