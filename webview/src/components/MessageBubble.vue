<script setup lang="ts">
import { computed, ref } from 'vue'
import EmotionAvatar from './EmotionAvatar.vue'
import UiIcon from './UiIcon.vue'
import { useChatStore, type Message } from '@/stores/chat'
import { stickerUrl } from '@/api/backend'

const props = defineProps<{ msg: Message }>()

const chat = useChatStore()

const emit = defineEmits<{
  quote: [msg: Message]
  reedit: [text: string]
  retry: [msg: Message]
}>()

// ---- 系统消息：居中灰字，无头像无气泡 ----
const isSystem = computed(() => props.msg.isSystem)

// ---- 长按菜单 ----
const menuOpen = ref(false)
let pressTimer: number | null = null
function onTouchStart() {
  pressTimer = window.setTimeout(() => {
    if (!chat.selectMode) menuOpen.value = true
  }, 500)
}
function onTouchEnd() {
  if (pressTimer) clearTimeout(pressTimer)
}
function onContextMenu(e: MouseEvent) {
  e.preventDefault()
  if (!chat.selectMode) menuOpen.value = true
}
function closeMenu() {
  menuOpen.value = false
}

// ---- 菜单项 ----
function onCopy() {
  if (props.msg.content) navigator.clipboard?.writeText(props.msg.content)
  closeMenu()
}
function onQuote() {
  emit('quote', props.msg)
  closeMenu()
}
function onDelete() {
  chat.removeMessage(props.msg.id)
  closeMenu()
}
function onRecall() {
  chat.recallMessage(props.msg.id)
  closeMenu()
}
function onSelect() {
  chat.startSelect(props.msg.id)
  closeMenu()
}

// 是否可撤回：自己的、2分钟内、非系统、非已撤回
const canRecall = computed(
  () => props.msg.role === 'user' && !props.msg.isSystem && !props.msg.recalled && Date.now() - props.msg.ts <= 2 * 60 * 1000
)

// 撤回后可重新编辑：自己的、已撤回、5 分钟内
const canReedit = computed(
  () => props.msg.role === 'user' && props.msg.recalled && Date.now() - props.msg.ts <= 5 * 60 * 1000
)

// ---- 语音点播 ----
const audioLoading = ref(false)
async function onPlayAudio() {
  if (audioLoading.value) return
  audioLoading.value = true
  try {
    await chat.playMessageAudio(props.msg)
  } finally {
    audioLoading.value = false
  }
}

// ---- 双击头像拍一拍 ----
function onDblTapAvatar() {
  chat.pat(props.msg.role === 'user' ? 'user' : 'assistant')
}

// ---- 多选 ----
const selected = computed(() => chat.selectedIds.has(props.msg.id))
function onBubbleClick() {
  if (chat.selectMode) chat.toggleSelect(props.msg.id)
}

// 撤回后重新编辑（仅自己文字撤回 5 分钟内）
function onReedit() {
  emit('reedit', props.msg.content)
}
</script>

<template>
  <!-- 系统消息：居中灰字 -->
  <div v-if="isSystem" class="sys-msg">{{ msg.content }}</div>

  <!-- 普通消息行 -->
  <div v-else class="msg-row" :class="{ 'is-mine': msg.role === 'user' }" @click="onBubbleClick">
    <!-- 多选复选框 -->
    <span v-if="chat.selectMode" class="check" :class="{ checked: selected }">✓</span>

    <EmotionAvatar
      v-if="msg.role === 'assistant'"
      :emotion="msg.emotion"
      class="msg-avatar"
      @dblclick="onDblTapAvatar"
    />
    <div v-else class="msg-avatar user-avatar" @dblclick="onDblTapAvatar">我</div>

    <div class="msg-bubble-wrap">
      <!-- 情绪标签已移除：前端不再露出情绪状态，保持聊天沉浸感 -->

      <!-- 发送失败标记 + 重试按钮 -->
      <span v-if="msg.failed" class="msg-fail" @click.stop="msg.errorRetryable !== false && emit('retry', msg)">!</span>

      <!-- 引用预览块 -->
      <div v-if="msg.quote" class="quote-preview">
        <span class="quote-sender">{{ msg.quote.sender }}</span>
        <span class="quote-text">{{ msg.quote.text }}</span>
      </div>

      <!-- 气泡 -->
      <div
        class="bubble"
        :class="[
          msg.role === 'user' ? 'bubble-mine' : 'bubble-other',
          { 'bubble-image': msg.image, 'bubble-pending': msg.pending, 'bubble-recalled': msg.recalled },
        ]"
        @touchstart.passive="onTouchStart"
        @touchend="onTouchEnd"
        @touchmove="onTouchEnd"
        @contextmenu="onContextMenu"
      >
        <!-- 撤回提示 -->
        <template v-if="msg.recalled">
          <span class="recalled-text">你撤回了一条消息</span>
          <button v-if="canReedit" class="reedit" @click.stop="onReedit">重新编辑</button>
        </template>
        <!-- 正常内容：有 content 时优先显示（流式边收边渲染） -->
        <template v-else>
          <img v-if="msg.image" :src="msg.image" class="bubble-img" alt="图片" />
          <span v-if="msg.content" class="bubble-text">{{ msg.content }}<i v-if="msg.pending" class="streaming-cursor" /></span>
          <span v-else-if="msg.pending" class="typing">…</span>
        </template>
      </div>

      <!-- AI 语音条 -->
      <button
        v-if="msg.role === 'assistant' && msg.content && !msg.pending && !msg.recalled"
        class="voice-bar"
        :class="{ loading: audioLoading, played: msg.audioPlayed }"
        @click.stop="onPlayAudio"
      >
        <span class="voice-ico"><UiIcon :name="msg.audioPlayed ? 'volume' : 'volume-off'" :size="14" /></span>
        <span class="voice-wave"><i v-for="n in 8" :key="n" /></span>
        <span class="voice-label">{{ audioLoading ? '加载…' : msg.audioPlayed ? '已播' : '播放语音' }}</span>
      </button>

      <!-- AI 回复带的表情包 -->
      <img
        v-if="msg.role === 'assistant' && msg.sticker && !msg.pending && !msg.recalled"
        :src="stickerUrl(msg.sticker)"
        class="bubble-sticker"
        alt="表情包"
      />

      <!-- 语音转文字结果块 -->
      <div v-if="msg.transcript" class="transcript">{{ msg.transcript }}</div>
    </div>

    <!-- 长按/右键菜单 -->
    <Transition name="menu">
      <div v-if="menuOpen" class="msg-menu-mask" @click="closeMenu">
        <div class="msg-menu" @click.stop>
          <button class="menu-item" @click="onCopy">复制</button>
          <button class="menu-item" @click="onQuote">引用</button>
          <button v-if="canRecall" class="menu-item" @click="onRecall">撤回</button>
          <button class="menu-item" @click="onSelect">多选</button>
          <button class="menu-item danger" @click="onDelete">删除</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/bubble.scss';

