<script setup lang="ts">
import { useRouter } from 'vue-router'
import EmotionAvatar from '@/components/EmotionAvatar.vue'
import UiIcon from '@/components/UiIcon.vue'
import { useProfileStore } from '@/stores/profile'

defineOptions({ name: 'Contacts' })

const router = useRouter()
const profile = useProfileStore()

// 微信通讯录经典功能入口（icon 存 UiIcon name 字符串，bg/fg 为莫兰迪浅底+同色系深图标）
const shortcuts = [
  { icon: 'users', label: '新的朋友', bg: 'var(--wx-morandi-amber)', fg: 'var(--wx-morandi-amber-fg)' },
  { icon: 'comment', label: '仅聊天的朋友', bg: 'var(--wx-morandi-green)', fg: 'var(--wx-morandi-green-fg)' },
  { icon: 'tag', label: '标签', bg: 'var(--wx-morandi-blue)', fg: 'var(--wx-morandi-blue-fg)' },
  { icon: 'megaphone', label: '公众号', bg: 'var(--wx-morandi-purple)', fg: 'var(--wx-morandi-purple-fg)' },
  { icon: 'building', label: '企业微信联系人', bg: 'var(--wx-morandi-blue-deep)', fg: 'var(--wx-morandi-blue-deep-fg)' },
] as const
</script>

<template>
  <div class="page">
    <header class="nav"><span class="nav-title">通讯录</span></header>

    <div class="list">
      <!-- 搜索栏 -->
      <div class="search-bar">
        <UiIcon class="search-ico" name="search" :size="14" />
        <input class="search-input" placeholder="搜索" />
      </div>

      <!-- 功能入口 -->
      <div class="section">
        <button v-for="s in shortcuts" :key="s.label" class="cell">
          <span class="cell-ico" :style="{ background: s.bg, color: s.fg }"><UiIcon :name="s.icon" :size="18" /></span>
          <span class="cell-text">{{ s.label }}</span>
          <span class="cell-arrow">›</span>
        </button>
      </div>

      <!-- 联系人 -->
      <div class="section-head">L</div>
      <button class="cell contact" @click="router.push('/contacts/detail')">
        <EmotionAvatar :src="profile.avatarUrl" :size="40" class="cell-avatar" />
        <span class="cell-text">{{ profile.name }}</span>
      </button>
    </div>
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
.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 10px;
  padding: 7px 10px;
  background: var(--wx-bg-input);
  border-radius: var(--wx-radius-control);
}
.search-ico {
  font-size: 13px;
  opacity: 0.5;
}
.search-input {
  flex: 1;
  font-size: 15px;
}
.section {
  background: var(--wx-bg-white);
  border-top: 0.5px solid var(--wx-line);
  border-bottom: 0.5px solid var(--wx-line);
  margin-bottom: 8px;
}
.section-head {
  padding: 6px 14px;
  font-size: 13px;
  color: var(--wx-text-tips);
  background: var(--wx-bg-white);
  border-top: 0.5px solid var(--wx-line);
  border-bottom: 0.5px solid var(--wx-line);
}
.cell {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--wx-bg-white);
  border-bottom: 0.5px solid var(--wx-line);
  text-align: left;
  &:active {
    background: var(--wx-bg-active);
  }
  &:last-child {
    border-bottom: none;
  }
}
.cell-ico {
  width: 40px;
  height: 40px;
  border-radius: var(--wx-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.cell-avatar {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
}
.cell-text {
  flex: 1;
  font-size: 16px;
  color: var(--wx-text);
}
.cell-arrow {
  color: var(--wx-text-tips);
  font-size: 18px;
}
</style>
