<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import PhoneFrame from '@/components/PhoneFrame.vue'
import TabBar from '@/components/TabBar.vue'
import { useProfileStore } from '@/stores/profile'
import { usePresentationStore } from '@/stores/presentation'

const route = useRoute()
// ChatWindow / VideoCall 是全屏子页面，隐藏底栏
const showTabBar = computed(() => !route.meta.hideTabBar)

// 启动时拉取个人资料（名字/头像/签名），各页面读 store 显示
const profile = useProfileStore()
const presentation = usePresentationStore()
onMounted(() => {
  if (!presentation.staticPreview) void profile.load()
})
</script>

<template>
  <PhoneFrame>
    <div class="app-shell">
      <main class="app-main">
        <RouterView v-slot="{ Component }">
          <KeepAlive :include="['ChatList', 'Contacts', 'Settings']">
            <component :is="Component" />
          </KeepAlive>
        </RouterView>
      </main>
      <TabBar v-if="showTabBar" />
    </div>
  </PhoneFrame>
</template>

<style scoped lang="scss">
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.app-main {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
