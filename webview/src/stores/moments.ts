import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api/backend'
import type { Moment, MomentComment } from '@/api/backend'

// 朋友圈状态：列表 / 点赞 / 评论 / 轮询新动态 / 发圈 / 发圈频率配置

export const useMomentsStore = defineStore('moments', () => {
  const items = ref<Moment[]>([])
  const loading = ref(false)
  const sending = ref(false)
  const error = ref<string | null>(null)
  // 上次查看时间戳（用于红点未读计数）
  const lastSeenTs = ref<number>(Number(localStorage.getItem('ling:moments_last_seen')) || 0)
  const newCount = ref(0)
  // 发圈频率配置
  const postInterval = ref(300)
  let pollTimer: number | null = null

  // 我是否已赞某条
  function likedByMe(m: Moment): boolean {
    return m.likes.some((l) => l.name === '我')
  }

  // 拉列表
  async function load(refresh = false) {
    loading.value = true
    error.value = null
    try {
      const before = refresh ? undefined : items.value.length ? items.value[items.value.length - 1].ts : undefined
      const res = await api.getMoments(20, before)
      if (refresh) {
        items.value = res.items
      } else {
        // 去重合并
        const ids = new Set(items.value.map((m) => m.id))
        for (const m of res.items) {
          if (!ids.has(m.id)) items.value.push(m)
        }
      }
      // 更新最新时间戳
      if (items.value.length) {
        const maxTs = Math.max(...items.value.map((m) => m.ts))
        if (maxTs > lastSeenTs.value) {
          // 不立即清红点，等用户实际查看 Moments 页才清
        }
      }
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  }

  // 刷新（下拉刷新）：拉最新
  async function refresh() {
    await load(true)
    // 刷新后清红点
    markSeen()
  }

  // 标记已查看（进 Moments 页调）：清红点 + 记录时间
  function markSeen() {
    const maxTs = items.value.length ? Math.max(...items.value.map((m) => m.ts)) : Date.now() / 1000
    lastSeenTs.value = maxTs
    localStorage.setItem('ling:moments_last_seen', String(maxTs))
    newCount.value = 0
  }

  // 轮询新动态数（Discover 页红点用）
  async function pollNewCount() {
    try {
      const res = await api.getNewCount(lastSeenTs.value)
      newCount.value = res.count
    } catch {
      // 静默
    }
  }

  // 启动轮询（进 Discover 页调）
  function startPolling(intervalSec = 30) {
    stopPolling()
    pollNewCount()
    pollTimer = window.setInterval(pollNewCount, intervalSec * 1000)
  }
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  // 点赞/取消
  async function toggleLike(momentId: string) {
    const m = items.value.find((x) => x.id === momentId)
    if (!m) return
    const wasLiked = likedByMe(m)
    // 乐观更新
    if (wasLiked) {
      m.likes = m.likes.filter((l) => l.name !== '我')
    } else {
      m.likes.push({ name: '我' })
    }
    try {
      await api.toggleLike(momentId)
    } catch {
      // 回滚
      if (wasLiked) {
        m.likes.push({ name: '我' })
      } else {
        m.likes = m.likes.filter((l) => l.name !== '我')
      }
    }
  }

  // 评论
  async function comment(momentId: string, text: string): Promise<void> {
    const m = items.value.find((x) => x.id === momentId)
    if (!m || !text.trim()) return
    // 乐观加我的评论（无回复，等后端返回补）
    const tempComment: MomentComment = {
      id: 'temp_' + Date.now(),
      name: '我',
      text: text.trim(),
      ts: Date.now() / 1000,
    }
    m.comments.push(tempComment)
    try {
      const res = await api.postComment(momentId, text.trim())
      // 后端返回 reply，补到临时评论上
      if (res.reply) {
        tempComment.reply = res.reply
        tempComment.reply_emotion = res.reply_emotion
      }
      tempComment.id = res.comment_id
    } catch {
      tempComment.reply = '（回复失败）'
    }
  }

  // 发圈
  async function compose(content: string, images: string[] = []): Promise<boolean> {
    if (!content.trim() || sending.value) return false
    sending.value = true
    try {
      await api.postMoment(content.trim(), images)
      // 发完刷新列表
      await load(true)
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      sending.value = false
    }
  }

  // 发圈频率配置
  async function loadConfig() {
    try {
      const c = await api.getMomentsConfig()
      postInterval.value = c.post_interval_sec
    } catch {
      // 静默
    }
  }
  async function saveConfig(intervalSec: number) {
    postInterval.value = intervalSec
    await api.setMomentsConfig(intervalSec)
  }

  return {
    items,
    loading,
    sending,
    error,
    newCount,
    postInterval,
    likedByMe,
    load,
    refresh,
    markSeen,
    startPolling,
    stopPolling,
    toggleLike,
    comment,
    compose,
    loadConfig,
    saveConfig,
  }
})
