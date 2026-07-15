<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useProfileStore } from '@/stores/profile'
import EmotionAvatar from '@/components/EmotionAvatar.vue'
import UiIcon from '@/components/UiIcon.vue'
import { VoiceCallClient, type Emotion } from '@/api/backend'
import { TtsQueue } from '@/utils/ttsQueue'
import { OpusRecorder } from '@/utils/opusRecorder'

// 假视频：5 段预录视频按情绪 crossfade 切换（口型同步待后续）
// 素材放 src/assets/videos/，命名沿用 avatars 同名约定；真人素材同名替换即可
import dailyVideo from '@/assets/videos/daily.mp4'
import flirtVideo from '@/assets/videos/flirt.mp4'
import coaxVideo from '@/assets/videos/coax.mp4'
import anxiousVideo from '@/assets/videos/anxious.mp4'
import coldVideo from '@/assets/videos/cold.mp4'

const EMOTION_VIDEOS: Record<Emotion, string> = {
  '日常': dailyVideo,
  '调情': flirtVideo,
  '撒娇': coaxVideo,
  '焦急': anxiousVideo,
  '冷淡': coldVideo,
}

// V0.3 视频通话：全双工 + VAD 自动断句 + Opus 双向 + 实时打断
// 流程：选择(语音/视频) → 呼叫中(WS连接) → 通话中(持续Opus录音+TTS播放) → 挂断
// WS 连上发 hello(auto) → 收 ready → 持续录音发 Opus 包 → 服务端 VAD 断句
// 她说话时用户开口 → 前端音量检测 → abort + 清 TTS 队列

import micOffIcon from '@/assets/icons/call-mic-off.svg?raw'
import cameraIcon from '@/assets/icons/call-camera.svg?raw'
import flipIcon from '@/assets/icons/call-flip.svg?raw'
import speakerIcon from '@/assets/icons/call-speaker.svg?raw'
import hangupIcon from '@/assets/icons/call-hangup.svg?raw'

const router = useRouter()
const profile = useProfileStore()

type Phase = 'choose' | 'calling' | 'active'
const phase = ref<Phase>('choose')
const callType = ref<'voice' | 'video'>('video')

const localVideo = ref<HTMLVideoElement | null>(null)
const stream = ref<MediaStream | null>(null)
const errorMsg = ref('')
const micOn = ref(true)
const camOn = ref(true)
const speakerOn = ref(true)
const facing = ref<'user' | 'environment'>('user')
const callDuration = ref(0)
let timer: number | null = null

// WS 通话相关
let wsClient: VoiceCallClient | null = null
let opusRec: OpusRecorder | null = null
const ttsQueue = new TtsQueue({
  isActive: () => phase.value === 'active',
  onPlayStart: () => { isSpeaking.value = true },
  onPlayEnd: () => { isSpeaking.value = false },
})
const isSpeaking = ref(false) // 她正在说话（TTS播放中）
const subtitle = ref('') // 字幕：显示她的回复 / 识别结果
const peerEmotion = ref<Emotion>('日常')
let videoFrameTimer: number | null = null

// 双 video crossfade：A/B 两层叠放，情绪变化时新视频设到非活跃层并预加载首帧，
// 再切 activeLayer 触发 CSS opacity 过渡，旧层过渡完暂停。避免单 video 换 src 黑屏跳变。
const videoA = ref<HTMLVideoElement | null>(null)
const videoB = ref<HTMLVideoElement | null>(null)
const activeLayer = ref<'A' | 'B'>('A')
const currentVideoUrl = ref<string>('')

/** 把指定 url 设到某层并预播放（muted 不出声），保证 crossfade 时首帧已就绪。 */
function preloadLayer(layer: 'A' | 'B', url: string): Promise<void> {
  const el = layer === 'A' ? videoA.value : videoB.value
  if (!el) return Promise.resolve()
  el.src = url
  el.load()
  return el.play().then(() => {}, () => {}) // 静默失败：load 失败时该层保持空，文字层正常
}

/** 情绪变化 → 切换视频。同情绪重复下发短路；预加载新层后 nextTick 切 active 触发 crossfade。 */
watch(peerEmotion, (emotion) => {
  const nextUrl = EMOTION_VIDEOS[emotion]
  if (!nextUrl || nextUrl === currentVideoUrl.value) return
  const inactiveLayer = activeLayer.value === 'A' ? 'B' : 'A'
  void preloadLayer(inactiveLayer, nextUrl).then(() => {
    nextTick(() => {
      currentVideoUrl.value = nextUrl
      activeLayer.value = inactiveLayer
    })
  })
})

