export type UserRole = 'viewer' | 'operator' | 'admin'
export type PairingState = 'pending' | 'authorized' | 'disabled' | 'revoked'

export interface Page {
  total: number
  limit: number
  offset: number
}

export interface User {
  id: string
  email: string
  role: UserRole
  created_at: string
}

export interface Device {
  id: string
  name: string
  pairing_state: PairingState
  online: boolean
  last_seen_at: string | null
  serial: string | null
  board_rev: string | null
  created_at: string
}

export interface DeviceListResponse {
  items: Device[]
  page: Page
}

export interface DeviceCreateResponse {
  device: Device
  pairing_token: string | null
}

export interface AuditLogEntry {
  id: string
  actor_user_id: string | null
  action: string
  target_device_id: string | null
  payload: Record<string, unknown>
  created_at: string
}

export interface AuditLogListResponse {
  items: AuditLogEntry[]
  page: Page
}

export type FaultSeverity = 'info' | 'warn' | 'critical'

export interface Fault {
  id: string
  device_id: string
  code: string
  severity: FaultSeverity
  message: string
  raised_at: string
  cleared_at: string | null
}

export interface FaultListResponse {
  items: Fault[]
  page: Page
}

export type AlarmState = 'active' | 'acknowledged' | 'resolved'

export interface Alarm {
  id: string
  alarm_rule_id: string
  device_id: string
  state: AlarmState
  triggered_at: string
  acknowledged_at: string | null
  resolved_at: string | null
}

export interface AlarmListResponse {
  items: Alarm[]
  page: Page
}

// Device-reported 4-byte alarm from the `alarms` table (GET /devices/{id}/alarms).
// `alarm_code` is the packed big-endian uint32 (byte0=major_id, byte1=sub_section,
// byte2=fault_type, byte3=severity), e.g. 0x01020304 -> (1, 2, 3, 4).
export interface DeviceAlarm {
  id: string
  device_id: string
  major_id: number
  sub_section: number
  fault_type: number
  severity: number
  alarm_code: number
  state: AlarmState
  triggered_at: string
  resolved_at: string | null
}

export interface DeviceAlarmListResponse {
  items: DeviceAlarm[]
  page: Page
}

export interface AlarmRule {
  id: string
  name: string
  condition: Record<string, unknown>
  notify_channels: Record<string, unknown>
  enabled: boolean
}

export interface LogBundle {
  id: string
  device_id: string
  size_bytes: number
  uploaded_at: string
  time_range_start: string
  time_range_end: string
}

export interface LogBundleListResponse {
  items: LogBundle[]
  page: Page
}

export interface Backup {
  id: string
  device_id: string
  size_bytes: number
  created_at: string
  restored_at: string | null
}

export interface BackupListResponse {
  items: Backup[]
  page: Page
}

export type RolloutTarget = 'all' | 'device_group' | 'specific_devices'
export type RolloutStatus = 'pending' | 'in_progress' | 'completed' | 'failed'
export type DeviceRolloutStatus = 'pending' | 'applying' | 'succeeded' | 'failed'

export interface UpdateArtifact {
  id: string
  version: string
  target_board_rev: string
  storage_url: string
  checksum_sha256: string
  created_at: string
}

export interface UpdateArtifactListResponse {
  items: UpdateArtifact[]
  page: Page
}

export interface UpdateRollout {
  id: string
  artifact_id: string
  target: RolloutTarget
  target_selector: Record<string, unknown>
  status: RolloutStatus
  started_at: string | null
  completed_at: string | null
}

export interface UpdateRolloutListResponse {
  items: UpdateRollout[]
  page: Page
}

export interface RolloutDevice {
  device_id: string
  status: DeviceRolloutStatus
  applied_at: string | null
  error: string | null
}

export interface UpdateRolloutDetail {
  rollout: UpdateRollout
  artifact: UpdateArtifact
  devices: RolloutDevice[]
}

export interface DeviceUpdate {
  rollout_id: string
  version: string
  status: DeviceRolloutStatus
  applied_at: string | null
  error: string | null
}

export interface DeviceUpdateListResponse {
  items: DeviceUpdate[]
  page: Page
}

export interface DeviceLocation {
  id: string
  device_id: string
  latitude: number
  longitude: number
  altitude_m: number | null
  accuracy_m: number | null
  source: string | null
  captured_at: string
  created_at: string
}

export interface DeviceLocationListResponse {
  items: DeviceLocation[]
  page: Page
}
