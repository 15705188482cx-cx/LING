import { createRouter, createWebHashHistory } from 'vue-router'

// 4 tab：消息 / 通讯录 / 发现 / 我（真微信结构）
// 朋友圈在"发现"里；视频通话从聊天"+"进入，不当 tab
const routes = [
  { path: '/', redirect: '/chat' },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('@/views/ChatList.vue'),
    meta: { tab: 'chat' },
  },
  {
    path: '/chat/window',
    name: 'chat-window',
    component: () => import('@/views/ChatWindow.vue'),
    meta: { tab: 'chat', hideTabBar: true },
  },
  {
    path: '/preview/chat',
    name: 'preview-chat-window',
    component: () => import('@/views/PreviewChatWindow.vue'),
    meta: { tab: 'chat', hideTabBar: true },
  },
  {
    path: '/contacts',
    name: 'contacts',
    component: () => import('@/views/Contacts.vue'),
    meta: { tab: 'contacts' },
  },
  {
    path: '/contacts/detail',
    name: 'contact-detail',
    component: () => import('@/views/ContactDetail.vue'),
    meta: { tab: 'contacts', hideTabBar: true },
  },
  {
    path: '/discover',
    name: 'discover',
    component: () => import('@/views/Discover.vue'),
    meta: { tab: 'discover' },
  },
  {
    path: '/discover/moments',
    name: 'moments',
    component: () => import('@/views/Moments.vue'),
    meta: { tab: 'discover', hideTabBar: true },
  },
  {
    path: '/discover/moments/compose',
    name: 'compose-moment',
    component: () => import('@/views/ComposeMoment.vue'),
    meta: { tab: 'discover', hideTabBar: true },
  },
  {
    path: '/me',
    name: 'me',
    component: () => import('@/views/Me.vue'),
    meta: { tab: 'me' },
  },
  {
    path: '/me/appearance',
    name: 'appearance-settings',
    component: () => import('@/views/AppearanceSettings.vue'),
    meta: { tab: 'me', hideTabBar: true },
  },
  // 视频通话：从聊天"+"进入，不当 tab
  {
    path: '/video-call',
    name: 'video-call',
    component: () => import('@/views/VideoCall.vue'),
    meta: { tab: 'chat', hideTabBar: true },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
