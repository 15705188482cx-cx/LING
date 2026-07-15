<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMomentsStore } from '@/stores/moments'

const router = useRouter()
const moments = useMomentsStore()

const content = ref('')
// images 存 base64 data URL（FileReader 转换），既能本地预览又能直接发给后端持久化
// 不能用 URL.createObjectURL——那是临时 blob URL，刷新后失效，发圈后存进 DB 也会变 404
const images = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

function pickImage() {
  fileInput.value?.click()
}

function onFileChosen(e: Event) {
  const t = e.target as HTMLInputElement
  const f = t.files?.[0]
  if (!f) return
  // 转 base64 data URL（image/jpeg 兜底，部分手机拍的是 image/jpeg）
  const reader = new FileReader()
  reader.onload = () => {
    if (typeof reader.result === 'string') {
      images.value.push(reader.result)
    }
  }
  reader.readAsDataURL(f)
  t.value = ''
}

function removeImage(i: number) {
  images.value.splice(i, 1)
}

async function onPost() {
  if (!content.value.trim() || moments.sending) return
  const ok = await moments.compose(content.value, images.value)
  if (ok) {
    router.push('/discover/moments')
  }
}
</script>

<template>
  <div class="compose-page">
    <header class="nav">
      <button class="back" @click="router.back()">取消</button>
      <span class="nav-title">发表朋友圈</span>
      <button class="post-btn" :disabled="!content.trim() || moments.sending" @click="onPost">
        {{ moments.sending ? '发表中…' : '发表' }}
      </button>
    </header>

    <div class="body">
      <textarea
        v-model="content"
        class="textarea"
        rows="6"
        placeholder="这一刻的想法…"
      />

      <!-- 图片预览 -->
      <div class="images-grid">
        <div v-for="(img, i) in images" :key="i" class="img-cell">
          <img :src="img" alt="" />
          <button class="img-del" @click="removeImage(i)">×</button>
        </div>
        <button v-if="images.length < 9" class="img-add" @click="pickImage">＋</button>
      </div>
    </div>

    <input ref="fileInput" type="file" accept="image/*" hidden @change="onFileChosen" />
  </div>
</template>

<style scoped lang="scss">
.compose-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--wx-bg-white);
}
.nav {
  height: var(--wx-navbar-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  background: var(--wx-glass-bg);
  backdrop-filter: blur(var(--wx-glass-blur));
  -webkit-backdrop-filter: blur(var(--wx-glass-blur));
  border-bottom: 0.5px solid var(--wx-glass-border);
  flex-shrink: 0;
}
.back {
  font-size: 16px;
  color: var(--wx-text);
}
.nav-title {
  font-size: 17px;
  font-weight: 600;
}
.post-btn {
  background: var(--wx-brand);
  color: var(--wx-text-white);
  font-size: 14px;
  padding: 6px 14px;
  border-radius: var(--wx-radius-sm);
  &:disabled {
    opacity: 0.4;
  }
}
.body {
  flex: 1;
  padding: 14px;
  overflow-y: auto;
}
.textarea {
  width: 100%;
  font-size: 17px;
  line-height: 1.5;
  resize: none;
  min-height: 120px;
}
.images-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-top: 14px;
}
.img-cell {
  position: relative;
  aspect-ratio: 1;
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: var(--wx-radius-sm);
  }
}
.img-del {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.7);
  color: var(--wx-text-white);
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.img-add {
  aspect-ratio: 1;
  background: var(--wx-bg-input);
  border-radius: var(--wx-radius-sm);
  font-size: 28px;
  color: var(--wx-text-tips);
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
