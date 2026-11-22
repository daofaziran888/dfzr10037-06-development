import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'
import GovernDashView from '@/views/GovernDashView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 治理看板需要分层指标与回执核对，单独走专用页面；其余模块仍用共享工作台。
    { path: '/govern_dash', name: 'govern_dash', component: GovernDashView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
