import { defineStore } from 'pinia'

export const ROLE_OPTIONS = ['管理员', '业务员', '审核员', '检测员']

/** 与后端 app/services/permission.py 的 ROLE_PERMISSIONS 保持一致：
 *  前端只决定「看得见什么、点得动什么」，后端仍是最终拦截口径。 */
const ROLE_PERMISSIONS: Record<string, string[]> = {
  业务员: ['client:create', 'sample:create', 'settlement:create'],
  审核员: ['client:review'],
  管理员: [
    'client:create',
    'client:review',
    'client:suspend',
    'client:terminate',
    'client:update',
    'sample:create',
    'settlement:create',
  ],
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: '管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '实验室样品检测平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    permissions: (state) => ROLE_PERMISSIONS[state.role] ?? [],
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: string) {
      this.role = role
    },
    can(permission: string) {
      return this.permissions.includes(permission)
    },
  },
})
