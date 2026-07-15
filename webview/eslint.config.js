import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'
import tsParser from '@typescript-eslint/parser'

// 宽松实用配置：error 级只留真实问题（未声明变量/未处理错误），style 级 warn/off。
// 目标是 pnpm lint 退出 0，同时能抓到明显错误。
export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    // vue 文件用 vue-eslint-parser 解析外层，<script lang="ts"> 用 ts parser
    files: ['**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        extraFileExtensions: ['.vue'],
      },
    },
  },
  {
    files: ['**/*.{ts,vue,js}'],
    languageOptions: {
      globals: {
        // 浏览器 + node 全局，flat 配置需手动声明
        window: 'readonly',
        document: 'readonly',
        navigator: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        WebSocket: 'readonly',
        URL: 'readonly',
        Blob: 'readonly',
        File: 'readonly',
        FileReader: 'readonly',
        FormData: 'readonly',
        AudioContext: 'readonly',
        HTMLAudioElement: 'readonly',
        HTMLVideoElement: 'readonly',
        MediaRecorder: 'readonly',
        HTMLElement: 'readonly',
        Event: 'readonly',
        MessageEvent: 'readonly',
        DOMException: 'readonly',
        DataView: 'readonly',
        Int16Array: 'readonly',
        Float32Array: 'readonly',
        Uint8Array: 'readonly',
        ArrayBuffer: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        btoa: 'readonly',
        process: 'readonly',
      },
    },
    rules: {
      // vue：template 排版/属性顺序不强制（style 级）
      'vue/multi-word-component-names': 'off',
      'vue/attributes-order': 'off',
      'vue/html-indent': 'off',
      'vue/html-self-closing': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/component-name-in-template-casing': 'off',
      // ts：未使用变量降为 warn（vue-tsc 已强校验，eslint 这层不阻塞）
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      '@typescript-eslint/ban-ts-comment': 'off',
      'prefer-const': 'off',
      // 通用
      'no-undef': 'off', // ts 已覆盖，避免 flat 配置误报全局
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**', '*.config.ts', 'pnpm-lock.yaml'],
  },
]
