<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// 4 tab：消息 / 通讯录 / 发现 / 我（真微信结构）
// 图标全用 chat-uniapp 的真·微信 tab 图标 PNG（MPL-2.0）
import iconChat from '@/assets/icons/n0.png'
import iconChatOn from '@/assets/icons/n0_on.png'
import iconContacts from '@/assets/icons/n01.png'
import iconContactsOn from '@/assets/icons/n01_on.png'
import iconDiscover from '@/assets/icons/n02.png'
import iconDiscoverOn from '@/assets/icons/n02_on.png'
import iconMe from '@/assets/icons/n03.png'
import iconMeOn from '@/assets/icons/n03_on.png'

const route = useRoute()
const router = useRouter()

type Tab = {
  key: string
  text: string
  to: string
  png: { off: string; on: string }
}

const tabs: Tab[] = [
  { key: 'chat', text: '消息', to: '/chat', png: { off: iconChat, on: iconChatOn } },
  { key: 'contacts', text: '通讯录', to: '/contacts', png: { off: iconContacts, on: iconContactsOn } },
  { key: 'discover', text: '发现', to: '/discover', png: { off: iconDiscover, on: iconDiscoverOn } },
  { key: 'me', text: '我', to: '/me', png: { off: iconMe, on: iconMeOn } },
]

const activeTab = computed(() => (route.meta.tab as string) || '')
</script>

<template>
  <nav class="tabbar">
    <button
      v-for="t in tabs"
      :key="t.key"
      class="tab"
      :class="{ active: activeTab === t.key }"
      @click="router.push(t.to)"
    >
      <img class="tab-icon" :src="activeTab === t.key ? t.png.on : t.png.off" :alt="t.text" />
      <span class="tab-text">{{ t.text }}</span>
    </button>
  </nav>
</template>

<style scoped lang="scss">
.tabbar {
  display: flex;
  height: var(--wx-tabbar-height);
  // 毛玻璃底：半透明白 + blur + 发光边框（仅底部浮层用，正文保持扁平）
  background: var(--wx-glass-bg);
  backdrop-filter: blur(var(--wx-glass-blur));
  -webkit-backdrop-filter: blur(var(--wx-glass-blur));
  border-top: 0.5px solid var(--wx-glass-border);
  padding-bottom: var(--wx-safe-bottom);
  flex-shrink: 0;
}

.tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  color: var(--wx-tab-color);
  transition: color var(--wx-duration-fast) var(--wx-ease), transform var(--wx-duration-fast) var(--wx-ease);

  &.active {
    color: var(--wx-tab-selected);
  }
  &:active {
    opacity: 1;
    transform: scale(0.94);
  }
}

.tab-icon {
  width: 22px;
  height: 22px;
  object-fit: contain;
  display: block;
}

.tab-text {
  font-size: 10px;
  line-height: 1;
}
</style>
