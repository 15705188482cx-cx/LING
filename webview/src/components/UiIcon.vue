<script setup lang="ts">
// UiIcon —— 统一图标入口，内部映射到 @lucide/vue 矢量图标。
// 全项目图标风格统一到 lucide 设计语言（stroke 线性，24×24，默认 currentColor）。
// 调用方零改动：仍 <UiIcon name="back" :size="24" />。
import {
  ChevronLeft, MoreHorizontal, Plus, Search, Smile, Mic, Keyboard,
  Image as ImageIcon, Camera, Video, MapPin, FileText, Aperture, ScanLine,
  Headphones, Star, BookOpen, Heart, MessageCircle,
  Pin, BellOff, Users, Tag, Megaphone, Building2, Layers,
  Phone, AlertTriangle, Volume2, VolumeX, X, Sticker,
} from '@lucide/vue'
import type { Component } from 'vue'

type IconName =
  | 'back' | 'more' | 'plus' | 'search' | 'smile' | 'mic' | 'keyboard'
  | 'photo' | 'camera' | 'video' | 'location' | 'file' | 'moments' | 'scan'
  | 'service' | 'star' | 'album' | 'heart' | 'heart-filled' | 'comment'
  // 新增（原 emoji 语义）
  | 'pin' | 'bell-off' | 'image' | 'users' | 'tag' | 'megaphone' | 'building'
  | 'layers' | 'phone' | 'alert' | 'volume' | 'volume-off' | 'x' | 'sticker'

const props = withDefaults(defineProps<{
  name: IconName
  size?: number
  stroke?: number
}>(), {
  size: 24,
  stroke: 2,
})

// name → lucide 组件映射表
const iconMap: Record<IconName, Component> = {
  back: ChevronLeft,
  more: MoreHorizontal,
  plus: Plus,
  search: Search,
  smile: Smile,
  mic: Mic,
  keyboard: Keyboard,
  photo: ImageIcon,
  camera: Camera,
  video: Video,
  location: MapPin,
  file: FileText,
  moments: Aperture,
  scan: ScanLine,
  service: Headphones,
  star: Star,
  album: BookOpen,
  heart: Heart,
  'heart-filled': Heart, // 实心：靠下方 fill override 切换
  comment: MessageCircle,
  pin: Pin,
  'bell-off': BellOff,
  image: ImageIcon,
  users: Users,
  tag: Tag,
  megaphone: Megaphone,
  building: Building2,
  layers: Layers,
  phone: Phone,
  alert: AlertTriangle,
  volume: Volume2,
  'volume-off': VolumeX,
  x: X,
  sticker: Sticker,
}

const cmp = iconMap[props.name]
// heart-filled：lucide Heart 默认 stroke 空心，实心版靠 fill override 切换
const isFilled = props.name === 'heart-filled'
</script>

<template>
  <component
    :is="cmp"
    :size="size"
    :stroke-width="isFilled ? 0 : stroke"
    :fill="isFilled ? 'currentColor' : 'none'"
    aria-hidden="true"
  />
</template>

<style scoped>
.ui-icon { display: block; flex: 0 0 auto; }
</style>
