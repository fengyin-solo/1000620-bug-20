<template>
  <section class="page" data-module="client">
    <header class="page-head">
      <div>
        <h2>委托单位管理</h2>
        <p class="page-desc">
          维护委托单位：登记、审核、暂停、恢复、终止与资质变更；状态与可操作范围由后端按当前角色统一计算。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记委托单位</button>
        <button class="btn" type="button" @click="exportRows">导出委托单位清单</button>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>单位编码</span>
        <input v-model="filters.keyword" placeholder="按单位编码检索" />
      </label>
      <label class="filter-item">
        <span>单位状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span
              v-if="column === '单位状态'"
              class="badge"
              :class="statusClass(row.单位状态)"
              :title="row.拦截原因 ?? ''"
            >
              {{ row.单位状态 }}
            </span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in row.可用动作 ?? []"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button v-if="store.isAdmin" class="link" type="button" @click="openEdit(row)">变更资料</button>
            <button class="link" type="button" @click="openAudits(row)">变更记录</button>
            <span v-if="!(row.可用动作 ?? []).length && !store.isAdmin" class="muted">仅查看</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无委托单位数据，可先登记委托单位</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条委托单位记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>

    <div v-if="dialog !== 'none'" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <template v-if="dialog === 'create' || dialog === 'edit'">
          <h3>{{ dialog === 'create' ? '登记委托单位' : `变更资料：${form.单位编码}` }}</h3>
          <div class="form-grid">
            <label v-for="field in formFields" :key="field.name" class="field">
              <span>{{ field.label }}<em v-if="field.required">*</em></span>
              <input
                v-model="form[field.name]"
                :type="field.type ?? 'text'"
                :disabled="dialog === 'edit' && field.name === '单位编码'"
                :placeholder="field.placeholder ?? ''"
            /></label>
          </div>
          <p v-if="dialog === 'edit'" class="muted">
            单位编码是历史委托与结算的归属锚点，不允许修改；每次变更都会留存操作记录。
          </p>
          <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
          <footer class="modal-foot">
            <button class="btn primary" type="button" @click="submitForm">提交</button>
            <button class="btn ghost" type="button" @click="closeDialog">取消</button>
          </footer>
        </template>

        <template v-else-if="dialog === 'audits'">
          <h3>变更记录：{{ auditTarget?.单位编码 }} · {{ auditTarget?.单位名称 }}</h3>
          <table class="data-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>动作</th>
                <th>字段</th>
                <th>旧值</th>
                <th>新值</th>
                <th>操作人</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="record in audits" :key="String(record.id)">
                <td>{{ record.操作时间 }}</td>
                <td>{{ record.动作 }}</td>
                <td>{{ record.字段 ?? '—' }}</td>
                <td>{{ record.旧值 ?? '—' }}</td>
                <td>{{ record.新值 ?? '—' }}</td>
                <td>{{ record.操作人 }}（{{ record.操作角色 }}）</td>
              </tr>
              <tr v-if="!audits.length">
                <td colspan="6" class="empty-state">暂无变更记录</td>
              </tr>
            </tbody>
          </table>
          <footer class="modal-foot">
            <button class="btn ghost" type="button" @click="closeDialog">关闭</button>
          </footer>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { fetchJson, request, submit } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, any>

const ENDPOINT = '/api/client'
const columns = ['单位编码', '单位名称', '单位类型', '联系人', '联系电话', '结算方式', '资质编号', '资质有效期至', '单位状态']
const statuses = ['待审核', '合作中', '已暂停', '已终止', '资质过期']
const formFields = [
  { name: '单位编码', label: '单位编码', required: true, placeholder: '如 CLIE-0007' },
  { name: '单位名称', label: '单位名称', required: true },
  { name: '单位类型', label: '单位类型', required: true, placeholder: '生产企业 / 检测机构 / 贸易公司' },
  { name: '联系人', label: '联系人' },
  { name: '联系电话', label: '联系电话' },
  { name: '结算方式', label: '结算方式', placeholder: '月结 / 季结 / 现结' },
  { name: '资质编号', label: '资质编号' },
  { name: '资质有效期至', label: '资质有效期至', type: 'date' },
]

const store = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = reactive({ keyword: '', status: '' })

const dialog = ref<'none' | 'create' | 'edit' | 'audits'>('none')
const dialogError = ref('')
const form = reactive<Record<string, string>>({})
const editingId = ref<number | null>(null)
const audits = ref<Row[]>([])
const auditTarget = ref<Row | null>(null)

function statusClass(status: string) {
  return {
    'badge-green': status === '合作中',
    'badge-blue': status === '待审核',
    'badge-orange': status === '已暂停' || status === '资质过期',
    'badge-gray': status === '已终止',
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  Object.keys(form).forEach((key) => delete form[key])
  dialogError.value = ''
  editingId.value = null
  dialog.value = 'create'
}

function openEdit(row: Row) {
  Object.keys(form).forEach((key) => delete form[key])
  for (const field of formFields) {
    form[field.name] = row[field.name] ?? ''
  }
  dialogError.value = ''
  editingId.value = Number(row.id)
  dialog.value = 'edit'
}

async function openAudits(row: Row) {
  auditTarget.value = row
  dialog.value = 'audits'
  try {
    const payload = await fetchJson<{ items: Row[] }>(`${ENDPOINT}/${row.id}/audits`)
    audits.value = payload.items ?? []
  } catch (error) {
    audits.value = []
    errorMessage.value = error instanceof Error ? error.message : '变更记录读取失败'
  }
}

function closeDialog() {
  dialog.value = 'none'
}

async function submitForm() {
  errorMessage.value = ''
  noticeMessage.value = ''
  dialogError.value = ''
  try {
    if (dialog.value === 'create') {
      const result = await submit(ENDPOINT, { ...form })
      noticeMessage.value = result.message
    } else if (dialog.value === 'edit' && editingId.value !== null) {
      const result = await submit(`${ENDPOINT}/${editingId.value}/update`, { ...form })
      noticeMessage.value = result.message
    }
    closeDialog()
    await reload()
  } catch (error) {
    // 拦截原因留在弹窗里，表单保留已填内容，改完可再次提交。
    dialogError.value = error instanceof Error ? error.message : '提交失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const result = await submit(`${ENDPOINT}/${row.id}/actions`, { action })
    noticeMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '委托单位操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('委托单位列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '委托单位列表读取失败'
  }
}

onMounted(reload)
</script>
