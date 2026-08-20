<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '@/lib/api'
import type { DeviceUpdate, UpdateArtifact, UpdateRollout } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Card from '@/components/ui/Card.vue'
import Input from '@/components/ui/Input.vue'
import Table from '@/components/ui/Table.vue'

const props = defineProps<{ deviceId: string }>()
const auth = useAuthStore()

const updates = ref<DeviceUpdate[]>([])
const artifacts = ref<UpdateArtifact[]>([])
const rollouts = ref<UpdateRollout[]>([])
const loading = ref(true)
const error = ref('')
const message = ref('')

// create-artifact form
const showNewArtifact = ref(false)
const artVersion = ref('')
const artBoardRev = ref('')
const artStorageUrl = ref('')
const artChecksum = ref('')

// create-rollout form
const showNewRollout = ref(false)
const selectedArtifact = ref('')
const rolloutTarget = ref<'all' | 'specific_devices'>('specific_devices')

const busy = ref(false)

function statusTone(status: string): 'success' | 'neutral' | 'danger' | 'accent' {
  if (status === 'succeeded' || status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'applying' || status === 'in_progress') return 'accent'
  return 'neutral'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [u, a, r] = await Promise.all([
      api.updates.deviceUpdates(props.deviceId),
      api.updates.listArtifacts().catch(() => ({ items: [] as UpdateArtifact[] })),
      api.updates.listRollouts().catch(() => ({ items: [] as UpdateRollout[] })),
    ])
    updates.value = u.items
    artifacts.value = a.items
    rollouts.value = r.items
    if (!selectedArtifact.value && artifacts.value.length) selectedArtifact.value = artifacts.value[0].id
  } catch {
    error.value = 'Could not load update data.'
  } finally {
    loading.value = false
  }
}

async function createArtifact() {
  busy.value = true
  message.value = ''
  try {
    await api.updates.createArtifact({
      version: artVersion.value,
      target_board_rev: artBoardRev.value,
      storage_url: artStorageUrl.value,
      checksum_sha256: artChecksum.value,
    })
    message.value = 'Artifact registered.'
    showNewArtifact.value = false
    artVersion.value = ''
    artBoardRev.value = ''
    artStorageUrl.value = ''
    artChecksum.value = ''
    await load()
  } catch (e) {
    message.value = e instanceof ApiError ? e.message : 'Failed to register artifact.'
  } finally {
    busy.value = false
  }
}

