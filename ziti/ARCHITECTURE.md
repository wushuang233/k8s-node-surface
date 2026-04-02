# Ziti Frontend Architecture

`ziti/` 现在按职责拆成了几层：

- `app.js`
  - 极薄入口，只负责启动 `boot()`
- `js/shared.js`
  - 全局 `refs`、`state`
  - 资源文案、工作台提示
  - 通用工具函数
  - 组合框、config 表单、JSON 同步相关的共享能力
- `js/commands.js`
  - Ziti CLI 预览
  - 删除命令、附加命令、复制命令逻辑
- `js/render.js`
  - 工作台卡片渲染
  - 会话、JWT 面板、统计条、tab 内容渲染
- `js/dialog.js`
  - 新增/编辑弹窗
  - 配置表单和 JSON 双向同步
  - 组合框交互、弹窗内复制按钮
- `js/actions.js`
  - 登录、刷新、保存、删除、重签 JWT
  - 事件绑定和页面启动流程

如果后面继续扩展，建议遵守这几个原则：

- 新的 API 调用优先放到 `actions.js`
- 只负责拼命令预览的逻辑放到 `commands.js`
- 只负责页面输出 HTML 的逻辑放到 `render.js`
- 只负责弹窗交互和表单行为的逻辑放到 `dialog.js`
- 新增通用 helper 再放进 `shared.js`
