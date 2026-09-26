<template>
  <section class="page" data-module="client">
    <header class="page-head">
      <div>
        <h2>委托单位管理</h2>
        <p class="page-desc">维护委托单位，围绕单位编码、单位名称、单位类型、联系人做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button
          v-if="session.can('client:create')"
          class="btn primary"
          type="button"
          @click="toggleCreate"
        >
          登记委托单位
        </button>
        <button class="btn" type="button" @click="exportRows">导出委托单位清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>单位编码</span>
        <input v-model="keyword" placeholder="按单位编码检索" />
      </label>
      <label class="filter-item">
        <span>单位状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="createVisible" class="form-panel">
      <div class="panel-head">
        <h3 class="panel-title">登记委托单位</h3>
        <button class="link" type="button" @click="toggleCreate">收起</button>
      </div>
      <div class="field-grid">
        <label v-for="field in createFields" :key="field.name" class="field-item">
          <span>{{ field.label }}<template v-if="field.required">（必填）</template></span>
          <input
            v-model="createForm[field.name]"
            :placeholder="field.placeholder ?? `请输入${field.label}`"
          />
        </label>
      </div>
      <div class="panel-actions">
        <button class="btn primary" type="button" @click="submitCreate">提交登记</button>
        <button class="btn ghost" type="button" @click="resetCreateForm">清空</button>
      </div>
    </div>

    <div v-if="detail" class="detail-panel">
      <div class="panel-head">
        <h3 class="panel-title">单位详情：{{ detail['单位编码'] }} · {{ detail['单位名称'] }}</h3>
        <button class="link" type="button" @click="closeDetail">关闭</button>
      </div>
      <div class="field-grid">
        <div v-for="field in detailFields" :key="field" class="field-item">
          <span>{{ field }}</span>
          {{ detail[field] ?? '—' }}
        </div>
        <div class="field-item">
          <span>是否可新委托</span>
          <span class="status-tag" :class="detail['可委托'] ? 'active' : 'blocked'">
            {{ detail['可委托'] ? '可委托' : detail['不可委托原因'] }}
          </span>
        </div>
      </div>

      <template v-if="canEditDetail">
        <h3 class="panel-title">修改档案（留痕）</h3>
        <div class="field-grid">
          <label v-for="field in profileFields" :key="field" class="field-item">
            <span>{{ field }}</span>
            <input v-model="editForm[field]" :placeholder="`请输入${field}`" />
          </label>
        </div>
        <div class="panel-actions">
          <button class="btn primary" type="button" @click="submitProfile">保存档案修改</button>
        </div>
      </template>

      <h3 class="panel-title">变更记录</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in auditColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(audit, index) in detailAudits" :key="index">
            <td v-for="column in auditColumns" :key="column">{{ audit[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!detailAudits.length">
            <td :colspan="auditColumns.length" class="empty-state">暂无变更记录</td>
          </tr>
        </tbody>
      </table>
    </div>

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
              class="status-tag"
              :class="statusClass(row)"
            >
              {{ row[column] ?? '—' }}
            </span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in rowActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!rowActions(row).length" class="muted-text">无可执行动作</span>
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
      <span v-else-if="noticeMessage" class="success-text">{{ noticeMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request, responseError } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>
type Audit = Record<string, string | null>

const ENDPOINT = '/api/client'
const columns = ["单位编码", "单位名称", "单位类型", "联系人", "联系电话", "结算方式", "资质编号", "资质有效期至", "单位状态"]
const statuses = ["待审核", "合作中", "资质过期", "已暂停", "已终止"]
const detailFields = ["单位编码", "单位名称", "单位类型", "联系人", "联系电话", "结算方式", "资质编号", "资质有效期至", "单位状态", "资质状态", "登记人", "登记时间"]
const profileFields = ["联系人", "联系电话", "结算方式", "资质编号", "资质有效期至"]
const auditColumns = ["时间", "操作人", "角色", "动作", "字段", "旧值", "新值", "说明"]
const createFields = [
  { name: '单位编码', label: '单位编码', required: true, placeholder: '如 CLIE-0005' },
  { name: '单位名称', label: '单位名称', required: true },
  { name: '单位类型', label: '单位类型', required: true, placeholder: '企业单位 / 事业单位 / 合作社' },
  { name: '联系人', label: '联系人', required: false },
  { name: '联系电话', label: '联系电话', required: false },
  { name: '结算方式', label: '结算方式', required: false, placeholder: '月结30天 / 季结 / 现结' },
  { name: '资质编号', label: '资质编号', required: false, placeholder: '如 CNAS-L1005' },
  { name: '资质有效期至', label: '资质有效期至', required: false, placeholder: 'YYYY-MM-DD' },
]
// 动作 -> 所需权限、允许发起的状态；与后端 ACTION_RULES 口径一致
const ACTION_PERMISSION: Record<string, string> = { 审核单位: 'client:review', 暂停合作: 'client:suspend', 终止合作: 'client:terminate' }
const ACTION_BY_STATUS: Record<string, string[]> = {
  待审核: ['审核单位'],
  合作中: ['暂停合作', '终止合作'],
  已暂停: ['终止合作'],
  已终止: [],
}

const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const createVisible = ref(false)
const createForm = ref<Record<string, string>>({})

const detail = ref<Row | null>(null)
const editForm = ref<Record<string, string>>({})

const stats = computed(() => [
  { label: '合作单位', value: rows.value.filter((row) => row['单位状态'] === '合作中').length },
  { label: '待审核单位', value: rows.value.filter((row) => row['单位状态'] === '待审核').length },
  { label: '资质过期单位', value: rows.value.filter((row) => row['单位状态'] === '资质过期').length },
])

const detailAudits = computed<Audit[]>(() => {
  const audits = detail.value?.['变更记录']
  return Array.isArray(audits) ? (audits as Audit[]) : []
})

const canEditDetail = computed(
  () => session.can('client:update') && detail.value !== null && detail.value['status'] !== '已终止',
)

function statusClass(row: Row) {
  const status = String(row['单位状态'] ?? '')
  if (status === '合作中') return 'active'
  if (status === '资质过期' || status === '已暂停' || status === '已终止') return 'blocked'
  return ''
}

function rowActions(row: Row): string[] {
  const candidates = ACTION_BY_STATUS[String(row['status'] ?? '')] ?? []
  return candidates.filter((action) => session.can(ACTION_PERMISSION[action]))
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function toggleCreate() {
  createVisible.value = !createVisible.value
  if (createVisible.value) resetCreateForm()
}

function resetCreateForm() {
  createForm.value = {}
}

async function submitCreate() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    if (!response.ok) {
      throw new Error(await responseError(response, '委托单位登记失败'))
    }
    const payload = await response.json()
    if (payload.ok === false) {
      throw new Error(payload.message ?? '委托单位登记失败')
    }
    noticeMessage.value = payload.message ?? '委托单位已登记'
    createVisible.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '委托单位登记失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error(await responseError(response, '委托单位详情读取失败'))
    }
    detail.value = (await response.json()) as Row
    editForm.value = Object.fromEntries(profileFields.map((field) => [field, String(detail.value?.[field] ?? '')]))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '委托单位详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

async function submitProfile() {
  if (!detail.value) return
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${detail.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ values: editForm.value }),
    })
    if (!response.ok) {
      throw new Error(await responseError(response, '档案修改失败'))
    }
    const payload = await response.json()
    if (payload.ok === false) {
      throw new Error(payload.message ?? '档案修改失败')
    }
    noticeMessage.value = payload.message ?? '档案已更新'
    detail.value = payload.entry ?? detail.value
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '档案修改失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error(await responseError(response, '委托单位动作未生效'))
    }
    const payload = await response.json()
    if (payload.ok === false) {
      throw new Error(payload.message ?? '委托单位动作未生效')
    }
    noticeMessage.value = payload.message ?? `委托单位已${action}`
    if (detail.value && detail.value.id === row.id) {
      detail.value = payload.entry ?? detail.value
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '委托单位操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error(await responseError(response, '委托单位列表读取失败'))
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

<style scoped>
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
</style>
