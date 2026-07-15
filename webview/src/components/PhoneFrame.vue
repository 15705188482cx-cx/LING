<script setup lang="ts">
// 移动端外框：桌面浏览时居中显示一个 375px 宽的手机框；
// 真机/窄屏直接铺满。模拟微信在手机上的观感。
</script>

<template>
  <div class="phone-frame">
    <div class="phone-screen">
      <slot />
    </div>
  </div>
</template>

<style scoped lang="scss">
.phone-frame {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.phone-screen {
  position: relative;
  width: 100%;
  height: 100%;
  max-width: 414px; // iPhone Plus 宽度，桌面端收窄成手机框
  background: var(--wx-bg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

// 桌面端：外框加圆角阴影，模拟手机。用 aspect-ratio 锁定 9:19.5 手机比例，
// 高度优先（85vh），宽度由比例算出，避免矮屏变方框
@media (min-width: 480px) {
  .phone-frame {
    padding: 20px;
  }
  .phone-screen {
    height: min(85vh, 844px);
    width: auto;
    aspect-ratio: 9 / 19.5;
    border-radius: 40px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
    border: 8px solid #1a1a1a;
  }
}
</style>