async function createAndStartRollout() {
  busy.value = true
  message.value = ''
  try {
    const targetSelector =
      rolloutTarget.value === 'all' ? {} : { device_ids: [props.deviceId] }
    const rollout = await api.updates.createRollout({
      artifact_id: selectedArtifact.value,
      target: rolloutTarget.value,
      target_selector: targetSelector,
    })
    await api.updates.startRollout(rollout.id)
    message.value = 'Rollout created and started.'
    showNewRollout.value = false
    await load()
  } catch (e) {
    message.value = e instanceof ApiError ? e.message : 'Rollout failed.'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-if="loading" class="text-sm text-muted-foreground">Loading…</div>
  <Card v-else-if="error" class="p-6 text-sm text-danger">{{ error }}</Card>
  <div v-else class="space-y-6">
    <p v-if="message" class="text-sm text-muted-foreground">{{ message }}</p>

    <Card class="p-4">
      <h3 class="text-sm font-semibold">This device's update history</h3>
      <div v-if="updates.length === 0" class="mt-3 text-sm text-muted-foreground">
        No updates have been applied to this device.
      </div>
      <Table v-else class="mt-3">
        <thead class="border-b border-border bg-surface-muted text-xs uppercase text-muted-foreground">
          <tr>
            <th class="px-4 py-2 font-medium">Version</th>
            <th class="px-4 py-2 font-medium">Status</th>
            <th class="px-4 py-2 font-medium">Applied</th>
            <th class="px-4 py-2 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in updates" :key="u.rollout_id" class="border-b border-border last:border-0">
            <td class="px-4 py-2 font-mono">{{ u.version }}</td>
            <td class="px-4 py-2">
              <Badge :tone="statusTone(u.status)">{{ u.status }}</Badge>
            </td>
            <td class="px-4 py-2 text-muted-foreground">
              {{ u.applied_at ? new Date(u.applied_at).toLocaleString() : '—' }}
            </td>
            <td class="px-4 py-2 text-muted-foreground">{{ u.error ?? '' }}</td>
          </tr>
        </tbody>
      </Table>
    </Card>

    <Card class="p-4">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-semibold">OTA artifacts</h3>
          <p class="text-sm text-muted-foreground">Builds staged in object storage.</p>
        </div>
        <Button v-if="auth.hasRole('operator')" size="sm" variant="secondary" @click="showNewArtifact = !showNewArtifact">
          {{ showNewArtifact ? 'Close' : 'Register artifact' }}
        </Button>
      </div>

      <div v-if="showNewArtifact" class="mt-3 grid grid-cols-2 gap-3">
        <Input v-model="artVersion" placeholder="Version (e.g. 2.4.1)" />
        <Input v-model="artBoardRev" placeholder="Board revision" />
        <Input v-model="artStorageUrl" placeholder="Storage object key" />
        <Input v-model="artChecksum" placeholder="SHA-256 checksum" />
        <Button class="col-span-2" size="sm" :disabled="busy" @click="createArtifact">Register</Button>
      </div>

      <div v-if="artifacts.length === 0" class="mt-3 text-sm text-muted-foreground">
        No artifacts registered yet.
      </div>
      <Table v-else class="mt-3">
        <thead class="border-b border-border bg-surface-muted text-xs uppercase text-muted-foreground">
          <tr>
            <th class="px-4 py-2 font-medium">Version</th>
            <th class="px-4 py-2 font-medium">Board</th>
            <th class="px-4 py-2 font-medium">Checksum</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in artifacts" :key="a.id" class="border-b border-border last:border-0">
            <td class="px-4 py-2 font-mono">{{ a.version }}</td>
            <td class="px-4 py-2">{{ a.target_board_rev }}</td>
            <td class="px-4 py-2 font-mono text-muted-foreground">{{ a.checksum_sha256.slice(0, 16) }}…</td>
          </tr>
        </tbody>
      </Table>
    </Card>

    <Card v-if="auth.hasRole('operator')" class="p-4">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-semibold">Rollout</h3>
          <p class="text-sm text-muted-foreground">Create and start an update rollout.</p>
        </div>
        <Button size="sm" variant="secondary" :disabled="artifacts.length === 0" @click="showNewRollout = !showNewRollout">
          {{ showNewRollout ? 'Close' : 'New rollout' }}
        </Button>
      </div>

      <div v-if="showNewRollout" class="mt-3 space-y-3">
        <select v-model="selectedArtifact" class="w-full rounded border border-border bg-surface px-3 py-2 text-sm">
          <option v-for="a in artifacts" :key="a.id" :value="a.id">{{ a.version }}</option>
        </select>
        <div class="flex items-center gap-4 text-sm">
          <label class="flex items-center gap-2">
            <input v-model="rolloutTarget" type="radio" value="specific_devices" /> This device
          </label>
          <label class="flex items-center gap-2">
            <input v-model="rolloutTarget" type="radio" value="all" /> All devices
          </label>
        </div>
        <Button size="sm" :disabled="busy || !selectedArtifact" @click="createAndStartRollout">
          Create &amp; start
        </Button>
      </div>

      <div v-if="rollouts.length === 0" class="mt-3 text-sm text-muted-foreground">
        No rollouts yet.
      </div>
      <Table v-else class="mt-3">
        <thead class="border-b border-border bg-surface-muted text-xs uppercase text-muted-foreground">
          <tr>
            <th class="px-4 py-2 font-medium">Rollout</th>
            <th class="px-4 py-2 font-medium">Target</th>
            <th class="px-4 py-2 font-medium">Status</th>
            <th class="px-4 py-2 font-medium">Started</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rollouts" :key="r.id" class="border-b border-border last:border-0">
            <td class="px-4 py-2 font-mono">{{ r.id.slice(0, 8) }}</td>
            <td class="px-4 py-2">{{ r.target }}</td>
            <td class="px-4 py-2">
              <Badge :tone="statusTone(r.status)">{{ r.status }}</Badge>
            </td>
            <td class="px-4 py-2 text-muted-foreground">
              {{ r.started_at ? new Date(r.started_at).toLocaleString() : '—' }}
            </td>
          </tr>
        </tbody>
      </Table>
    </Card>
  </div>
</template>
