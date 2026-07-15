<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore, type Message } from '@/stores/chat'
import { useProfileStore } from '@/stores/profile'
import MessageBubble from '@/components/MessageBubble.vue'
import UiIcon from '@/components/UiIcon.vue'
import { emojiGroups } from '@/data/emojis'

import iconAlbum from '@/assets/icons/plus-album.svg'
import iconCamera from '@/assets/icons/plus-camera.svg'
import iconVideocall from '@/assets/icons/plus-videocall.svg'
import iconLocation from '@/assets/icons/plus-location.svg'
import iconFile from '@/assets/icons/plus-file.svg'
import iconRedpacket from '@/assets/icons/plus-redpacket.svg'
import iconVoice from '@/assets/icons/plus-voice.svg'

const router = useRouter()
const chat = useChatStore()
const profile = useProfileStore()

const input = ref(loadDraft())
const listEl = ref<HTMLElement | null>(null)
const textareaEl = ref<HTMLTextAreaElement | null>(null)

// 三种底部面板：plus / emoji / 无
const showPlus = ref(false)
const showEmoji = ref(false)
const voiceMode = ref(false) // 按住说话模式
const fileInput = ref<HTMLInputElement | null>(null)
const cameraInput = ref<HTMLInputElement | null>(null)
const quoting = ref<Message | null>(null)

// 表情分类
const emojiTab = ref(0)
const currentEmojis = computed(() => emojiGroups[emojiTab.value]?.emojis || [])

onMounted(async () => {
  chat.enterChat() // 标记在聊天内 + 清未读
  await chat.loadHistory()
  scrollToBottom()
})
// KeepAlive 重新激活时也清未读（从消息列表再进来）
onActivated(() => {
  chat.enterChat()
})
onBeforeUnmount(() => {
  chat.leaveChat()
})

// 草稿持久化
function loadDraft(): string {
  return localStorage.getItem('ling:draft') || ''
}
watch(input, (v) => {
  localStorage.setItem('ling:draft', v)
})

function scrollToBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

// ---- 发送 ----
async function onSend() {
  const text = input.value
  if (!text.trim()) return
  // sending 中也允许发送：store.send 内部会打断当前流式轮次再开新轮
  input.value = ''
  const q = quoting.value
  quoting.value = null
  const wasVoice = lastInputWasVoice
  lastInputWasVoice = false // 发送后重置
  await chat.send(text, q, wasVoice)
  scrollToBottom()
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}

// ---- 表情 ----
function toggleEmoji() {
  showEmoji.value = !showEmoji.value
  showPlus.value = false
}
function insertEmoji(em: string) {
  const el = textareaEl.value
  if (!el) {
    input.value += em
    return
  }
  const s = el.selectionStart ?? input.value.length
  const e = el.selectionEnd ?? input.value.length
  input.value = input.value.slice(0, s) + em + input.value.slice(e)
  nextTick(() => {
    el.focus()
    const pos = s + em.length
    el.setSelectionRange(pos, pos)
  })
}

// ---- + 面板 ----
function togglePlus() {
  showPlus.value = !showPlus.value
  showEmoji.value = false
}
function pickAlbum() {
  fileInput.value?.click()
}
function pickCamera() {
  cameraInput.value?.click()
}
async function onFileChosen(e: Event) {
  const t = e.target as HTMLInputElement
  const f = t.files?.[0]
  if (!f) return
  showPlus.value = false
  await chat.sendImage(f)
  scrollToBottom()
  t.value = ''
}

// ---- 引用 ----
function onQuote(msg: Message) {
  quoting.value = msg
  showPlus.value = false
  showEmoji.value = false
  nextTick(() => textareaEl.value?.focus())
}
function cancelQuote() {
  quoting.value = null
}
// 重新编辑（撤回后）
function onReedit(text: string) {
  input.value = text
  nextTick(() => textareaEl.value?.focus())
}

function onRetry(msg: Message) {
  chat.retry(msg)
  scrollToBottom()
}

// ---- 按住说话 ----
const recording = ref(false)
const cancelRec = ref(false) // 上滑到取消区
const transcribing = ref(false) // ASR 识别中
let recStartTs = 0
let recStartY = 0
let mediaRecorder: MediaRecorder | null = null
let recChunks: Blob[] = []
// 标记本次输入是否来自语音识别（按住说话）。onSend 时传给 store 决定是否回语音
let lastInputWasVoice = false

