<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMomentsStore } from '@/stores/moments'
import { usePresentationStore } from '@/stores/presentation'
import MomentCard from '@/components/MomentCard.vue'
import UiIcon from '@/components/UiIcon.vue'
import type { Moment } from '@/api/backend'

const router = useRouter()
const moments = useMomentsStore()
const presentation = usePresentationStore()

const demoMoments: Moment[] = [
  {
    id: 'preview-1',
    author: '刘嘉玲',
    content: '今天路过一家很香的小店，想和你一起去。',
    ts: Date.now() / 1000 - 180,
    likes: [{ name: '我' }],
    comments: [{ id: 'preview-comment-1', name: '我', text: '下次一起去', ts: Date.now() / 1000 - 120 }],
  },
  {
    id: 'preview-2',
    author: '我',
    content: '把今天的小事记下来。',
    ts: Date.now() / 1000 - 5400,
    likes: [{ name: '刘嘉玲' }],
    comments: [],
  },
]
const displayItems = computed(() => presentation.staticPreview ? demoMoments : moments.items)

const listEl = ref<HTMLElement | null>(null)
// 下拉刷新状态
const refreshing = ref(false)
const pullY = ref(0)
const touchStartY = ref(0)

onMounted(async () => {
  if (!presentation.staticPreview) {
    await moments.refresh()
    moments.markSeen()
  }
})

// 下拉刷新
function onTouchStart(e: TouchEvent) {
  if (listEl.value && listEl.value.scrollTop === 0) {
    touchStartY.value = e.touches[0].clientY
  }
}
function onTouchMove(e: TouchEvent) {
  if (!touchStartY.value) return
  const dy = e.touches[0].clientY - touchStartY.value
  if (dy > 0 && listEl.value && listEl.value.scrollTop === 0) {
    pullY.value = Math.min(dy * 0.5, 60)
  }
}
async function onTouchEnd() {
  if (pullY.value > 40 && !presentation.staticPreview) {
    refreshing.value = true
    await moments.refresh()
    moments.markSeen()
    refreshing.value = false
  }
  pullY.value = 0
  touchStartY.value = 0
}
</script>

<template>
  <div class="moments-page">
    <!-- 顶部导航 -->
    <header class="nav">
      <button class="back" @click="router.push('/discover')">‹</button>
      <span class="nav-title">朋友圈</span>
      <button class="camera" @click="router.push('/discover/moments/compose')"><UiIcon name="camera" :size="20" /></button>
    </header>

    <!-- 列表 -->
    <div
      ref="listEl"
      class="list"
      @touchstart.passive="onTouchStart"
      @touchmove.passive="onTouchMove"
      @touchend="onTouchEnd"
    >
      <!-- 下拉刷新提示 -->
      <div class="pull-tip" :style="{ height: pullY + 'px' }">
        {{ refreshing ? '刷新中…' : pullY > 40 ? '松开刷新' : '下拉刷新' }}
      </div>

      <!-- 封面 -->
      <div class="cover">
        <div
          class="cover-img"
          :class="{ configured: Boolean(presentation.momentsCover) }"
          :style="presentation.momentsCover ? { backgroundImage: `url(${presentation.momentsCover})` } : {}"
        />
        <div class="cover-info">
          <div class="cover-name">{{ presentation.selfName }}</div>
          <span class="self-avatar" :class="{ photo: presentation.selfAvatar }">
            <img v-if="presentation.selfAvatar" :src="presentation.selfAvatar" alt="我的头像" />
            <span v-else>{{ presentation.selfAvatarLabel }}</span>
          </span>
        </div>
      </div>

      <!-- 动态列表 -->
      <MomentCard v-for="m in displayItems" :key="m.id" :moment="m" :interactive="!presentation.staticPreview" />

      <!-- 空态：骨架占位（3 张灰块卡片）替代纯文字，提升档次 -->
      <div v-if="displayItems.length === 0 && !moments.loading" class="empty">
        <div class="skeleton-card" v-for="i in 3" :key="i">
          <div class="sk-line sk-w-40"></div>
          <div class="sk-line sk-w-80"></div>
          <div class="sk-line sk-w-60"></div>
        </div>
        <div class="empty-text">还没有朋友圈动态</div>
      </div>
      <!-- 加载态：spinner + 文案 -->
      <div v-if="moments.loading" class="loading">
        <span class="spinner"></span>
        <span>加载中…</span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.moments-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--wx-surface);
}
.nav {
  height: var(--wx-navbar-height);
  display: flex;
  align-items: center;
  background: var(--wx-nav-bg);
  border-bottom: 0.5px solid var(--wx-line);
  flex-shrink: 0;
  position: relative;
  z-index: 5;
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
.camera {
  padding: 0 14px;
  color: var(--wx-text);
  display: inline-flex;
  align-items: center;
}

.list {
  flex: 1;
  overflow-y: auto;
  background: var(--wx-surface);
}

.pull-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--wx-text-tips);
  overflow: hidden;
}

// 封面
.cover {
  position: relative;
  height: 280px;
  background: linear-gradient(135deg, #6b8cce, #8e6bcd);
  margin-bottom: 40px;
}
.cover-img {
  width: 100%;
  height: 100%;
  // 与 .cover 渐变统一，避免两层叠加色调冲突
  background: linear-gradient(135deg, #6b8cce, #8e6bcd);
  background-position: center;
  background-size: cover;
}
.cover-info {
  position: absolute;
  bottom: -40px;
  right: 14px;
  display: flex;
  align-items: flex-end;
  gap: 12px;
}
.cover-name {
  font-size: 17px;
  font-weight: 600;
  color: var(--wx-text-white);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  margin-bottom: 48px;
}
.self-avatar {
  width: 70px;
  height: 70px;
  border: 3px solid var(--wx-bg-white);
  border-radius: var(--wx-radius-md);
  overflow: hidden;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #71809a, #404a5a);
  color: var(--wx-text-white);
  font-size: 22px;
}
.self-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

// 空态：骨架屏（shimmer 动画）替代纯文字
.empty {
  padding: 16px 14px 40px;
}
.skeleton-card {
  padding: 14px;
  background: var(--wx-bg-white);
  border-bottom: 0.5px solid var(--wx-line);
}
.sk-line {
  height: 14px;
  border-radius: var(--wx-radius-sm);
  background: linear-gradient(90deg, var(--wx-bg-input) 25%, var(--wx-bg-active) 50%, var(--wx-bg-input) 75%);
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s var(--wx-ease) infinite;
  margin-bottom: 8px;
}
.sk-w-40 { width: 40%; }
.sk-w-60 { width: 60%; }
.sk-w-80 { width: 80%; }
@keyframes sk-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.empty-text {
  text-align: center;
  font-size: 14px;
  color: var(--wx-text-tips);
  padding: 24px 0 0;
}

// 加载态：spinner + 文案
.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  color: var(--wx-text-tips);
  padding: 40px 0;
}
.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--wx-line);
  border-top-color: var(--wx-brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