/** 进入通话时初始化活跃层为当前情绪视频。 */
watch(phase, (p) => {
  if (p === 'active') {
    const url = EMOTION_VIDEOS[peerEmotion.value]
    currentVideoUrl.value = url
    void preloadLayer(activeLayer.value, url)
  }
})

// 前端 VAD 辅助打断：她说话时检测用户开口（音量超阈值）→ abort
let vadAnalyser: AnalyserNode | null = null
let vadCtx: AudioContext | null = null
let vadTimer: number | null = null
let userVoiceDetected = false
const VAD_VOLUME_THRESHOLD = 0.08 // 音量阈值（0-1），超此认为用户开口

// 选择类型 → 进入呼叫（连 WS）
async function startCall(type: 'voice' | 'video') {
  callType.value = type
  phase.value = 'calling'
  errorMsg.value = ''

  const mediaStarted = await startCamera(type === 'video')
  if (!mediaStarted) {
    phase.value = 'choose'
    return
  }

  wsClient = new VoiceCallClient({
    onReady: () => {
      // WS 连上 + ready = "接听"
      phase.value = 'active'
      startDuration()
      // V0.3：auto 模式持续录音，服务端 VAD 自动断句
      startStreamingAudio()
      // 视频模式：定时发摄像头帧
      if (type === 'video') startVideoFrames()
      // 启动前端 VAD 辅助打断检测
      startFrontendVad()
    },
    onAsrText: (text) => {
      subtitle.value = `我: ${text}`
    },
    onLlmChunk: (text) => {
      subtitle.value = `她: ${text}`
    },
    onEmotion: (emotion) => {
      peerEmotion.value = emotion
    },
    onTtsStart: () => {
      isSpeaking.value = true
    },
    // V0.3：逐个 Opus 包入队解码
    onTtsAudio: (opusBytes) => {
      void ttsQueue.enqueueOpus(opusBytes)
    },
    // V0.3：一句 TTS 结束（或被打断）→ 拼包播放 / 清队列
    onTtsStop: (reason) => {
      if (reason === 'aborted') {
        // 被打断：立即清播放队列
        ttsQueue.clear()
        isSpeaking.value = false
      } else {
        // 正常句末：把累积的 Opus 包拼成一句播放
        ttsQueue.flushSentence()
      }
    },
    onDone: (reason) => {
      isSpeaking.value = false
      if (reason === 'closed' || phase.value !== 'active') return
      // 一轮结束，字幕留着显示一会儿
      // auto 模式无需重启录音——录音一直在跑，服务端 VAD 会自动触发下一轮
    },
    onError: (err) => {
      errorMsg.value = err
    },
  })

  try {
    await wsClient.connect()
    // V0.3：握手声明 auto 模式（服务端 VAD 自动断句）
    wsClient.hello('auto', 16000)
  } catch (e) {
    errorMsg.value = '连接失败：' + (e as Error).message
    phase.value = 'choose'
  }
}

function cancelCalling() {
  cleanup()
  phase.value = 'choose'
}

async function startCamera(video = true): Promise<boolean> {
  errorMsg.value = ''
  try {
    // echoCancellation=true 防止 TTS 回采误触发 VAD
    const s = await navigator.mediaDevices.getUserMedia({
      video: video ? { facingMode: facing.value } : false,
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      } as MediaTrackConstraints,
    })
    stream.value = s
    if (video && localVideo.value) localVideo.value.srcObject = s
    return true
  } catch (e) {
    errorMsg.value = (e as Error).message || '无法访问摄像头/麦克风'
    return false
  }
}

/** V0.3：用 OpusRecorder 持续录音，每个 Opus 包直接发 WS（服务端 VAD 自动断句）。 */
async function startStreamingAudio() {
  if (!stream.value || phase.value !== 'active') return
  opusRec = new OpusRecorder({
    onOpusPacket: (pkt) => {
      wsClient?.sendAudio(pkt)
    },
    onError: (err) => {
      console.warn('Opus 录音错误:', err)
    },
  })
  try {
    await opusRec.startFromStream(stream.value)
  } catch (e) {
    console.warn('Opus 录音启动失败:', e)
    errorMsg.value = '录音启动失败'
  }
}

