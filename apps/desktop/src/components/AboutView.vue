<script setup lang="ts">
import { getVersion } from "@tauri-apps/api/app";
import { onMounted, ref } from "vue";

const version = ref("0.1.5");

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
      <div><p class="eyebrow">ABOUT &amp; OPEN SOURCE</p><h2>关于时奕教务排课</h2><p>本地优先的中小学教务排课桌面应用。</p></div>
      <span>v{{ version }}</span>
    </div>

    <section class="hero-card about-hero">
      <div><p class="eyebrow">OFFICIAL IDENTITY</p><h2>tech.karios.stt.desktop</h2><p>源代码按 Apache License 2.0 开放；官方名称、图标、安装包和签名发行版另受商标与代码签名政策约束。</p></div>
      <dl><div><dt>首发平台</dt><dd>Windows 10 / 11 x64</dd></div><div><dt>本地算法</dt><dd>Python · OR-Tools</dd></div><div><dt>桌面技术</dt><dd>Tauri 2 · Vue 3</dd></div><div><dt>官方仓库</dt><dd>github.com/DepartureZSH/AcademicAffairsSystemDesk</dd></div></dl>
    </section>

    <div class="about-grid">
      <article class="panel"><p class="eyebrow">PRIVACY</p><h3>教务数据留在本机</h3><p>学校、教师、班级、课程、约束、课表、算法输入输出、导入文件和备份不上传。真实远程服务仅处理账号、许可证、支付、设备风险记录和签名更新。</p><code>PRIVACY.md</code></article>
      <article class="panel"><p class="eyebrow">SECURITY</p><h3>私下报告漏洞</h3><p>请使用 GitHub Private vulnerability reporting 或私有 Security Advisory。公开 issue 不得包含密码、密钥、真实学校资料或可利用细节。</p><code>SECURITY.md</code></article>
      <article class="panel"><p class="eyebrow">SIGNING</p><h3>两套独立签名</h3><p>Windows Authenticode 验证发布者与文件完整性，Tauri updater Ed25519 验证更新字节。测试版自签名；正式版计划使用 SignPath Foundation。</p><code>CODE_SIGNING_POLICY.md</code></article>
      <article class="panel"><p class="eyebrow">TRADEMARKS</p><h3>第三方构建须明确区分</h3><p>修改版需更换名称、图标、标识符、更新端点和签名身份，不得暗示由官方维护者或 SignPath Foundation 审核发布。</p><code>TRADEMARKS.md</code></article>
    </div>

    <article class="panel about-notices"><p class="eyebrow">THIRD-PARTY SOFTWARE</p><h3>依赖与许可证</h3><p>每次发布从 Cargo、npm 和 Python 锁定环境生成完整依赖许可证清单；缺失许可证元数据会阻止合规检查。随包字体为 OFL-1.1 许可的 Noto Sans SC，不分发专有字体。</p><code>THIRD_PARTY_NOTICES.md · LICENSE · NOTICE</code></article>
  </section>
</template>
