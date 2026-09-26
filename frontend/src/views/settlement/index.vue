<template>
  <section class="page" data-module="settlement">
    <header class="page-head">
      <div>
        <h2>检测结算管理</h2>
        <p class="page-desc">
          维护结算单：新开结算单必须归属到名册内的委托单位；已收款的记录封存，不允许再改动。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记结算单</button>
        <button class="btn" type="button" @click="exportRows">导出检测结算清单</button>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>结算单号</span>
        <input v-model="filters.keyword" placeholder="按结算单号检索" />
      </label>
      <label class="filter-item">
        <span>结算状态</span>
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
            <span v-if="!(row.可用动作 ?? []).length" class="muted">已封存</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无检测结算数据，可先登记结算单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条检测结算记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>

    <div v-if="dialog === 'create'" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <h3>登记结算单</h3>
        <div class="form-grid">
          <label class="field"><span>结算单号<em>*</em></span><input v-model="form.结算单号" placeholder="如 SETT-9001" /></label>
          <label class="field"><span>委托单位<em>*</em></span><input v-model="form.委托单位" placeholder="单位编码或单位名称" /></label>
          <label class="field"><span>结算周期<em>*</em></span><input v-model="form.结算周期" placeholder="如 2026-09" /></label>
          <label class="field"><span>检测项数</span><input v-model="form.检测项数" /></label>
          <label class="field"><span>应收金额</span><input v-model="form.应收金额" /></label>
          <label class="field"><span>已收金额</span><input v-model="form.已收金额" /></label>
        </div>
        <p class="muted">已终止合作的单位不能新开结算单；历史结算记录收款后封存，不允许再改动。</p>
        <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
        <footer class="modal-foot">
          <button class="btn primary" type="button" @click="submitForm">提交</button>
          <button class="btn ghost" type="button" @click="closeDialog">取消</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request, submit } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/settlement'
const columns = ['结算单号', '委托单位', '结算周期', '检测项数', '应收金额', '已收金额', '开票状态', '结算状态']
const statuses = ['待核对', '核对中', '已确认', '已收款', '有争议']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = reactive({ keyword: '', status: '' })

const dialog = ref<'none' | 'create'>('none')
const dialogError = ref('')
const form = reactive<Record<string, string>>({})

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
  dialog.value = 'create'
}

function closeDialog() {
  dialog.value = 'none'
}

async function submitForm() {
  errorMessage.value = ''
  noticeMessage.value = ''
  dialogError.value = ''
  try {
    const result = await submit(ENDPOINT, { ...form })
    noticeMessage.value = result.message
    closeDialog()
    await reload()
  } catch (error) {
    // 拦截原因留在弹窗里，表单保留已填内容，改完可再次提交。
    dialogError.value = error instanceof Error ? error.message : '登记失败'
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
    errorMessage.value = error instanceof Error ? error.message : '检测结算操作失败'
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
      throw new Error('结算单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '结算单列表读取失败'
  }
}

onMounted(reload)
</script>