/** 视频模式：每 3 秒抓一帧发后端 VLM */
function startVideoFrames() {
  if (videoFrameTimer) clearInterval(videoFrameTimer)
  videoFrameTimer = window.setInterval(() => {
    if (!camOn.value || !localVideo.value) return
    const video = localVideo.value
    const canvas = document.createElement('canvas')
    canvas.width = 320
    canvas.height = 240
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob(
      (blob) => {
        if (!blob) return
        const reader = new FileReader()
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1] || ''
          wsClient?.sendVideoFrame(base64)
        }
        reader.readAsDataURL(blob)
      },
      'image/jpeg',
      0.7
    )
  }, 3000)
}

/** 前端 VAD 辅助打断：她说话时检测用户开口 → abort + 清 TTS。 */
function startFrontendVad() {
  if (!stream.value) return
  try {
    vadCtx = new AudioContext()
    const source = vadCtx.createMediaStreamSource(stream.value)
    vadAnalyser = vadCtx.createAnalyser()
    vadAnalyser.fftSize = 512
    source.connect(vadAnalyser)
    const data = new Uint8Array(vadAnalyser.frequencyBinCount)
    vadTimer = window.setInterval(() => {
      if (!vadAnalyser || !isSpeaking.value) {
        userVoiceDetected = false
        return
      }
      // 只在她说话时检测用户开口（避免她不说时也监听）
      vadAnalyser.getByteTimeDomainData(data)
      let sum = 0
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128
        sum += v * v
      }
      const rms = Math.sqrt(sum / data.length)
      if (rms > VAD_VOLUME_THRESHOLD) {
        if (!userVoiceDetected) {
          userVoiceDetected = true
          // 用户开口 → 打断她的 TTS
          wsClient?.abort()
          ttsQueue.clear()
          isSpeaking.value = false
        }
      } else {
        userVoiceDetected = false
      }
    }, 100) // 100ms 检测一次
  } catch (e) {
    console.warn('前端 VAD 启动失败:', e)
  }
}

function stopFrontendVad() {
  if (vadTimer) { clearInterval(vadTimer); vadTimer = null }
  if (vadCtx) { void vadCtx.close(); vadCtx = null }
  vadAnalyser = null
  userVoiceDetected = false
}

function startDuration() {
  callDuration.value = 0
  timer = window.setInterval(() => callDuration.value++, 1000)
}

function toggleMic() {
  micOn.value = !micOn.value
  stream.value?.getAudioTracks().forEach((t) => (t.enabled = micOn.value))
}
function toggleCam() {
  camOn.value = !camOn.value
  stream.value?.getVideoTracks().forEach((t) => (t.enabled = camOn.value))
  // V0.3 修复：关闭摄像头时发空帧，清后端 latest_frame，避免 VLM 用旧帧
  if (!camOn.value) {
    wsClient?.sendVideoFrame('')
  }
}
function toggleSpeaker() {
  speakerOn.value = !speakerOn.value
  ttsQueue.setSpeakerOn(speakerOn.value)
}
async function flipCamera() {
  facing.value = facing.value === 'user' ? 'environment' : 'user'
  // V0.3 修复：只切换 video track，保留 audio track（opusRec 绑的是 audio，断了录音就失效）
  const oldVideoTracks = stream.value?.getVideoTracks() ?? []
  try {
    const s = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: facing.value },
      audio: false, // 不重新拿 audio，保留原 audio track
    })
    // 停掉旧 video track，挂上新 video track
    oldVideoTracks.forEach((t) => t.stop())
    const newVideo = s.getVideoTracks()[0]
    if (newVideo && stream.value) {
      oldVideoTracks.forEach((t) => stream.value!.removeTrack(t))
      stream.value.addTrack(newVideo)
      if (localVideo.value) localVideo.value.srcObject = stream.value
    }
  } catch (e) {
    errorMsg.value = (e as Error).message || '翻转摄像头失败'
  }
}
function stopStream() {
  stream.value?.getTracks().forEach((t) => t.stop())
  stream.value = null
}

function hangup() {
  cleanup()
  router.push('/chat/window')
}

function cleanup() {
  if (timer) { clearInterval(timer); timer = null }
  if (videoFrameTimer) { clearInterval(videoFrameTimer); videoFrameTimer = null }
  // V0.3：停止 Opus 录音
  if (opusRec) {
    void opusRec.stop()
    opusRec = null
  }
  stopFrontendVad()
  ttsQueue.clear()
  // V0.3：挂断前补发 abort，让服务端立即停 TTS + 清状态
  wsClient?.abort()
  wsClient?.close()
  wsClient = null
  stopStream()
  isSpeaking.value = false
  subtitle.value = ''
  // 释放预录视频资源，避免挂断后后台继续解码
  ;[videoA.value, videoB.value].forEach((el) => {
    if (el) {
      el.pause()
      el.removeAttribute('src')
      el.load()
    }
  })
  currentVideoUrl.value = ''
}

