<script setup lang="ts">
import { ref } from 'vue'
import { useProfileStore } from '@/stores/profile'
import EmotionAvatar from './EmotionAvatar.vue'

// 个人资料编辑弹层：头像（本地上传压缩）+ 名字 + 签名
const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: [] }>()

const profile = useProfileStore()

// 本地编辑副本（保存前不直接改 store）
const name = ref(profile.name)
const signature = ref(profile.signature)
const avatar = ref(profile.avatar)  // base64 data URL
const saving = ref(false)
const errMsg = ref('')

/** 本地图片 → 压缩到最大边 256px JPEG quality 0.8 → base64 data URL */
async function onPickAvatar(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  errMsg.value = ''
  try {
    const dataUrl = await compressImage(file, 256, 0.8)
    avatar.value = dataUrl
  } catch (err) {
    errMsg.value = '图片处理失败：' + (err as Error).message
  }
  // 清空 input 允许重复选同一张
  input.value = ''
}

/** File → Image → canvas 压缩 → data URL */
function compressImage(file: File, maxEdge: number, quality: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => {
        let { width, height } = img
        if (width > height && width > maxEdge) {
          height = Math.round(height * maxEdge / width)
          width = maxEdge
        } else if (height > maxEdge) {
          width = Math.round(width * maxEdge / height)
          height = maxEdge
        }
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        if (!ctx) return reject(new Error('canvas 不可用'))
        ctx.drawImage(img, 0, 0, width, height)
        resolve(canvas.toDataURL('image/jpeg', quality))
      }
      img.onerror = () => reject(new Error('图片加载失败'))
      img.src = reader.result as string
    }
    reader.onerror = () => reject(new Error('文件读取失败'))
    reader.readAsDataURL(file)
  })
}

/** 清除自定义头像，回退默认 */
function clearAvatar() {
  avatar.value = ''
}

async function onSave() {
  if (!name.value.trim()) {
    errMsg.value = '名字不能为空'
    return
  }
  saving.value = true
  errMsg.value = ''
  try {
    await profile.update({
      name: name.value.trim(),
      signature: signature.value.trim(),
      avatar: avatar.value,
    })
    emit('close')
  } catch (e) {
    errMsg.value = '保存失败：' + (e as Error).message
  } finally {
    saving.value = false
  }
}

/** 打开时同步最新值 */
function syncFromStore() {
  name.value = profile.name
  signature.value = profile.signature
  avatar.value = profile.avatar
}
// visible 变 true 时同步（watch 避免初始触发）
import { watch } from 'vue'
watch(() => props.visible, (v) => { if (v) syncFromStore() })
</script>

<template>
  <div v-if="visible" class="editor-mask" @click.self="emit('close')">
    <div class="editor-sheet">
      <header class="editor-head">
        <button class="cancel" @click="emit('close')">取消</button>
        <span class="title">编辑资料</span>
        <button class="save" :disabled="saving" @click="onSave">{{ saving ? '保存中' : '保存' }}</button>
      </header>

      <div class="editor-body">
        <!-- 头像 -->
        <div class="field avatar-field">
          <span class="field-label">头像</span>
          <label class="avatar-pick">
            <EmotionAvatar :src="avatar" :size="64" />
            <input type="file" accept="image/*" @change="onPickAvatar" hidden />
            <span class="pick-hint">点击更换</span>
          </label>
          <button v-if="avatar" class="clear-avatar" @click="clearAvatar">移除</button>
        </div>

        <!-- 名字 -->
        <div class="field">
          <span class="field-label">名字</span>
          <input v-model="name" class="field-input" maxlength="20" placeholder="她的名字" />
        </div>

        <!-- 签名 -->
        <div class="field">
          <span class="field-label">签名</span>
          <textarea v-model="signature" class="field-textarea" maxlength="50" rows="2" placeholder="个性签名"></textarea>
        </div>

        <p v-if="errMsg" class="err">{{ errMsg }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.editor-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-end;
  z-index: 100;
}
.editor-sheet {
  width: 100%;
  background: var(--wx-bg, #ededed);
  border-radius: 16px 16px 0 0;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}
.editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--wx-bg-white, #fff);
  border-bottom: 0.5px solid var(--wx-line, #e5e5e5);
  border-radius: 16px 16px 0 0;
}
.cancel, .save {
  font-size: 16px;
  background: none;
  border: none;
}
.cancel { color: var(--wx-text-tips, #888); }
.save { color: var(--wx-brand, #07c160); font-weight: 600; }
.save:disabled { opacity: 0.5; }
.title {
  font-size: 17px;
  font-weight: 600;
  color: var(--wx-text, #000);
}
.editor-body {
  padding: 8px 0;
  overflow-y: auto;
}
.field {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--wx-bg-white, #fff);
  border-bottom: 0.5px solid var(--wx-line, #e5e5e5);
}
.field-label {
  width: 56px;
  flex-shrink: 0;
  font-size: 16px;
  color: var(--wx-text, #000);
}
.field-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 16px;
  background: transparent;
  color: var(--wx-text, #000);
}
.field-textarea {
  flex: 1;
  border: none;
  outline: none;
  font-size: 16px;
  background: transparent;
  color: var(--wx-text, #000);
  resize: none;
  font-family: inherit;
}
.avatar-field {
  gap: 16px;
}
.avatar-pick {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  flex: 1;
}
.pick-hint {
  font-size: 14px;
  color: var(--wx-text-tips, #888);
}
.clear-avatar {
  font-size: 14px;
  color: #fa5151;
  background: none;
  border: none;
}
.err {
  padding: 8px 16px;
  font-size: 13px;
  color: #fa5151;
}
</style>
