<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import EmotionAvatar from '@/components/EmotionAvatar.vue'
import UiIcon from '@/components/UiIcon.vue'
import { useChatStore } from '@/stores/chat'
import { usePresentationStore } from '@/stores/presentation'
import { useProfileStore } from '@/stores/profile'

defineOptions({ name: 'ChatList' })

type Conversation = {
  id: string
  name: string
  preview: string
  time: string
  unread?: number
  tone: string
}

const router = useRouter()
const chat = useChatStore()
const presentation = usePresentationStore()
const profile = useProfileStore()
const searchKey = ref('')

const demoConversations: Conversation[] = [
  { id: 'file', name: '文件传输助手', preview: '[图片]', time: '昨天 15:11', tone: '#07c160' },
  { id: 'family', name: '家人', preview: '到家说一声', time: '16:39', unread: 1, tone: '#8d7a68' },
  { id: 'club', name: '周末小组', preview: '[3条] 周末有什么安排？', time: '16:31', unread: 3, tone: '#7095b7' },
  { id: 'friend', name: '阿北', preview: '[动画表情]', time: '15:44', tone: '#8077a1' },
]

const lingConversation = computed<Conversation>(() => {
  const lastMessage = [...chat.messages].reverse().find((message) => !message.pending && !message.isSystem)
  return {
    id: 'ling',
    name: presentation.staticPreview ? presentation.lingName : profile.name,
    preview: lastMessage?.content || '点击开始聊天',
    time: lastMessage ? formatTime(lastMessage.ts) : '14:29',
    unread: chat.unread || undefined,
    tone: '#dba7ba',
  }
})

const conversations = computed(() => [lingConversation.value, ...demoConversations].filter((conversation) => {
  const keyword = searchKey.value.trim()
  return !keyword || conversation.name.includes(keyword) || conversation.preview.includes(keyword)
}))

function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function openConversation(id: string): void {
  if (id !== 'ling') return
  router.push(presentation.staticPreview ? '/preview/chat' : '/chat/window')
}
</script>

<template>
  <div class="page">
    <header class="nav">
      <span class="nav-title">消息</span>
      <button class="nav-add" aria-label="新增会话"><UiIcon name="plus" :size="22" /></button>
    </header>

    <label class="search-bar">
      <UiIcon class="search-icon" name="search" :size="18" :stroke="1.8" />
      <input v-model="searchKey" placeholder="搜索" />
    </label>

    <div class="list">
      <button
        v-for="conversation in conversations"
        :key="conversation.id"
        class="chat-item"
        :class="{ passive: conversation.id !== 'ling' }"
        @click="openConversation(conversation.id)"
      >
        <div class="avatar-wrap">
          <EmotionAvatar
            v-if="conversation.id === 'ling'"
            :src="presentation.staticPreview && presentation.lingAvatar ? presentation.lingAvatar : profile.avatarUrl"
            :size="54"
            class="avatar"
          />
          <span v-else class="demo-avatar" :style="{ background: conversation.tone }">{{ conversation.name.slice(0, 1) }}</span>
          <span v-if="conversation.unread" class="badge">{{ conversation.unread }}</span>
        </div>
        <span class="info">
          <span class="row-one">
            <strong>{{ conversation.name }}</strong>
            <time>{{ conversation.time }}</time>
          </span>
          <span class="preview">{{ conversation.preview }}</span>
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.page { height: 100%; display: flex; flex-direction: column; background: var(--wx-bg); }
.nav { height: var(--wx-navbar-height); position: relative; display: flex; align-items: center; justify-content: center; background: var(--wx-glass-bg); backdrop-filter: blur(var(--wx-glass-blur)); -webkit-backdrop-filter: blur(var(--wx-glass-blur)); border-bottom: 0.5px solid var(--wx-glass-border); }
.nav-title { font-size: 17px; font-weight: 600; }
.nav-add { position: absolute; right: 14px; display: grid; place-items: center; color: var(--wx-icon); }
.search-bar { display: flex; align-items: center; gap: 7px; margin: 9px 12px; padding: 8px 12px; border-radius: var(--wx-radius-control); background: var(--wx-surface); color: var(--wx-icon-muted); }
.search-bar input { min-width: 0; flex: 1; color: var(--wx-text); font-size: 15px; }
.list { flex: 1; overflow-y: auto; background: var(--wx-surface); }
.chat-item { width: 100%; min-height: 76px; display: flex; align-items: center; gap: 12px; padding: 10px 14px; text-align: left; border-bottom: 0.5px solid var(--wx-line); }
.chat-item:active { background: var(--wx-press-overlay); opacity: 1; }
.chat-item.passive { cursor: default; }
.avatar-wrap { position: relative; flex: 0 0 54px; }
.avatar, .demo-avatar { display: grid; width: 54px; height: 54px; place-items: center; overflow: hidden; border-radius: var(--wx-radius-control); color: var(--wx-text-white); font-size: 22px; }
.badge { position: absolute; top: -5px; right: -5px; min-width: 20px; height: 20px; display: grid; place-items: center; padding: 0 5px; border: 1.5px solid var(--wx-surface); border-radius: 10px; background: var(--wx-danger); color: var(--wx-text-white); font-size: 11px; }
.info { min-width: 0; flex: 1; }
.row-one { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.row-one strong { overflow: hidden; font-size: 17px; font-weight: 400; text-overflow: ellipsis; white-space: nowrap; }
.row-one time { flex: 0 0 auto; color: var(--wx-text-tips); font-size: 12px; }
.preview { display: block; overflow: hidden; margin-top: 5px; color: var(--wx-text-desc); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
</style>