// 系统消息
.sys-msg {
  text-align: center;
  font-size: 12px;
  color: var(--wx-text-tips);
  padding: 8px 30px;
  margin: 4px 0;
}

.user-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--wx-brand);
  color: var(--wx-text-white);
  font-size: 13px;
  border-radius: var(--wx-radius-control);
  width: var(--wx-avatar-size);
  height: var(--wx-avatar-size);
  flex-shrink: 0;
}

// 多选复选框
.check {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1.5px solid #c5c5c5;
  display: flex;
  align-items: center;
  justify-content: center;
  color: transparent;
  font-size: 13px;
  flex-shrink: 0;
  margin-right: 6px;
  align-self: center;
  &.checked {
    background: var(--wx-brand);
    border-color: var(--wx-brand);
    color: var(--wx-text-white);
  }
}

.typing {
  opacity: 0.5;
}
.bubble-pending {
  opacity: 0.7;
}
// 流式输出中的闪烁光标
.streaming-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  background: currentColor;
  vertical-align: text-bottom;
  animation: blink-cursor 0.8s steps(2) infinite;
}
@keyframes blink-cursor {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}
.bubble-image {
  padding: 0;
  overflow: hidden;
  &::before {
    display: none;
  }
}
.bubble-img {
  display: block;
  max-width: 200px;
  max-height: 280px;
  object-fit: cover;
}

// 撤回
.bubble-recalled {
  background: transparent !important;
  padding: 0;
  &::before {
    display: none;
  }
}
.recalled-text {
  font-size: 13px;
  color: var(--wx-text-tips);
}
.reedit {
  color: var(--wx-link);
  font-size: 13px;
  margin-left: 4px;
}

// 发送失败
.msg-fail {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--wx-danger);
  color: var(--wx-text-white);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 4px;
  align-self: flex-end;
  cursor: pointer;
  &:active {
    opacity: 0.6;
  }
}

// 引用预览块
.quote-preview {
  display: flex;
  flex-direction: column;
  background: rgba(0, 0, 0, 0.06);
  border-left: 3px solid var(--wx-text-tips);
  border-radius: var(--wx-radius-sm);
  padding: 5px 8px;
  margin-bottom: 4px;
  max-width: 220px;
  font-size: 13px;
}
.quote-sender {
  color: var(--wx-text-desc);
  font-size: 12px;
}
.quote-text {
  color: var(--wx-text-desc);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

// 语音条
.voice-bar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  padding: 6px 12px;
  background: var(--wx-bubble-other);
  border-radius: var(--wx-radius-xl);
  font-size: 13px;
  color: var(--wx-text-desc);
  &.loading {
    opacity: 0.6;
  }
  &.played {
    color: var(--wx-brand);
  }
}
.voice-ico {
  font-size: 14px;
}
.voice-wave {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  height: 14px;
  i {
    width: 2px;
    height: 100%;
    background: currentColor;
    opacity: 0.5;
    border-radius: 1px;
  }
}
.voice-label {
  font-size: 12px;
}

// 语音转文字
.transcript {
  margin-top: 4px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: var(--wx-radius-control);
  font-size: 13px;
  color: var(--wx-text-desc);
  line-height: 1.5;
  max-width: 240px;
}

// 表情包
.bubble-sticker {
  margin-top: 4px;
  max-width: 120px;
  max-height: 120px;
  border-radius: var(--wx-radius-sm);
  object-fit: contain;
}

// 长按菜单
.msg-menu-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.2);
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
}
.msg-menu {
  background: var(--wx-glass-dark-bg);
  backdrop-filter: blur(var(--wx-glass-blur));
  -webkit-backdrop-filter: blur(var(--wx-glass-blur));
  border-radius: var(--wx-radius-md);
  padding: 6px 0;
  min-width: 130px;
  overflow: hidden;
}
.menu-item {
  display: block;
  width: 100%;
  padding: 11px 18px;
  color: var(--wx-text-white);
  font-size: 15px;
  text-align: center;
  &:active {
    background: rgba(255, 255, 255, 0.1);
  }
  &.danger {
    color: #ff6b6b;
  }
  & + .menu-item {
    border-top: 0.5px solid rgba(255, 255, 255, 0.15);
  }
}
.menu-enter-active,
.menu-leave-active {
  transition: opacity 0.15s;
}
.menu-enter-from,
.menu-leave-to {
  opacity: 0;
}
</style>
