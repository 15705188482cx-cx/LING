<script setup lang="ts">
import { computed, ref } from 'vue'
import EmotionAvatar from './EmotionAvatar.vue'
import UiIcon from './UiIcon.vue'
import { useMomentsStore } from '@/stores/moments'
import type { Moment } from '@/api/backend'

const props = withDefaults(defineProps<{ moment: Moment; interactive?: boolean }>(), {
  interactive: true,
})
const moments = useMomentsStore()

const liked = computed(() => moments.likedByMe(props.moment))
const likeCount = computed(() => props.moment.likes.length)
const commentCount = computed(() => props.moment.comments.length)

// 时间格式
function fmtTime(ts: number): string {
  const diff = Date.now() / 1000 - ts
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

// 点赞
function onLike() {
  if (!props.interactive) return
  moments.toggleLike(props.moment.id)
}

// 评论
const showCommentInput = ref(false)
const commentText = ref('')
function onComment() {
  if (!props.interactive) return
  showCommentInput.value = true
}
async function submitComment() {
  if (!props.interactive) return
  if (!commentText.value.trim()) return
  await moments.comment(props.moment.id, commentText.value)
  commentText.value = ''
  showCommentInput.value = false
}

// 点赞人列表（昵称用逗号连）
const likeNames = computed(() => props.moment.likes.map((l) => l.name).join('，'))
</script>

<template>
  <div class="moment-card">
    <div class="row">
      <EmotionAvatar :emotion="moment.author === '刘嘉玲' ? '日常' : undefined" :size="42" class="avatar" />
      <div class="info">
        <div class="name" :class="{ mine: moment.author === '我' }">{{ moment.author }}</div>
        <div class="time">{{ fmtTime(moment.ts) }}{{ moment.source ? ' · ' + moment.source : '' }}</div>
      </div>
    </div>

    <!-- 正文 -->
    <div v-if="moment.content" class="content">{{ moment.content }}</div>

    <!-- 图片 -->
    <div v-if="moment.images && moment.images.length" class="images">
      <img v-for="(img, i) in moment.images" :key="i" :src="img" class="moment-img" alt="" />
    </div>

    <!-- 操作栏 -->
    <div class="actions">
      <span class="time-small">{{ fmtTime(moment.ts) }}</span>
      <div class="action-btns">
        <button class="action-btn" :class="{ liked }" :disabled="!interactive" @click="onLike">
          <UiIcon class="ico" :name="liked ? 'heart-filled' : 'heart'" :size="16" />
        </button>
        <button class="action-btn" :disabled="!interactive" @click="onComment">
          <UiIcon class="ico" name="comment" :size="16" />
        </button>
      </div>
    </div>

    <!-- 点赞 + 评论区 -->
    <div v-if="likeCount > 0 || commentCount > 0" class="feedback">
      <!-- 点赞 -->
      <div v-if="likeCount > 0" class="like-row">
        <UiIcon class="like-ico" name="heart-filled" :size="12" />
        <span class="like-names">{{ likeNames }}</span>
      </div>
      <!-- 评论 -->
      <div v-if="commentCount > 0" class="comments">
        <div v-for="c in moment.comments" :key="c.id" class="comment">
          <span class="c-name" :class="{ mine: c.name === '我' }">{{ c.name }}</span>
          <span class="c-text">：{{ c.text }}</span>
          <!-- 她的回复 -->
          <div v-if="c.reply" class="c-reply">
            <span class="reply-name">刘嘉玲</span>
            <span class="reply-text">：{{ c.reply }}</span>
            <span v-if="c.reply_emotion" class="reply-emo">{{ c.reply_emotion }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 评论输入框 -->
    <div v-if="showCommentInput" class="comment-input">
      <input
        v-model="commentText"
        class="c-input"
        placeholder="评论…"
        @keydown.enter="submitComment"
        @keydown.esc="showCommentInput = false"
      />
      <button class="c-send" :disabled="!commentText.trim()" @click="submitComment">发送</button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.moment-card {
  padding: 14px;
  background: var(--wx-bg-white);
  border-bottom: 0.5px solid var(--wx-line);
}
.row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.avatar {
  width: 42px;
  height: 42px;
  flex-shrink: 0;
}
.info {
  flex: 1;
}
.name {
  font-size: 15px;
  font-weight: 600;
  color: var(--wx-link); // 微信昵称蓝
  &.mine {
    color: var(--wx-link);
  }
}
.time {
  font-size: 12px;
  color: var(--wx-text-tips);
  margin-top: 2px;
}
.content {
  font-size: 16px;
  color: var(--wx-text);
  line-height: 1.5;
  margin-top: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}
.images {
  margin-top: 8px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
}
.moment-img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: var(--wx-radius-sm);
}
.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}
.time-small {
  font-size: 12px;
  color: var(--wx-text-tips);
}
.action-btns {
  display: flex;
  gap: 16px;
  background: var(--wx-bg-input);
  border-radius: var(--wx-radius-sm);
  padding: 2px 10px;
}
.action-btn {
  color: var(--wx-text-desc);
  display: inline-flex;
  align-items: center;
  &.liked {
    color: var(--wx-danger); // 已点赞红心
  }
  .ico {
    display: block;
  }
}
.feedback {
  background: var(--wx-bg-input);
  border-radius: var(--wx-radius-sm);
  margin-top: 8px;
  padding: 6px 10px;
}
.like-row {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 0;
  border-bottom: 0.5px solid var(--wx-line);
}
.like-ico {
  color: var(--wx-danger);
  display: inline-flex;
}
.like-names {
  font-size: 13px;
  color: var(--wx-link);
}
.comments {
  padding-top: 4px;
}
.comment {
  padding: 3px 0;
  font-size: 13px;
  line-height: 1.5;
}
.c-name {
  color: var(--wx-link);
  &.mine {
    color: var(--wx-link);
  }
}
.c-text {
  color: var(--wx-text);
}
.c-reply {
  margin-top: 3px;
  margin-left: 12px;
  padding: 4px 8px;
  background: var(--wx-brand-soft);
  border-radius: var(--wx-radius-sm);
  font-size: 13px;
}
.reply-name {
  color: var(--wx-brand);
  font-weight: 500;
}
.reply-text {
  color: var(--wx-text);
}
.reply-emo {
  font-size: 11px;
  color: var(--wx-text-tips);
  margin-left: 6px;
  background: var(--wx-bg-white);
  padding: 1px 5px;
  border-radius: var(--wx-radius-sm);
}
.comment-input {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.c-input {
  flex: 1;
  height: 34px;
  padding: 0 10px;
  background: var(--wx-bg-input);
  border-radius: var(--wx-radius-sm);
  font-size: 14px;
}
.c-send {
  background: var(--wx-brand);
  color: var(--wx-text-white);
  font-size: 14px;
  padding: 0 14px;
  border-radius: var(--wx-radius-sm);
  height: 34px;
  &:disabled {
    opacity: 0.5;
  }
}
</style>
