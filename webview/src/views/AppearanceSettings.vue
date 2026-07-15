<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePresentationStore } from '@/stores/presentation'

const router = useRouter()
const presentation = usePresentationStore()

const name = ref(presentation.selfName)
const avatar = ref(presentation.selfAvatar)
const lingName = ref(presentation.lingName)
const lingAvatar = ref(presentation.lingAvatar)
const cover = ref(presentation.momentsCover)
const errorMessage = ref('')

function readImage(file: File): Promise<string> {
  if (!file.type.startsWith('image/')) {
    return Promise.reject(new Error('请选择图片文件'))
  }
  const maxFileSize = 5 * 1024 * 1024
  if (file.size > maxFileSize) {
    return Promise.reject(new Error('图片不能超过 5MB'))
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('图片读取失败'))
    reader.onload = () => {
      if (typeof reader.result !== 'string') {
        reject(new Error('图片格式无效'))
        return
      }
      resolve(reader.result)
    }
    reader.readAsDataURL(file)
  })
}

async function onFileChange(event: Event, target: 'avatar' | 'ling-avatar' | 'cover'): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  try {
    errorMessage.value = ''
    const dataUrl = await readImage(file)
    if (target === 'avatar') avatar.value = dataUrl
    else if (target === 'ling-avatar') lingAvatar.value = dataUrl
    else cover.value = dataUrl
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : '图片处理失败'
  } finally {
    input.value = ''
  }
}

function save(): void {
  try {
    presentation.updateSelfProfile(name.value, avatar.value)
    presentation.updateLingProfile(lingName.value, lingAvatar.value)
    presentation.updateMomentsCover(cover.value)
    router.back()
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : '保存失败'
  }
}
</script>

<template>
  <div class="appearance-page">
    <header class="nav">
      <button class="nav-action" @click="router.back()">取消</button>
      <span class="nav-title">展示设置</span>
      <button class="nav-action save" @click="save">保存</button>
    </header>

    <main class="content">
      <p class="hint">这些设置只用于静态预览；接入后端后可替换为真实资料接口。</p>

      <section class="section">
        <label class="cell preview-mode">
          <span>
            <strong>静态预览模式</strong>
            <small>关闭后恢复现有真实后端链路</small>
          </span>
          <input v-model="presentation.staticPreview" type="checkbox" />
          <i class="switch" aria-hidden="true" />
        </label>
      </section>

      <section class="section">
        <label class="cell">
          <span>我的展示名称</span>
          <input v-model="name" maxlength="20" placeholder="请输入名称" />
        </label>
        <label class="cell upload-cell">
          <span>我的头像</span>
          <span class="preview-avatar" :class="{ empty: !avatar }">
            <img v-if="avatar" :src="avatar" alt="我的头像" />
            <span v-else>{{ presentation.selfAvatarLabel }}</span>
          </span>
          <input type="file" accept="image/*" @change="onFileChange($event, 'avatar')" />
        </label>
      </section>

      <section class="section">
        <label class="cell">
          <span>Ling 的展示名称</span>
          <input v-model="lingName" maxlength="20" placeholder="请输入名称" />
        </label>
        <label class="cell upload-cell">
          <span>Ling 的头像</span>
          <span class="preview-avatar" :class="{ empty: !lingAvatar }">
            <img v-if="lingAvatar" :src="lingAvatar" alt="Ling 的头像" />
            <span v-else>{{ presentation.lingAvatarLabel }}</span>
          </span>
          <input type="file" accept="image/*" @change="onFileChange($event, 'ling-avatar')" />
        </label>
      </section>

      <section class="section">
        <label class="cover-picker">
          <span class="cover-title">朋友圈封面</span>
          <span class="cover-preview" :class="{ empty: !cover }" :style="cover ? { backgroundImage: `url(${cover})` } : {}" />
          <input type="file" accept="image/*" @change="onFileChange($event, 'cover')" />
        </label>
      </section>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </main>
  </div>
</template>

<style scoped lang="scss">
.appearance-page { height: 100%; background: var(--wx-bg); }
.nav { height: var(--wx-navbar-height); display: flex; align-items: center; background: var(--wx-glass-bg); backdrop-filter: blur(var(--wx-glass-blur)); -webkit-backdrop-filter: blur(var(--wx-glass-blur)); border-bottom: 0.5px solid var(--wx-glass-border); }
.nav-title { flex: 1; text-align: center; font-size: 17px; font-weight: 600; }
.nav-action { width: 64px; color: var(--wx-text-desc); font-size: 16px; }
.nav-action.save { color: var(--wx-brand); font-weight: 600; }
.content { padding-top: 12px; }
.hint { margin: 0 16px 10px; font-size: 13px; line-height: 1.5; color: var(--wx-text-desc); }
.section { margin: 0 8px 10px; background: var(--wx-bg-white); border-top: 0.5px solid var(--wx-line); border-bottom: 0.5px solid var(--wx-line); border-radius: var(--wx-radius-md); box-shadow: var(--wx-shadow-sm); overflow: hidden; }
.cell { min-height: 58px; display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 0.5px solid var(--wx-line); font-size: 16px; }
.cell:last-child { border-bottom: none; }
.cell input[type='text'], .cell input:not([type]) { flex: 1; min-width: 0; text-align: right; color: var(--wx-text); }
.upload-cell { position: relative; justify-content: space-between; cursor: pointer; }
.upload-cell input, .cover-picker input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.preview-avatar { width: 40px; height: 40px; overflow: hidden; border-radius: var(--wx-radius-control); background: #d9d9d9; display: grid; place-items: center; }
.preview-avatar.empty { background: linear-gradient(135deg, #8995a8, #596575); color: var(--wx-text-white); font-size: 17px; }
.preview-avatar img { width: 100%; height: 100%; object-fit: cover; }
.cover-picker { position: relative; display: block; padding: 14px 16px; cursor: pointer; }
.cover-title { display: block; margin-bottom: 10px; font-size: 16px; }
.cover-preview { height: 120px; display: block; border-radius: var(--wx-radius-sm); background-position: center; background-size: cover; }
.cover-preview.empty { background: linear-gradient(135deg, #778899, #bfd5e4 52%, #f0d9c2); }
.error { margin: 12px 16px; color: var(--wx-danger); font-size: 13px; }
.preview-mode { justify-content: space-between; }
.preview-mode strong, .preview-mode small { display: block; }
.preview-mode strong { font-size: 16px; font-weight: 400; }
.preview-mode small { margin-top: 3px; color: var(--wx-text-desc); font-size: 12px; }
.preview-mode input { position: absolute; opacity: 0; }
.switch { position: relative; width: 46px; height: 28px; border-radius: 14px; background: #d9d9d9; transition: background 0.2s; }
.switch::before { position: absolute; top: 2px; left: 2px; width: 24px; height: 24px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2); content: ''; transition: transform 0.2s; }
.preview-mode input:checked + .switch { background: var(--wx-brand); }
.preview-mode input:checked + .switch::before { transform: translateX(18px); }
</style>
