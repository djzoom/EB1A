// 分享只传可验证的计算条件；片段不会随 HTTP 请求发送到服务器。
function parseDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return year >= 1990 && year <= 2099 && date.getFullYear() === year &&
    date.getMonth() === month - 1 && date.getDate() === day ? date.getTime() : null
}

function parse(hash, categories, countries) {
  const values = new URLSearchParams(hash.replace(/^#/, ''))
  if (values.get('share') !== '1') return null
  if (hash.length > 5000) return { invalid: true }
  const category = values.get('category')
  const country = values.get('country') || 'CN'
  const pd = parseDate(values.get('pd'))
  if (!categories.includes(category) || !countries.includes(country) || pd === null) return { invalid: true }
  let params = null
  try {
    params = values.has('params') ? JSON.parse(values.get('params')) : null
  } catch { return { invalid: true } }
  if (params !== null && (typeof params !== 'object' || Array.isArray(params))) return { invalid: true }
  return {
    profile: { pd, category, country, path: 'AOS', family: 0, chartType: 'A' },
    view: values.get('view') === 'B' ? 'B' : 'A',
    pace: values.get('pace') === 'recent' ? 'recent' : 'model',
    scenario: ['normal', 'tight', 'surge'].includes(values.get('supply')) ? values.get('supply') : null,
    percentile: ['p10', 'p50', 'p90'].includes(values.get('percentile')) ? values.get('percentile') : 'p50',
    params
  }
}

function build(locationHref, state) {
  const source = new URL(locationHref)
  const url = new URL(/^https?:$/.test(source.protocol) ? source.origin + source.pathname : 'https://gc.bracketboss2026.com/')
  const values = new URLSearchParams({ share: '1', category: state.category, country: state.country,
    pd: state.pd, view: state.view, pace: state.pace, percentile: state.percentile })
  if (state.supply) values.set('supply', state.supply)
  if (state.params) values.set('params', JSON.stringify(state.params))
  if (state.lang) values.set('lang', state.lang)
  url.hash = values.toString()
  return url.href
}

window.GCShare = { parse, build, parseDate }
