import { defineStore } from 'pinia'

export type Role = '管理员' | '业务员'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: '管理员' as Role,
    shiftLabel: '白班 08:00-20:00',
    scope: '实验室样品检测平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    isAdmin: (state) => state.role === '管理员',
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: Role) {
      this.role = role
      this.operator = role === '管理员' ? '值班管理员' : '业务员小李'
    },
  },
})