async function recStart(e: Event) {
  // 不调 preventDefault：touchstart 用了 .passive 修饰符
  recording.value = true
  cancelRec.value = false
  recStartTs = Date.now()
  if (e instanceof TouchEvent && e.touches[0]) {
    recStartY = e.touches[0].clientY
  } else if (e instanceof MouseEvent) {
    recStartY = e.clientY
  }
  // 开始录音
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    recChunks = []
    mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (ev) => {
      if (ev.data.size > 0) recChunks.push(ev.data)
    }
    mediaRecorder.start()
  } catch {
    // 麦克风不可用，仍走原流程（dur<1 提示）
    mediaRecorder = null
  }
}
function recMove(e: TouchEvent) {
  if (e.touches[0]) {
    cancelRec.value = recStartY - e.touches[0].clientY > 80
  }
}
async function recEnd() {
  if (!recording.value) return
  const dur = Math.round((Date.now() - recStartTs) / 1000)
  recording.value = false
  const wasCancelled = cancelRec.value
  cancelRec.value = false
  if (wasCancelled) return // 上滑取消，不发

  if (dur < 1) {
    chat.messages.push({
      id: Date.now().toString(36),
      role: 'user',
      content: '说话时间太短',
      ts: Date.now(),
      isSystem: true,
    })
    scrollToBottom()
    return
  }

  // 停止录音拿 blob → ASR → 文字填输入框
  if (!mediaRecorder || mediaRecorder.state === 'inactive') return
  const blob = await stopRecorder()
  if (!blob) return
  transcribing.value = true
  try {
    const text = await chat.transcribeAudio(blob)
    if (text) {
      // 文字填入输入框，用户可编辑后发送
      input.value = text
      // 标记来自语音 → 发送时她会回语音
      lastInputWasVoice = true
    } else {
      chat.messages.push({
        id: Date.now().toString(36),
        role: 'user',
        content: '没听清，再说一遍',
        ts: Date.now(),
        isSystem: true,
      })
    }
  } catch (e) {
    chat.messages.push({
      id: Date.now().toString(36),
      role: 'user',
      content: `语音识别失败：${(e as Error).message}`,
      ts: Date.now(),
      isSystem: true,
    })
  } finally {
    transcribing.value = false
    scrollToBottom()
  }
}

/** 停止 MediaRecorder，返回音频 blob */
function stopRecorder(): Promise<Blob | null> {
  return new Promise((resolve) => {
    if (!mediaRecorder) return resolve(null)
    mediaRecorder.onstop = () => {
      const blob = new Blob(recChunks, { type: 'audio/webm' })
      // 释放麦克风
      mediaRecorder?.stream.getTracks().forEach((t) => t.stop())
      resolve(blob)
    }
    mediaRecorder.stop()
  })
}

const panelItems = [
  { key: 'album', label: '相册', icon: iconAlbum, action: pickAlbum },
  { key: 'camera', label: '拍摄', icon: iconCamera, action: pickCamera },
  { key: 'videocall', label: '视频通话', icon: iconVideocall, action: () => { showPlus.value = false; router.push('/video-call') } },
  { key: 'location', label: '位置', icon: iconLocation, action: () => toast('阶段1不支持') },
  { key: 'file', label: '文件', icon: iconFile, action: () => toast('阶段1不支持') },
  { key: 'redpacket', label: '红包', icon: iconRedpacket, action: () => toast('阶段1不支持') },
  { key: 'voice', label: '语音输入', icon: iconVoice, action: () => { showPlus.value = false; voiceMode.value = true } },
  { key: 'emoji', label: '表情', icon: iconRedpacket, action: () => { showPlus.value = false; toggleEmoji() } },
] as const

const toastMsg = ref('')
let toastTimer: number | null = null
function toast(msg: string) {
  toastMsg.value = msg
  showPlus.value = false
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => (toastMsg.value = ''), 1500)
}

