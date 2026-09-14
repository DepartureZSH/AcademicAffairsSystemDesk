<script setup lang="ts">
import { getVersion } from "@tauri-apps/api/app";
import { onMounted, ref } from "vue";

const version = ref("0.2.5");

onMounted(async () => {
  try {
    version.value = await getVersion();
  } catch {
    // Browser-only previews do not expose the Tauri application API.
  }
});
</script>

<template>
  <section class="module-view about-view">
    <div class="module-heading">
      <div><p class="eyebrow">软件信息</p><h2>时奕教务排课</h2><p>与网页版使用相同流程的本地桌面版。</p></div>
      <span>v{{ version }}</span>
    </div>

    <div class="about-simple-grid">
      <article class="panel"><h3>教务数据保存在本机</h3><p>普通排课在本地完成；主动使用 AI 时，相关内容会发送至你配置的 AI 服务，请先阅读 AI 页面的数据提示。请定期在“数据备份”中创建备份。</p></article>
      <article class="panel"><h3>适用于 Windows 10 / 11</h3><p>桌面版会自动保存项目内容，关闭软件后再次打开即可继续。</p></article>
      <article class="panel"><h3>遇到问题</h3><p>请记录出现问题前的操作和提示内容，再联系时奕教务技术支持。</p></article>
    </div>

    <details class="panel advanced-details about-notices">
      <summary>开源许可与技术信息</summary>
      <p>本软件源代码采用 Apache-2.0 许可证开放。官方名称、图标和发行包受商标与发布政策保护。</p>
      <p>项目标识：tech.karios.stt.desktop</p>
      <p>源代码：github.com/DepartureZSH/AcademicAffairsSystemDesk</p>
    </details>
  </section>
</template>
