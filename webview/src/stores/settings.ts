import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

function load<T>(key: string, fallback: T): T {
  const value = localStorage.getItem(`ling:${key}`)
  return value === null ? fallback : JSON.parse(value) as T
}

function save<T>(key: string, value: T): void {
  localStorage.setItem(`ling:${key}`, JSON.stringify(value))
}

export const useSettingsStore = defineStore('settings', () => {
  const autoTts = ref(load('autoTts', true))
  const fontScale = ref(load('fontScale', 1))
  // 保留旧设置页的兼容字段；界面主题固定为浅色，值不会影响 CSS。
  const theme = ref<'auto' | 'light' | 'dark'>('light')

  watch(autoTts, (value) => save('autoTts', value))
  watch(fontScale, (value) => {
    save('fontScale', value)
    document.documentElement.style.fontSize = `${16 * value}px`
  })

  document.documentElement.style.fontSize = `${16 * fontScale.value}px`
  document.documentElement.setAttribute('data-weui-theme', 'light')

  return { autoTts, fontScale, theme }
})