// ---- 时间分隔 ----
function showTimeSep(cur: Message, prev?: Message): boolean {
  if (!prev) return true
  if (cur.isSystem) return false
  return cur.ts - prev.ts > 5 * 60 * 1000
}
function fmtTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (sameDay) return hm
  return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`
}
const renderedItems = computed(() => {
  const items: Array<{ type: 'time'; ts: number } | { type: 'msg'; msg: Message }> = []
  let prev: Message | undefined
  for (const m of chat.messages) {
    if (showTimeSep(m, prev)) {
      items.push({ type: 'time', ts: m.ts })
    }
    items.push({ type: 'msg', msg: m })
    if (!m.isSystem) prev = m
  }
  return items
})

// ---- 多选操作 ----
const selectedCount = computed(() => chat.selectedIds.size)
function exitSelect() {
  chat.exitSelect()
}
function deleteSelected() {
  chat.deleteSelected()
  scrollToBottom()
}
</script>

<template>
  <div class="chat-window">
    <header class="nav">
      <button class="back" @click="router.push('/chat')">‹</button>
      <span class="nav-title">{{ profile.name }}</span>
      <span class="nav-spacer" />
    </header>

    <!-- 消息列表 -->
    <div ref="listEl" class="msg-list">
      <div v-if="chat.loading" class="center-tip">加载历史中…</div>
      <template v-for="(it, i) in renderedItems" :key="i">
        <div v-if="it.type === 'time'" class="msg-time">{{ fmtTime(it.ts) }}</div>
        <MessageBubble v-else :msg="it.msg" @quote="onQuote" @reedit="onReedit" @retry="onRetry" />
      </template>
    </div>

    <!-- 多选模式底部操作条 -->
    <footer v-if="chat.selectMode" class="select-bar">
      <span class="select-count">已选 {{ selectedCount }}</span>
      <div class="select-actions">
        <button class="select-btn" @click="toast('单会话不支持转发')">逐条转发</button>
        <button class="select-btn" @click="toast('单会话不支持转发')">合并转发</button>
        <button class="select-btn" @click="toast('已收藏（演示）')">收藏</button>
        <button class="select-btn danger" @click="deleteSelected">删除</button>
      </div>
      <button class="select-cancel" @click="exitSelect">取消</button>
    </footer>

    <template v-else>
      <!-- + 面板 -->
      <Transition name="panel">
        <div v-if="showPlus" class="plus-panel">
          <button v-for="it in panelItems" :key="it.key" class="panel-item" @click="it.action">
            <img class="panel-icon" :src="it.icon" :alt="it.label" />
            <span class="panel-label">{{ it.label }}</span>
          </button>
        </div>
      </Transition>

      <!-- 表情面板 -->
      <Transition name="panel">
        <div v-if="showEmoji" class="emoji-panel">
          <div class="emoji-grid">
            <button v-for="(em, idx) in currentEmojis" :key="idx" class="emoji-cell" @click="insertEmoji(em)">{{ em }}</button>
          </div>
          <div class="emoji-tabs">
            <button
              v-for="(g, idx) in emojiGroups"
              :key="idx"
              class="emoji-tab"
              :class="{ active: emojiTab === idx }"
              @click="emojiTab = idx"
            >{{ g.name }}</button>
          </div>
        </div>
      </Transition>

      <!-- 引用预览条 -->
      <Transition name="quote">
        <div v-if="quoting" class="quote-bar">
          <div class="quote-bar-info">
            <span class="quote-bar-sender">{{ quoting.role === 'user' ? '我' : profile.name }}</span>
            <span class="quote-bar-text">{{ quoting.content.slice(0, 30) }}</span>
          </div>
          <button class="quote-bar-close" @click="cancelQuote">×</button>
        </div>
      </Transition>

      <!-- 输入栏 -->
      <footer class="input-bar">
        <!-- 左侧：语音/键盘切换 -->
        <button class="ico" @click="voiceMode = !voiceMode; showEmoji = false; showPlus = false">
          <UiIcon :name="voiceMode ? 'keyboard' : 'mic'" :size="22" />
        </button>

        <!-- 语音模式：按住说话 -->
        <button
          v-if="voiceMode"
          class="hold-talk"
          :class="{ rec: recording, cancel: cancelRec }"
          @touchstart.passive="recStart"
          @touchmove.passive="recMove"
          @touchend="recEnd"
          @mousedown="recStart"
          @mouseup="recEnd"
          @mouseleave="recording && recEnd()"
        >{{ recording ? (cancelRec ? '松开手指，取消发送' : '松开 结束') : '按住 说话' }}</button>

        <!-- 文本模式：输入框 -->
        <textarea
          v-else
          ref="textareaEl"
          v-model="input"
          class="input"
          rows="1"
          :placeholder="quoting ? '回复…' : '说点什么…'"
          @keydown="onKeydown"
          @focus="showPlus = false; showEmoji = false"
        />

        <button class="ico" @click="toggleEmoji"><UiIcon :name="showEmoji ? 'keyboard' : 'smile'" :size="22" /></button>
        <button v-if="input.trim() && !voiceMode" class="send" @click="onSend">
          发送
        </button>
        <button v-else class="ico plus-btn" :class="{ active: showPlus }" @click="togglePlus">＋</button>
      </footer>
    </template>

    <!-- 录音浮层 -->
    <Transition name="fade">
      <div v-if="recording" class="rec-overlay">
        <div class="rec-box" :class="{ cancel: cancelRec }">
          <div class="rec-mic"><UiIcon :name="cancelRec ? 'x' : 'mic'" :size="32" /></div>
          <div class="rec-tip">{{ cancelRec ? '松开手指，取消发送' : '上滑取消，松开发送' }}</div>
        </div>
      </div>
    </Transition>

    <!-- ASR 识别中浮层 -->
    <Transition name="fade">
      <div v-if="transcribing" class="rec-overlay">
        <div class="rec-box">
          <div class="rec-mic">⏳</div>
          <div class="rec-tip">识别中…</div>
        </div>
      </div>
    </Transition>

    <input ref="fileInput" type="file" accept="image/*" hidden @change="onFileChosen" />
    <input ref="cameraInput" type="file" accept="image/*" capture="environment" hidden @change="onFileChosen" />

    <Transition name="toast">
      <div v-if="toastMsg" class="toast">{{ toastMsg }}</div>
    </Transition>
  </div>
</template>

<style scoped lang="scss">
.chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--wx-bg);
  position: relative;
}

.nav {
  height: var(--wx-navbar-height);
  display: flex;
  align-items: center;
  // 导航栏毛玻璃：消息列表滚动时透出柔和质感
  background: var(--wx-glass-bg);
  backdrop-filter: blur(var(--wx-glass-blur));
  -webkit-backdrop-filter: blur(var(--wx-glass-blur));
  border-bottom: 0.5px solid var(--wx-glass-border);
  flex-shrink: 0;
}
.back {
  font-size: 30px;
  line-height: 1;
  padding: 0 12px;
  color: var(--wx-text);
}
.nav-title {
  flex: 1;
  text-align: center;
  font-size: 17px;
  font-weight: 600;
}
.nav-spacer {
  width: 44px;
}

.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px 0;
}
.center-tip {
  text-align: center;
  font-size: 12px;
  color: var(--wx-text-tips);
  padding: 10px;
}
.msg-time {
  text-align: center;
  font-size: 12px;
  color: var(--wx-text-tips);
  margin: 12px 0 6px;
}

// 多选操作条
.select-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px calc(10px + var(--wx-safe-bottom));
  background: var(--wx-bg-white);
  border-top: 0.5px solid var(--wx-line);
  flex-shrink: 0;
}
.select-count {
  font-size: 13px;
  color: var(--wx-text-desc);
  flex-shrink: 0;
}
.select-actions {
  flex: 1;
  display: flex;
  justify-content: space-around;
}
.select-btn {
  font-size: 13px;
  color: var(--wx-text);
  padding: 6px 8px;
  &.danger {
    color: var(--wx-danger);
  }
}
.select-cancel {
  font-size: 14px;
  color: var(--wx-text-desc);
  flex-shrink: 0;
}

// + 面板
.plus-panel {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px 0;
  padding: 18px 14px;
  background: var(--wx-bg-white);
  border-top: 0.5px solid var(--wx-line);
  flex-shrink: 0;
}
.panel-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  &:active {
    opacity: 0.6;
  }
}
.panel-icon {
  width: 58px;
  height: 58px;
  border-radius: var(--wx-radius-lg);
  display: block;
}
.panel-label {
  font-size: 12px;
  color: var(--wx-text-desc);
}

// 表情面板
.emoji-panel {
  background: var(--wx-bg-white);
  border-top: 0.5px solid var(--wx-line);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  height: 220px;
}
.emoji-grid {
  flex: 1;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  padding: 8px;
}
.emoji-cell {
  font-size: 26px;
  padding: 6px 0;
  text-align: center;
  &:active {
    background: var(--wx-bg-active);
  }
}
.emoji-tabs {
  display: flex;
  border-top: 0.5px solid var(--wx-line);
  height: 36px;
}
.emoji-tab {
  flex: 1;
  font-size: 12px;
  color: var(--wx-text-desc);
  &.active {
    color: var(--wx-brand);
    border-bottom: 2px solid var(--wx-brand);
  }
}

.panel-enter-active,
.panel-leave-active {
  transition: max-height 0.2s ease, opacity 0.2s ease;
  overflow: hidden;
  max-height: 240px;
}
.panel-enter-from,
.panel-leave-to {
  max-height: 0;
  opacity: 0;
  padding-top: 0;
  padding-bottom: 0;
}

// 引用条
.quote-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  background: var(--wx-bg-white);
  border-top: 0.5px solid var(--wx-line);
  flex-shrink: 0;
}
.quote-bar-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border-left: 3px solid var(--wx-brand);
  padding-left: 8px;
}
.quote-bar-sender {
  font-size: 12px;
  color: var(--wx-text-desc);
}
.quote-bar-text {
  font-size: 13px;
  color: var(--wx-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.quote-bar-close {
  font-size: 22px;
  color: var(--wx-text-tips);
  padding: 0 4px;
}
.quote-enter-active,
.quote-leave-active {
  transition: max-height 0.2s ease, opacity 0.2s ease;
  overflow: hidden;
  max-height: 60px;
}
.quote-enter-from,
.quote-leave-to {
  max-height: 0;
  opacity: 0;
}

// 输入栏
.input-bar {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 8px 10px calc(8px + var(--wx-safe-bottom));
  background: var(--wx-bg-white);
  border-top: 0.5px solid var(--wx-line);
  flex-shrink: 0;
}
.ico {
  font-size: 24px;
  line-height: 36px;
  color: var(--wx-text-desc);
  flex-shrink: 0;
  min-width: 30px;
}
.plus-btn {
  &.active {
    color: var(--wx-brand);
    transform: rotate(45deg);
  }
  transition: transform 0.2s;
}
.input {
  flex: 1;
  min-height: 36px;
  max-height: 96px;
  padding: 8px 10px;
  background: var(--wx-bg-input);
  border-radius: var(--wx-radius-control);
  font-size: 16px;
  line-height: 1.4;
  resize: none;
}
// 按住说话
.hold-talk {
  flex: 1;
  height: 36px;
  background: var(--wx-bg-input);
  border-radius: var(--wx-radius-control);
  font-size: 15px;
  color: var(--wx-text-desc);
  user-select: none;
  &.rec {
    background: var(--wx-brand-soft);
    color: var(--wx-brand);
  }
  &.cancel {
    background: var(--wx-danger-soft);
    color: var(--wx-danger);
  }
}
.send {
  background: var(--wx-brand);
  color: var(--wx-text-white);
  font-size: 15px;
  padding: 8px 14px;
  border-radius: var(--wx-radius-control);
  flex-shrink: 0;
  height: 36px;
  &:active {
    background: var(--wx-brand-press);
  }
  &:disabled {
    opacity: 0.5;
  }
}

// 录音浮层
.rec-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.rec-box {
  background: var(--wx-glass-dark-bg);
  backdrop-filter: blur(var(--wx-glass-blur));
  -webkit-backdrop-filter: blur(var(--wx-glass-blur));
  border-radius: var(--wx-radius-lg);
  padding: 20px 30px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  &.cancel {
    background: rgba(250, 81, 81, 0.85);
  }
}
.rec-mic {
  font-size: 40px;
  color: var(--wx-text-white);
}
.rec-tip {
  font-size: 13px;
  color: var(--wx-text-white);
}

.toast {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0, 0, 0, 0.75);
  color: var(--wx-text-white);
  font-size: 14px;
  padding: 10px 18px;
  border-radius: var(--wx-radius-md);
  z-index: 100;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
}
</style>