onBeforeUnmount(() => {
  cleanup()
  ttsQueue.dispose()
})

function fmt(s: number) {
  const m = String(Math.floor(s / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return `${m}:${ss}`
}
</script>

<template>
  <div class="vc">
    <!-- 阶段1：选择语音/视频 -->
    <div v-if="phase === 'choose'" class="phase-choose">
      <div class="choose-avatar">
        <EmotionAvatar :src="profile.avatarUrl" :size="80" />
      </div>
      <div class="choose-name">{{ profile.name }}</div>
      <div class="choose-tip">选择通话方式</div>
      <div class="choose-actions">
        <button class="choose-btn" @click="startCall('voice')">
          <span class="choose-ico"><UiIcon name="phone" :size="28" /></span>
          <span class="choose-label">语音通话</span>
        </button>
        <button class="choose-btn" @click="startCall('video')">
          <span class="choose-ico"><UiIcon name="video" :size="28" /></span>
          <span class="choose-label">视频通话</span>
        </button>
      </div>
      <button class="back-chat" @click="router.push('/chat/window')">返回</button>
    </div>

    <!-- 阶段2：呼叫中 -->
    <div v-else-if="phase === 'calling'" class="phase-calling">
      <EmotionAvatar :src="profile.avatarUrl" :size="96" class="call-avatar" />
      <div class="call-name">{{ profile.name }}</div>
      <div class="call-status">{{ callType === 'voice' ? '语音通话' : '视频通话' }} · 正在呼叫…</div>
      <div class="calling-dots"><span /><span /><span /></div>
      <button class="hangup-floating" @click="cancelCalling">
        <span class="hangup-ico" v-html="hangupIcon" />
      </button>
    </div>

    <!-- 阶段3：通话中 -->
    <template v-else>
      <!-- 主画面 -->
      <div class="main-view">
        <!-- 双 video crossfade 层：情绪变化时新层预加载首帧后 opacity 交叉过渡 -->
        <video ref="videoA" class="peer-video" :class="{ active: activeLayer === 'A' }"
               autoplay loop muted playsinline />
        <video ref="videoB" class="peer-video" :class="{ active: activeLayer === 'B' }"
               autoplay loop muted playsinline />
        <div class="peer-name">{{ profile.name }}</div>
        <div class="call-time">{{ camOn ? fmt(callDuration) : '已关闭摄像头' }}</div>
        <div v-if="isSpeaking" class="speaking-tip">正在说话…</div>
        <div v-if="errorMsg" class="err"><UiIcon name="alert" :size="14" /> {{ errorMsg }}</div>
      </div>

      <!-- 字幕 -->
      <div v-if="subtitle" class="subtitle">{{ subtitle }}</div>

      <!-- 右上小窗（仅视频） -->
      <div v-if="callType === 'video'" class="self-view" :class="{ off: !camOn }">
        <video v-show="camOn" ref="localVideo" autoplay playsinline muted />
        <span v-if="!camOn" class="self-off-tip">摄像头已关</span>
      </div>

      <!-- 控制条 -->
      <footer class="ctrl-bar">
        <button class="ctrl" :class="{ on: micOn }" @click="toggleMic">
          <span class="ctrl-ico" v-html="micOffIcon" />
          <span class="ctrl-label">静音</span>
        </button>
        <button v-if="callType === 'video'" class="ctrl" :class="{ on: camOn }" @click="toggleCam">
          <span class="ctrl-ico" v-html="cameraIcon" />
          <span class="ctrl-label">摄像头</span>
        </button>
        <button v-if="callType === 'video'" class="ctrl" @click="flipCamera">
          <span class="ctrl-ico" v-html="flipIcon" />
          <span class="ctrl-label">翻转</span>
        </button>
        <button class="ctrl" :class="{ on: speakerOn }" @click="toggleSpeaker">
          <span class="ctrl-ico" v-html="speakerIcon" />
          <span class="ctrl-label">扬声器</span>
        </button>
        <button class="ctrl hangup" @click="hangup">
          <span class="ctrl-ico big" v-html="hangupIcon" />
          <span class="ctrl-label">挂断</span>
        </button>
      </footer>
    </template>
  </div>
</template>

<style scoped lang="scss">
.vc {
  position: relative;
  height: 100%;
  background: #1a1a1a;
  overflow: hidden;
  color: #fff;
}

// 阶段1：选择
.phase-choose {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
}
.choose-avatar {
  margin-bottom: 8px;
}
.choose-name {
  font-size: 24px;
  font-weight: 500;
}
.choose-tip {
  font-size: 14px;
  opacity: 0.6;
  margin-bottom: 30px;
}
.choose-actions {
  display: flex;
  gap: 30px;
}
.choose-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--wx-text-white);
}
.choose-ico {
  width: 68px;
  height: 68px;
  border-radius: 50%;
  background: var(--wx-brand);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  box-shadow: var(--wx-shadow-md);
  transition: background var(--wx-duration-fast) var(--wx-ease), transform var(--wx-duration-fast) var(--wx-ease);
  &:active {
    background: var(--wx-brand-press);
    transform: scale(0.95);
  }
}
.choose-label {
  font-size: 13px;
  opacity: 0.85;
}
.back-chat {
  margin-top: 40px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.6);
}

