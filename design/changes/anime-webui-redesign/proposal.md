# Proposal: anime-webui-redesign

## Why

The project needs a requirements-driven reusable DESIGN.md before implementation.

## Problem

重做 wxc（微信小程序网课下载器）的本地单页 Web 界面：把现有深色灰板的 static/index.html 改成日式二次元风格，使用用户提供的 3840x2160 动漫插画作为整页背景，中文界面、桌面优先。约束：FastAPI 直接返回 static/index.html，无构建步骤、无外部字体/CDN/依赖；现有 DOM id、/api/* 契约、轮询逻辑与全部功能按钮不变；信息密度保持运维工具级别（抓包状态、条目表、进度、批量下载），不做营销式 hero。产品主线四步：安装 CA 证书 → 开启系统代理 → 在微信 PC 端播放几秒网课 → 回来下载成 mp4。验收：背景插画可见但不影响表格可读性与对比度，四步流程一眼可循，键盘可达，prefers-reduced-motion 有回退，1440x900 与窄屏都不重叠不裁字。

## Safety

Reference sites and templates are attributed evidence, not product authority or copy targets.
