<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import { useProfileStore } from '@/stores/profile'
import { useMomentsStore } from '@/stores/moments'
import { usePresentationStore } from '@/stores/presentation'
import * as api from '@/api/backend'
import type { HealthResponse } from '@/api/backend'
import EmotionAvatar from '@/components/EmotionAvatar.vue'
import UiIcon from '@/components/UiIcon.vue'

defineOptions({ name: 'Me' })

const router = useRouter()
const chat = useChatStore()
const settings = useSettingsStore()
const profile = useProfileStore()
const moments = useMomentsStore()
const presentation = usePresentationStore()

const health = ref<HealthResponse | null>(null)
const healthErr = ref('')
const resetting = ref(false)
const resetMsg = ref('')
const showResetConfirm = ref(false)

// 发圈频率选项（秒）
const intervalOptions = [
  { value: 60, label: '1 分钟（测试）' },
  { value: 300, label: '5 分钟' },
  { value: 1800, label: '30 分钟' },
  { value: 7200, label: '2 小时' },
  { value: 10800, label: '3 小时（正式）' },
]
const intervalLabel = () => intervalOptions.find((o) => o.value === moments.postInterval)?.label || `${moments.postInterval} 秒`
const showIntervalPicker = ref(false)

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

onMounted(async () => {
  if (!presentation.staticPreview) {
    await Promise.all([refreshHealth(), moments.loadConfig()])
  }
})
</script>

<template>
  <div class="page">
    <div class="list">
      <!-- 个人资料卡（微信"我"页顶部） -->
      <button
        class="profile-card"
        @click="router.push(presentation.staticPreview ? '/me/appearance' : '/contacts/detail')"
      >
        <EmotionAvatar :src="profile.avatarUrl" :size="64" class="big-avatar" />
        <div class="profile-info">
          <div class="profile-name">{{ profile.name }}</div>
          <div class="profile-wx">微信号：lijialing_ai</div>
          <div class="profile-id">+ 关注</div>
        </div>
        <div class="qr-arrow">
          <span class="qr">▦</span>
          <span class="arrow">›</span>
        </div>
      </button>

      <div class="section">
        <button class="cell clickable" @click="router.push('/me/appearance')">
          <span class="cell-ico" style="background:#576b95">◐</span>
          <span class="cell-text">展示设置</span>
          <span class="cell-value">头像与朋友圈封面</span>
          <span class="cell-arrow">›</span>
        </button>
      </div>

      <!-- 服务入口 -->
      <div class="section">
        <button class="cell">
          <span class="cell-ico service"><UiIcon name="service" :size="18" /></span>
          <span class="cell-text">服务</span>
          <span class="cell-arrow">›</span>
        </button>
        <button class="cell">
          <span class="cell-ico star"><UiIcon name="star" :size="18" /></span>
          <span class="cell-text">收藏</span>
          <span class="cell-arrow">›</span>
        </button>
        <button class="cell" @click="router.push('/discover/moments')">
          <span class="cell-ico album"><UiIcon name="album" :size="18" /></span>
          <span class="cell-text">相册</span>
          <span class="cell-arrow">›</span>
        </button>
        <button class="cell">
          <span class="cell-ico" style="background:var(--wx-morandi-purple); color:var(--wx-morandi-purple-fg)"><UiIcon name="layers" :size="18" /></span>
          <span class="cell-text">卡包</span>
          <span class="cell-arrow">›</span>
        </button>
        <button class="cell">
          <span class="cell-ico" style="background:var(--wx-morandi-rose); color:var(--wx-morandi-rose-fg)"><UiIcon name="sticker" :size="18" /></span>
          <span class="cell-text">表情</span>
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

      <!-- 朋友圈设置 -->
      <div class="section-head">朋友圈</div>
      <div class="section">
        <button class="cell clickable" @click="showIntervalPicker = true">
          <span class="cell-text">她发圈频率</span>
          <span class="cell-value">{{ intervalLabel() }}</span>
          <span class="cell-arrow">›</span>
        </button>
      </div>

      <!-- 通用 -->
      <div class="section-head">通用</div>
      <div class="section">
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

      <!-- 引擎信息 -->
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
      </div>

      <div class="foot">刘嘉玲 微信调试客户端 · feat/moments</div>
    </div>

    <!-- 发圈频率选择 -->
    <Transition name="sheet">
      <div v-if="showIntervalPicker" class="sheet-mask" @click="showIntervalPicker = false">
        <div class="sheet" @click.stop>
          <button
            v-for="o in intervalOptions"
            :key="o.value"
            class="sheet-item"
            :class="{ active: moments.postInterval === o.value }"
            @click="moments.saveConfig(o.value); showIntervalPicker = false"
          >
            {{ o.label }}
            <span v-if="moments.postInterval === o.value" class="check-mark">✓</span>
          </button>
          <button class="sheet-cancel" @click="showIntervalPicker = false">取消</button>
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
.list {
  flex: 1;
  overflow-y: auto;
}

// 个人资料卡
.profile-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 16px;
  background: var(--wx-bg-white);
  border-bottom: 0.5px solid var(--wx-line);
  margin-bottom: 8px;
  text-align: left;
  width: 100%;
  &:active {
    background: var(--wx-bg-active);
  }
}
.big-avatar {
  width: 64px;
  height: 64px;
  border-radius: var(--wx-radius-md);
  flex-shrink: 0;
}
.profile-info {
  flex: 1;
}
.profile-name {
  font-size: 22px;
  font-weight: 600;
  color: var(--wx-text);
}
.profile-wx {
  font-size: 14px;
  color: var(--wx-text-tips);
  margin-top: 6px;
}
.profile-id {
  font-size: 13px;
  color: var(--wx-link);
  margin-top: 6px;
}
.qr-arrow {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--wx-text-tips);
}
.qr {
  font-size: 22px;
}
.arrow {
  font-size: 20px;
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
  margin-bottom: 8px;
  // 现代质感：分组卡片微阴影 + 圆角
  box-shadow: var(--wx-shadow-sm);
  border-radius: var(--wx-radius-md);
  margin-left: 8px;
  margin-right: 8px;
  overflow: hidden;
}
.cell {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
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
.cell-ico {
  width: 24px;
  height: 24px;
  border-radius: var(--wx-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.cell-ico.service { background: var(--wx-morandi-green); color: var(--wx-morandi-green-fg); }
.cell-ico.star { background: var(--wx-morandi-amber); color: var(--wx-morandi-amber-fg); }
.cell-ico.album { background: var(--wx-morandi-blue); color: var(--wx-morandi-blue-fg); }
.cell-text {
  flex: 1;
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

// 字体大小
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

// ActionSheet
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
