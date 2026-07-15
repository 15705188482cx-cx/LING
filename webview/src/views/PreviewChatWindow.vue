<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import EmotionAvatar from '@/components/EmotionAvatar.vue'
import UiIcon from '@/components/UiIcon.vue'
import { usePresentationStore } from '@/stores/presentation'
import { useProfileStore } from '@/stores/profile'

type PreviewMessage = {
  id: string
  content: string
  mine: boolean
}

const router = useRouter()
const presentation = usePresentationStore()
const profile = useProfileStore()
const input = ref('')
const showPlus = ref(false)
const showEmoji = ref(false)
const voiceMode = ref(false)
const messages = ref<PreviewMessage[]>([
  { id: 'p1', content: '今天怎么样？', mine: false },
  { id: 'p2', content: '还行，刚忙完。', mine: true },
  { id: 'p3', content: '那就好，记得吃饭。', mine: false },
  { id: 'p4', content: '好，晚点聊。', mine: true },
])

const canSend = computed(() => Boolean(input.value.trim()))

function send(): void {
  const content = input.value.trim()
  if (!content) return
  messages.value.push({ id: `preview-${Date.now()}`, content, mine: true })
  input.value = ''
}

function togglePlus(): void {
  showPlus.value = !showPlus.value
  showEmoji.value = false
}

function toggleEmoji(): void {
  showEmoji.value = !showEmoji.value
  showPlus.value = false
}
</script>

<template>
  <div class="preview-chat">
    <header class="nav">
      <button class="back" aria-label="返回" @click="router.push('/chat')"><UiIcon name="back" :size="24" /></button>
      <span class="nav-title">{{ presentation.lingName }}</span>
      <button class="more" aria-label="更多"><UiIcon name="more" :size="22" /></button>
    </header>

    <main class="messages">
      <div class="time">今天 17:56</div>
      <article v-for="message in messages" :key="message.id" class="message" :class="{ mine: message.mine }">
        <EmotionAvatar
          v-if="!message.mine"
          :src="presentation.lingAvatar || profile.avatarUrl"
          :size="40"
          class="avatar"
        />
        <span v-else class="self-avatar" :class="{ photo: presentation.selfAvatar }">
          <img v-if="presentation.selfAvatar" :src="presentation.selfAvatar" alt="我的头像" />
          <span v-else>{{ presentation.selfAvatarLabel }}</span>
        </span>
        <p class="bubble">{{ message.content }}</p>
      </article>
    </main>

    <div class="input-area">
      <button class="voice-switch" :class="{ active: voiceMode }" aria-label="切换语音输入" @click="voiceMode = !voiceMode">
        <UiIcon :name="voiceMode ? 'keyboard' : 'mic'" :size="22" />
      </button>
      <button v-if="voiceMode" class="hold-to-talk">按住 说话</button>
      <textarea
        v-else
        v-model="input"
        rows="1"
        placeholder=""
        @keydown.enter.exact.prevent="send"
      />
      <button class="emoji" aria-label="表情" @click="toggleEmoji"><UiIcon name="smile" :size="24" /></button>
      <button v-if="canSend && !voiceMode" class="send" @click="send">发送</button>
      <button v-else class="plus" aria-label="更多功能" @click="togglePlus"><UiIcon name="plus" :size="24" /></button>
    </div>

    <section v-if="showPlus" class="tool-panel">
      <button v-for="item in [{ label: '照片', icon: 'photo' }, { label: '拍摄', icon: 'camera' }, { label: '视频通话', icon: 'video' }, { label: '位置', icon: 'location' }, { label: '文件', icon: 'file' }, { label: '语音输入', icon: 'mic' }]" :key="item.label" class="tool-item">
        <span class="tool-icon"><UiIcon :name="item.icon" :size="26" :stroke="1.7" /></span>
        <span>{{ item.label }}</span>
      </button>
    </section>
    <section v-if="showEmoji" class="emoji-panel">😀 😃 😄 😊 🥰 😎 🤔 😭 ❤️ 👍</section>
  </div>
</template>

<style scoped lang="scss">
.preview-chat { height: 100%; display: flex; flex-direction: column; background: var(--wx-bg); }
.nav { height: var(--wx-navbar-height); display: flex; align-items: center; background: var(--wx-nav-bg); border-bottom: 0.5px solid var(--wx-line); }
.back, .more { width: 54px; display: grid; place-items: center; color: var(--wx-icon); }
.nav-title { flex: 1; text-align: center; font-size: 17px; font-weight: 600; }
.messages { flex: 1; overflow-y: auto; padding: 14px 14px 18px; }
.time { margin: 8px 0 18px; color: var(--wx-text-tips); text-align: center; font-size: 12px; }
.message { display: flex; align-items: flex-start; gap: 10px; margin: 12px 0; }
.message.mine { flex-direction: row-reverse; }
.avatar, .self-avatar { width: 40px; height: 40px; flex: 0 0 40px; border-radius: 5px; overflow: hidden; }
.self-avatar { display: grid; place-items: center; background: linear-gradient(135deg, #777, #333); color: #fff; font-size: 16px; }
.self-avatar img { width: 100%; height: 100%; object-fit: cover; }
.bubble { position: relative; max-width: 72%; padding: 10px 12px; background: var(--wx-surface); border-radius: 5px; color: var(--wx-text); font-size: 16px; line-height: 1.45; }
.mine .bubble { background: #95ec69; }
.input-area { min-height: 56px; display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: var(--wx-panel-bg); border-top: 0.5px solid var(--wx-line); }
.voice-switch, .emoji, .plus { flex: 0 0 32px; display: grid; place-items: center; color: var(--wx-icon); }
.voice-switch.active { color: var(--wx-brand); }
.input-area textarea, .hold-to-talk { flex: 1; min-width: 0; min-height: 36px; max-height: 88px; padding: 8px 10px; border-radius: var(--wx-radius-control); background: var(--wx-surface); resize: none; font-size: 16px; }
.hold-to-talk { text-align: center; font-weight: 600; }
.send { padding: 8px 11px; border-radius: 4px; background: var(--wx-brand); color: #fff; font-size: 14px; }
.tool-panel { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px 12px; padding: 20px 20px 30px; background: var(--wx-panel-bg); }
.tool-item { display: grid; gap: 7px; justify-items: center; color: var(--wx-text-desc); font-size: 12px; }
.tool-icon { width: 54px; height: 54px; display: grid; place-items: center; border-radius: 10px; background: var(--wx-surface); color: var(--wx-icon); }
.emoji-panel { padding: 18px; background: var(--wx-panel-bg); border-top: 0.5px solid var(--wx-line); word-spacing: 12px; font-size: 27px; line-height: 1.8; }
</style>
