<script setup lang="ts">
import { onActivated, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import UiIcon from '@/components/UiIcon.vue'
import { useMomentsStore } from '@/stores/moments'
import { usePresentationStore } from '@/stores/presentation'

defineOptions({ name: 'Discover' })

type IconName = 'moments' | 'video' | 'camera' | 'album' | 'search' | 'service' | 'star' | 'scan'
type Entry = {
  icon: IconName
  bg: string
  fg: string
  label: string
  to: string
  tip?: string
  badge?: boolean
}

const router = useRouter()
const moments = useMomentsStore()
const presentation = usePresentationStore()
const toastMessage = ref('')
let toastTimer: number | undefined

const entries: Entry[] = [
  { icon: 'moments', bg: 'var(--wx-morandi-amber)', fg: 'var(--wx-morandi-amber-fg)', label: '朋友圈', to: '/discover/moments', badge: true },
  { icon: 'video', bg: 'var(--wx-morandi-rose)', fg: 'var(--wx-morandi-rose-fg)', label: '视频号', to: '', tip: '暂未开放' },
  { icon: 'camera', bg: 'var(--wx-morandi-rose)', fg: 'var(--wx-morandi-rose-fg)', label: '直播', to: '', tip: '暂未开放' },
  { icon: 'album', bg: 'var(--wx-morandi-blue)', fg: 'var(--wx-morandi-blue-fg)', label: '看一看', to: '', tip: '暂未开放' },
  { icon: 'search', bg: 'var(--wx-morandi-blue)', fg: 'var(--wx-morandi-blue-fg)', label: '搜一搜', to: '', tip: '暂未开放' },
  { icon: 'service', bg: 'var(--wx-morandi-rose)', fg: 'var(--wx-morandi-rose-fg)', label: '购物', to: '', tip: '暂未开放' },
  { icon: 'star', bg: 'var(--wx-morandi-green)', fg: 'var(--wx-morandi-green-fg)', label: '游戏', to: '', tip: '暂未开放' },
  { icon: 'scan', bg: 'var(--wx-morandi-green)', fg: 'var(--wx-morandi-green-fg)', label: '小程序', to: '', tip: '暂未开放' },
]

function startPolling(): void {
  if (!presentation.staticPreview) moments.startPolling(30)
}

function showToast(message: string): void {
  toastMessage.value = message
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => { toastMessage.value = '' }, 1500)
}

function onTap(entry: Entry): void {
  if (entry.to) {
    router.push(entry.to)
    return
  }
  if (entry.tip) showToast(entry.tip)
}

onMounted(startPolling)
onActivated(startPolling)
onBeforeUnmount(() => {
  moments.stopPolling()
  if (toastTimer) window.clearTimeout(toastTimer)
})
</script>

<template>
  <div class="page">
    <header class="nav"><span class="nav-title">发现</span></header>

    <main class="list">
      <section class="section">
        <button
          v-for="(entry, index) in entries"
          :key="entry.label"
          class="cell"
          :class="{ 'section-break': index === 1 || index === 4 || index === 6 }"
          @click="onTap(entry)"
        >
          <span class="cell-icon" :style="{ background: entry.bg, color: entry.fg }"><UiIcon :name="entry.icon" :size="18" :stroke="1.85" /></span>
          <span class="cell-text">{{ entry.label }}</span>
          <span v-if="entry.badge && (presentation.staticPreview || moments.newCount > 0)" class="badge">
            {{ presentation.staticPreview ? 1 : (moments.newCount > 99 ? '99+' : moments.newCount) }}
          </span>
          <span class="arrow">›</span>
        </button>
      </section>
    </main>

    <Transition name="toast"><div v-if="toastMessage" class="toast">{{ toastMessage }}</div></Transition>
  </div>
</template>

<style scoped lang="scss">
.page { height: 100%; display: flex; flex-direction: column; background: var(--wx-bg); }
.nav { height: var(--wx-navbar-height); display: flex; align-items: center; justify-content: center; background: var(--wx-glass-bg); backdrop-filter: blur(var(--wx-glass-blur)); -webkit-backdrop-filter: blur(var(--wx-glass-blur)); border-bottom: 0.5px solid var(--wx-glass-border); }
.nav-title { font-size: 17px; font-weight: 600; }
.list { flex: 1; overflow-y: auto; }
.section { margin-top: 8px; background: var(--wx-surface); border-top: 0.5px solid var(--wx-line); border-bottom: 0.5px solid var(--wx-line); }
.cell { position: relative; width: 100%; min-height: 55px; display: flex; align-items: center; gap: 12px; padding: 11px 14px; background: var(--wx-surface); border-bottom: 0.5px solid var(--wx-line); text-align: left; }
.cell:active { background: var(--wx-press-overlay); opacity: 1; }
.cell.section-break { margin-top: 8px; border-top: 0.5px solid var(--wx-line); }
.cell.section-break::before { position: absolute; top: -9px; right: 0; left: 0; height: 8px; background: var(--wx-bg); content: ''; }
.cell:last-child { border-bottom: none; }
.cell-icon { width: 28px; height: 28px; border-radius: var(--wx-radius-sm); display: grid; place-items: center; flex-shrink: 0; }
.cell-text { flex: 1; font-size: 16px; color: var(--wx-text); }
.badge { min-width: 19px; height: 19px; display: grid; place-items: center; padding: 0 5px; border-radius: 10px; background: var(--wx-danger); color: var(--wx-text-white); font-size: 11px; }
.arrow { color: var(--wx-icon-muted); font-size: 22px; font-weight: 300; }
.toast { position: absolute; top: 50%; left: 50%; padding: 10px 18px; transform: translate(-50%, -50%); border-radius: var(--wx-radius-md); background: rgba(0, 0, 0, 0.75); color: var(--wx-text-white); font-size: 14px; }
.toast-enter-active, .toast-leave-active { transition: opacity var(--wx-duration-normal) var(--wx-ease); }
.toast-enter-from, .toast-leave-to { opacity: 0; }
</style>
