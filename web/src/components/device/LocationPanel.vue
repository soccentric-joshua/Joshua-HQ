<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import type { DeviceLocation } from '@/lib/types'
import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import Table from '@/components/ui/Table.vue'

const props = defineProps<{ deviceId: string }>()
const latest = ref<DeviceLocation | null>(null)
const history = ref<DeviceLocation[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [l, h] = await Promise.all([
      api.location.latest(props.deviceId).catch(() => null),
      api.location.history(props.deviceId),
    ])
    latest.value = l
    history.value = h.items
  } catch {
    error.value = 'Could not load location data.'
  } finally {
    loading.value = false
  }
}

function mapLink(lat: number, lon: number): string {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=15/${lat}/${lon}`
}

watch(() => props.deviceId, load)
onMounted(load)
</script>

<template>
  <div v-if="loading" class="text-sm text-muted-foreground">Loading…</div>
  <Card v-else-if="error" class="p-6 text-sm text-danger">{{ error }}</Card>
  <div v-else class="space-y-6">
    <Card class="p-4">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-semibold">Latest position</h3>
          <p v-if="latest" class="mt-1 text-sm text-muted-foreground">
            Captured {{ new Date(latest.captured_at).toLocaleString() }}
          </p>
        </div>
        <Badge v-if="latest" tone="accent">{{ latest.source ?? 'unknown source' }}</Badge>
      </div>
      <div v-if="latest" class="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <div class="text-muted-foreground">Latitude</div>
          <div class="mt-1 font-mono">{{ latest.latitude.toFixed(6) }}</div>
        </div>
        <div>
          <div class="text-muted-foreground">Longitude</div>
          <div class="mt-1 font-mono">{{ latest.longitude.toFixed(6) }}</div>
        </div>
        <div>
          <div class="text-muted-foreground">Accuracy</div>
          <div class="mt-1">
            {{ latest.accuracy_m != null ? `${latest.accuracy_m.toFixed(0)} m` : '—' }}
          </div>
        </div>
        <div>
          <div class="text-muted-foreground">Altitude</div>
          <div class="mt-1">
            {{ latest.altitude_m != null ? `${latest.altitude_m.toFixed(0)} m` : '—' }}
          </div>
        </div>
      </div>
      <a
        v-if="latest"
        :href="mapLink(latest.latitude, latest.longitude)"
        target="_blank"
        rel="noopener"
        class="mt-3 inline-block text-sm text-accent hover:underline"
        >Open in map</a
      >
    </Card>

    <Card v-if="history.length === 0" class="p-6 text-sm text-muted-foreground">
      No location fixes recorded yet.
    </Card>
    <Table v-else>
      <thead class="border-b border-border bg-surface-muted text-xs uppercase text-muted-foreground">
        <tr>
          <th class="px-4 py-2 font-medium">Captured</th>
          <th class="px-4 py-2 font-medium">Latitude</th>
          <th class="px-4 py-2 font-medium">Longitude</th>
          <th class="px-4 py-2 font-medium">Accuracy</th>
          <th class="px-4 py-2 font-medium">Source</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in history" :key="p.id" class="border-b border-border last:border-0">
          <td class="px-4 py-2">{{ new Date(p.captured_at).toLocaleString() }}</td>
          <td class="px-4 py-2 font-mono">{{ p.latitude.toFixed(6) }}</td>
          <td class="px-4 py-2 font-mono">{{ p.longitude.toFixed(6) }}</td>
          <td class="px-4 py-2 text-muted-foreground">
            {{ p.accuracy_m != null ? `${p.accuracy_m.toFixed(0)} m` : '—' }}
          </td>
          <td class="px-4 py-2 text-muted-foreground">{{ p.source ?? '—' }}</td>
        </tr>
      </tbody>
    </Table>
  </div>
</template>
