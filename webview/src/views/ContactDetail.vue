<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useProfileStore } from '@/stores/profile'
import EmotionAvatar from '@/components/EmotionAvatar.vue'
import ProfileEditor from '@/components/ProfileEditor.vue'
import UiIcon from '@/components/UiIcon.vue'

// 联系人详情 —— 微信"聊天信息"页风格
const router = useRouter()
const profile = useProfileStore()
const showEditor = ref(false)

// 资料项（签名读 profile，其余硬编码）
const profileItems = [
  { label: '备注', value: '嘉玲' },
  { label: '微信号', value: 'lijialing_ai' },
  { label: '地区', value: '上海' },
]

// 聊天信息项（icon 存 UiIcon 的 name 字符串，bg/fg 为莫兰迪浅底+同色系深图标）
const chatInfoItems = [
  { icon: 'search', label: '查找聊天记录', bg: 'var(--wx-morandi-blue)', fg: 'var(--wx-morandi-blue-fg)' },
  { icon: 'image', label: '聊天背景', bg: 'var(--wx-morandi-green)', fg: 'var(--wx-morandi-green-fg)' },
  { icon: 'bell-off', label: '消息免打扰', bg: 'var(--wx-morandi-amber)', fg: 'var(--wx-morandi-amber-fg)' },
  { icon: 'pin', label: '置顶聊天', bg: 'var(--wx-morandi-purple)', fg: 'var(--wx-morandi-purple-fg)' },
] as const
</script>

<template>
  <div class="page">
    <header class="nav">
      <button class="back" @click="router.push('/contacts')">‹</button>
      <span class="nav-title">聊天信息</span>
    </header>

    <div class="list">
      <!-- 头像 + 昵称（点进编辑） -->
      <button class="profile-card" @click="showEditor = true">
        <EmotionAvatar :src="profile.avatarUrl" :size="56" class="big-avatar" />
        <div class="profile-info">
          <div class="profile-name">{{ profile.name }}</div>
          <div class="profile-wx">微信号：lijialing_ai</div>
          <div class="profile-region">地区：上海</div>
        </div>
        <span class="card-arrow">›</span>
      </button>

      <!-- 资料项 -->
      <div class="section">
        <div v-for="it in profileItems" :key="it.label" class="cell">
          <span class="cell-label">{{ it.label }}</span>
          <span class="cell-value">{{ it.value }}</span>
          <span class="cell-arrow">›</span>
        </div>
        <!-- 个性签名：读 profile，点击可编辑 -->
        <button class="cell" @click="showEditor = true">
          <span class="cell-label">个性签名</span>
          <span class="cell-value">{{ profile.signature }}</span>
          <span class="cell-arrow">›</span>
        </button>
      </div>

      <!-- 聊天信息 -->
      <div class="section">
        <button v-for="it in chatInfoItems" :key="it.label" class="cell clickable">
          <span class="cell-ico" :style="{ background: it.bg, color: it.fg }"><UiIcon :name="it.icon" :size="16" /></span>
          <span class="cell-text">{{ it.label }}</span>
          <span class="cell-arrow">›</span>
        </button>
      </div>

      <!-- 设置当前聊天背景 / 字体 / 我的备注等省略 -->

      <!-- 操作 -->
      <div class="section">
        <button class="cell clickable danger" @click="router.push('/settings')">
          <span class="cell-text">清空聊天记录</span>
          <span class="cell-arrow">›</span>
        </button>
        <button class="cell clickable danger" @click="router.push('/video-call')">
          <span class="cell-text">视频通话</span>
          <span class="cell-arrow">›</span>
        </button>
      </div>

      <!-- 发消息 -->
      <button class="send-msg-btn" @click="router.push('/chat/window')">发消息</button>
    </div>

    <!-- 编辑资料弹层 -->
    <ProfileEditor :visible="showEditor" @close="showEditor = false" />
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
  margin-right: 44px;
}
.list {
  flex: 1;
  overflow-y: auto;
}

// 头像卡
.profile-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 14px;
  background: var(--wx-bg-white);
  border-bottom: 0.5px solid var(--wx-line);
  margin-bottom: 8px;
}
.big-avatar {
  width: 56px;
  height: 56px;
}
.profile-info {
  flex: 1;
}
.profile-name {
  font-size: 19px;
  font-weight: 500;
  color: var(--wx-text);
}
.profile-wx,
.profile-region {
  font-size: 13px;
  color: var(--wx-text-tips);
  margin-top: 4px;
}
.card-arrow {
  color: var(--wx-text-tips);
  font-size: 20px;
}

.section {
  background: var(--wx-bg-white);
  border-top: 0.5px solid var(--wx-line);
  border-bottom: 0.5px solid var(--wx-line);
  margin: 0 8px 8px;
  border-radius: var(--wx-radius-md);
  box-shadow: var(--wx-shadow-sm);
  overflow: hidden;
}
.cell {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  background: var(--wx-bg-white);
  border-bottom: 0.5px solid var(--wx-line);
  text-align: left;
  &:active {
    background: var(--wx-bg-active);
  }
  &:last-child {
    border-bottom: none;
  }
  &.danger .cell-text {
    color: var(--wx-danger);
  }
}
.cell-label {
  font-size: 16px;
  color: var(--wx-text);
  width: 80px;
  flex-shrink: 0;
}
.cell-value {
  flex: 1;
  font-size: 15px;
  color: var(--wx-text-desc);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cell-ico {
  width: 28px;
  height: 28px;
  border-radius: var(--wx-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
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

.send-msg-btn {
  display: block;
  width: calc(100% - 28px);
  margin: 14px auto;
  padding: 12px;
  background: var(--wx-brand);
  color: var(--wx-text-white);
  font-size: 16px;
  border-radius: var(--wx-radius-control);
  box-shadow: var(--wx-shadow-sm);
  &:active {
    background: var(--wx-brand-press);
  }
}
</style>
