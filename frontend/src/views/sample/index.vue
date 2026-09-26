<template>
  <section class="page" data-module="sample">
    <header class="page-head">
      <div>
        <h2>样品受理管理</h2>
        <p class="page-desc">
          登记样品即登记新的检测委托：送检单位必须在委托单位名册内、合作中且资质在有效期内，否则会被拦下并说明原因。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记样品</button>
        <button class="btn" type="button" @click="exportRows">导出样品受理清单</button>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>样品编号</span>
        <input v-model="filters.keyword" placeholder="按样品编号检索" />
      </label>
      <label class="filter-item">
        <span>样品状态</span>
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
            <span v-if="!(row.可用动作 ?? []).length" class="muted">已归档</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无样品受理数据，可先登记样品</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条样品受理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>

    <div v-if="dialog === 'create'" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <h3>登记样品（新检测委托）</h3>
        <div class="form-grid">
          <label class="field"><span>样品编号<em>*</em></span><input v-model="form.样品编号" placeholder="如 SAMP-9001" /></label>
          <label class="field"><span>样品名称<em>*</em></span><input v-model="form.样品名称" /></label>
          <label class="field"><span>样品类别<em>*</em></span><input v-model="form.样品类别" placeholder="水质 / 固体 / 气体" /></label>
          <label class="field"><span>单位编码<em>*</em></span><input v-model="form.单位编码" placeholder="委托单位名册中的单位编码" /></label>
          <label class="field"><span>送检人</span><input v-model="form.送检人" /></label>
          <label class="field"><span>接收日期</span><input v-model="form.接收日期" type="date" /></label>
          <label class="field"><span>保存条件</span><input v-model="form.保存条件" /></label>
        </div>
        <p class="muted">已暂停、已终止或资质过期的单位不能登记新委托，提交时会按单位编码校验并说明原因。</p>
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

const ENDPOINT = '/api/sample'
const columns = ['样品编号', '样品名称', '样品类别', '单位编码', '送检单位', '送检人', '接收日期', '保存条件', '样品状态']
const statuses = ['待受理', '已受理', '已分发', '已退回']

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
    errorMessage.value = error instanceof Error ? error.message : '样品受理操作失败'
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
      throw new Error('样品列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '样品受理列表读取失败'
  }
}

onMounted(reload)
</script>
