import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_PREFIX = 'ling:presentation:'
const DEFAULT_SELF_NAME = '我'
const DEFAULT_LING_NAME = '刘嘉玲'

function readString(key: string, fallback: string): string {
  return localStorage.getItem(STORAGE_PREFIX + key) ?? fallback
}

function readBoolean(key: string, fallback: boolean): boolean {
  const value = localStorage.getItem(STORAGE_PREFIX + key)
  return value === null ? fallback : value === 'true'
}

export const usePresentationStore = defineStore('presentation', () => {
  const staticPreview = ref(readBoolean('static-preview', true))
  const selfName = ref(readString('self-name', DEFAULT_SELF_NAME))
  const selfAvatar = ref(readString('self-avatar', ''))
  const lingName = ref(readString('ling-name', DEFAULT_LING_NAME))
  const lingAvatar = ref(readString('ling-avatar', ''))
  const momentsCover = ref(readString('moments-cover', ''))

  const selfAvatarLabel = computed(() => selfName.value.trim().slice(0, 1) || DEFAULT_SELF_NAME)
  const lingAvatarLabel = computed(() => lingName.value.trim().slice(0, 1) || DEFAULT_LING_NAME)

  watch(staticPreview, (value) => {
    localStorage.setItem(STORAGE_PREFIX + 'static-preview', String(value))
  })
  watch(selfName, (value) => {
    localStorage.setItem(STORAGE_PREFIX + 'self-name', value)
  })
  watch(selfAvatar, (value) => {
    localStorage.setItem(STORAGE_PREFIX + 'self-avatar', value)
  })
  watch(lingName, (value) => {
    localStorage.setItem(STORAGE_PREFIX + 'ling-name', value)
  })
  watch(lingAvatar, (value) => {
    localStorage.setItem(STORAGE_PREFIX + 'ling-avatar', value)
  })
  watch(momentsCover, (value) => {
    localStorage.setItem(STORAGE_PREFIX + 'moments-cover', value)
  })

  function updateSelfProfile(name: string, avatar: string): void {
    const normalizedName = name.trim()
    if (!normalizedName) {
      throw new Error('展示名称不能为空')
    }
    selfName.value = normalizedName
    selfAvatar.value = avatar
  }

  function updateMomentsCover(cover: string): void {
    momentsCover.value = cover
  }

  function updateLingProfile(name: string, avatar: string): void {
    const normalizedName = name.trim()
    if (!normalizedName) {
      throw new Error('Ling 的展示名称不能为空')
    }
    lingName.value = normalizedName
    lingAvatar.value = avatar
  }

  return {
    staticPreview,
    selfName,
    selfAvatar,
    selfAvatarLabel,
    lingName,
    lingAvatar,
    lingAvatarLabel,
    momentsCover,
    updateSelfProfile,
    updateMomentsCover,
    updateLingProfile,
  }
})
