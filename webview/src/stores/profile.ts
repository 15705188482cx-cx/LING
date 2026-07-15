import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/backend'
import type { Profile } from '@/api/backend'
import dailyAvatar from '@/assets/avatars/daily.svg'

// 个人资料 store：名字/头像/签名，从后端 /profile 拉取，编辑后 PUT 回写。
// 头像优先用后端存的 base64，空则回退默认 svg。
export const useProfileStore = defineStore('profile', () => {
  const name = ref('刘嘉玲')
  const signature = ref('在呢宝贝，怎么了')
  const avatar = ref('')  // base64 data URL，空=用默认头像
  const loaded = ref(false)

  /** 头像 URL：有自定义用自定义，否则默认 svg */
  const avatarUrl = computed(() => avatar.value || dailyAvatar)

  /** 启动时拉取 profile（App.vue onMounted 调） */
  async function load() {
    try {
      const p: Profile = await api.getProfile()
      name.value = p.name
      signature.value = p.signature
      avatar.value = p.avatar
    } catch (e) {
      console.warn('profile 拉取失败，用默认值:', e)
    } finally {
      loaded.value = true
    }
  }

  /** 更新资料（只传要改的字段），成功后同步本地 */
  async function update(partial: Partial<Profile>) {
    const res = await api.updateProfile(partial)
    name.value = res.profile.name
    signature.value = res.profile.signature
    avatar.value = res.profile.avatar
  }

  return { name, signature, avatar, avatarUrl, loaded, load, update }
})
