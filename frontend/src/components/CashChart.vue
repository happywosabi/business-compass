<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { use, init, type ECharts, type EChartsCoreOption } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { StoreEvaluation, ScenarioResult } from '@/api/evaluations'
import { money, monthLabel } from '@/utils/finance'
use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  CanvasRenderer,
])
const props = defineProps<{ results: StoreEvaluation['results']; preview?: ScenarioResult }>()
const host = ref<HTMLElement>()
let chart: ECharts | undefined, observer: ResizeObserver | undefined
const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
function draw() {
  if (!chart) return
  const style = getComputedStyle(document.documentElement)
  const color = (key: string) => style.getPropertyValue(key).trim()
  const base = props.results.scenarios.base
  const options: EChartsCoreOption = {
    animation: !motion.matches,
    animationDuration: 1100,
    animationDurationUpdate: 400,
    color: [color('--faint'), color('--ink'), color('--accent'), color('--good')],
    textStyle: { fontFamily: style.getPropertyValue('--font-cn') },
    grid: { left: 48, right: 18, bottom: 66, top: 32 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: number) => `${money(value)} 元`,
      confine: true,
    },
    legend: {
      bottom: 0,
      itemWidth: 18,
      itemHeight: 2,
      textStyle: { color: color('--muted'), fontSize: 11 },
    },
    xAxis: {
      type: 'category',
      data: base.monthly.map((m) => m.t),
      boundaryGap: false,
      axisLabel: {
        color: color('--muted'),
        formatter: (v: string) => (v === '0' ? '开业' : `${v}月`),
        interval: 5,
      },
      axisLine: { lineStyle: { color: color('--line') } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '万元',
      nameTextStyle: { color: color('--muted') },
      axisLabel: { color: color('--muted'), formatter: (v: number) => money(v / 10000, 1) },
      splitLine: { lineStyle: { color: color('--line-soft'), type: 'dashed' } },
    },
    series: (['pessimistic', 'base', 'optimistic'] as const)
      .map((key, i) => ({
        name: ['悲观', '中性', '乐观'][i],
        type: 'line',
        showSymbol: false,
        smooth: false,
        data: props.results.scenarios[key].monthly.map((m) => m.cash),
        lineStyle: { width: key === 'base' ? 3 : 1.5, type: key === 'base' ? 'solid' : 'dashed' },
        ...(key === 'base'
          ? {
              markLine: {
                symbol: 'none',
                silent: true,
                label: {
                  position: 'insideEndTop',
                  formatter: '收回投入线',
                  fontSize: 11,
                  color: color('--accent-ink'),
                },
                lineStyle: { color: color('--accent'), type: 'dotted' },
                data: [{ yAxis: -base.startup.recoverable }],
              },
              markPoint: {
                symbolSize: 10,
                label: { show: false },
                tooltip: { formatter: (p: { name: string }) => p.name },
                data: [
                  ...(base.cash_low
                    ? [
                        {
                          name: `${monthLabel(base.cash_low.month)}，现金最低 ${money(base.cash_low.amount)} 元`,
                          coord: [base.cash_low.month, base.cash_low.amount],
                          itemStyle: { color: color('--bad') },
                        },
                      ]
                    : []),
                  ...(base.payback_month !== null && base.payback_month <= 36
                    ? [
                        {
                          name: `第 ${base.payback_month} 个月回本`,
                          coord: [base.payback_month, base.monthly[base.payback_month]!.cash],
                          itemStyle: { color: color('--accent') },
                        },
                      ]
                    : []),
                ],
              },
            }
          : {}),
      }))
      .concat(
        props.preview
          ? [
              {
                name: '试算',
                type: 'line',
                showSymbol: false,
                smooth: false,
                data: props.preview.monthly.map((m) => m.cash),
                lineStyle: { width: 2, type: 'solid' },
              },
            ]
          : [],
      ),
  }
  chart.setOption(options, { notMerge: true })
}
onMounted(() => {
  chart = init(host.value!)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(host.value!)
  draw()
  motion.addEventListener('change', draw)
})
watch(() => [props.results, props.preview], draw)
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  motion.removeEventListener('change', draw)
})
</script>
<template>
  <div
    ref="host"
    class="cash-chart"
    role="img"
    aria-label="三种情景下，开业前至第 36 个月的现金曲线；精确数据可在下方逐月明细查看"
  />
</template>
<style scoped>
.cash-chart {
  width: 100%;
  height: 330px;
}
@media (max-width: 767px) {
  .cash-chart {
    height: 290px;
  }
}
</style>
