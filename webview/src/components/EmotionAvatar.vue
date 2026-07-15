<script setup lang="ts">
import { computed } from 'vue'
import type { Emotion } from '@/api/backend'

// 情绪驱动的头像切换已停用：前端固定用日常头像，避免聊天时头像频繁变化打断沉浸感。
// 后台仍判断情绪（驱动回复语气），只是前端不再体现情绪状态。
// 支持自定义头像：传 src 用 src，不传用默认 svg（由 profile store 控制）。
import daily from '@/assets/avatars/daily.svg'

const props = defineProps<{
  emotion?: Emotion
  size?: number
  src?: string  // 自定义头像 URL（base64 或路径）；优先于默认头像
}>()

const src = computed(() => props.src || daily)
const px = computed(() => (props.size ?? 40) + 'px')
</script>

<template>
  <img class="emotion-avatar" :src="src" :style="{ width: px, height: px }" alt="avatar" />
</template>

<style scoped lang="scss">
.emotion-avatar {
  border-radius: 6px;
  object-fit: cover;
  display: block;
}
</style>