// 阶段2：呼叫中
.phase-calling {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
}
.call-avatar {
  width: 96px;
  height: 96px;
  border-radius: var(--wx-radius-lg);
}
.call-name {
  font-size: 26px;
  font-weight: 500;
}
.call-status {
  font-size: 14px;
  opacity: 0.7;
}
.calling-dots {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  span {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.6);
    animation: dot 1.2s infinite;
    &:nth-child(2) {
      animation-delay: 0.2s;
    }
    &:nth-child(3) {
      animation-delay: 0.4s;
    }
  }
}
@keyframes dot {
  0%, 60%, 100% {
    opacity: 0.3;
  }
  30% {
    opacity: 1;
  }
}
.hangup-floating {
  position: absolute;
  bottom: 60px;
}
.hangup-ico {
  width: 66px;
  height: 66px;
  border-radius: 50%;
  background: var(--wx-danger);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--wx-shadow-md);
  :deep(svg) {
    width: 38px;
    height: 38px;
    color: var(--wx-text-white);
  }
}

// 阶段3：通话中
.main-view {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
}
.peer-video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  z-index: 0;
  transition: opacity 300ms ease-in-out;
  &.active {
    opacity: 1;
  }
}
.peer-name {
  position: relative;
  z-index: 1;
  font-size: 22px;
  font-weight: 500;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
}
.call-time {
  position: relative;
  z-index: 1;
  font-size: 14px;
  opacity: 0.7;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
}
.err {
  position: relative;
  z-index: 1;
  font-size: 13px;
  color: #ff6b6b;
  padding: 0 30px;
  text-align: center;
}
.speaking-tip {
  position: relative;
  z-index: 1;
  font-size: 13px;
  opacity: 0.7;
  animation: dot 1.2s infinite;
}
.subtitle {
  position: absolute;
  bottom: calc(140px + var(--wx-safe-bottom));
  left: 50%;
  transform: translateX(-50%);
  max-width: 80%;
  padding: 10px 16px;
  background: rgba(0, 0, 0, 0.5);
  border-radius: var(--wx-radius-lg);
  font-size: 15px;
  line-height: 1.4;
  text-align: center;
  z-index: 8;
}
.self-view {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 90px;
  height: 130px;
  border-radius: var(--wx-radius-md);
  overflow: hidden;
  background: #333;
  border: 1px solid rgba(255, 255, 255, 0.15);
  z-index: 5;
  box-shadow: var(--wx-shadow-md);
  &.off {
    display: flex;
    align-items: center;
    justify-content: center;
  }
  video {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transform: scaleX(-1);
  }
}
.self-off-tip {
  font-size: 11px;
  opacity: 0.6;
  text-align: center;
  padding: 4px;
}

// 控制条
.ctrl-bar {
  position: absolute;
  bottom: calc(48px + var(--wx-safe-bottom));
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-around;
  align-items: flex-start;
  padding: 0 12px;
  z-index: 10;
}
.ctrl {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--wx-text-white);
  .ctrl-ico {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.32);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background var(--wx-duration-fast) var(--wx-ease);
    :deep(svg) {
      width: 30px;
      height: 30px;
      color: var(--wx-text-white);
    }
    &.big {
      width: 66px;
      height: 66px;
      :deep(svg) {
        width: 38px;
        height: 38px;
      }
    }
  }
  &.on .ctrl-ico {
    background: var(--wx-bg-white);
    :deep(svg) {
      color: #000;
    }
  }
  &.hangup .ctrl-ico {
    background: var(--wx-danger);
    :deep(svg) {
      color: var(--wx-text-white);
    }
  }
}
.ctrl-label {
  font-size: 11px;
  opacity: 0.9;
}
</style>
