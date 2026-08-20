from datetime import datetime, UTC

from sqlalchemy import select

from app.models.device import Device
from app.models.enums import CommandKind, UserRole
from app.models.pending_command import PendingCommand
from tests.factories import login_as, make_tenant, make_user


async def _device(db_session, tenant, name="unit-1") -> Device:
    device = Device(tenant_id=tenant.id, name=name)
    db_session.add(device)
    await db_session.flush()
    return device


async def test_disable_device(client, db_session):
    tenant = await make_tenant(db_session)
    admin = await make_user(db_session, tenant, UserRole.admin)
    device = await _device(db_session, tenant)
    await db_session.commit()

    login_as(client, admin)
    resp = await client.post(f"/devices/{device.id}/disable")
    assert resp.status_code == 200
    assert resp.json()["pairing_state"] == "disabled"

    actions = [r["action"] for r in (await client.get("/audit-log")).json()["items"]]
    assert "device.disable" in actions


async def test_disable_requires_admin(client, db_session):
    tenant = await make_tenant(db_session)
    viewer = await make_user(db_session, tenant, UserRole.viewer)
    device = await _device(db_session, tenant)
    await db_session.commit()

    login_as(client, viewer)
    assert (await client.post(f"/devices/{device.id}/disable")).status_code == 403


async def test_factory_reset_queues_command(client, db_session):
    tenant = await make_tenant(db_session)
    admin = await make_user(db_session, tenant, UserRole.admin)
    device = await _device(db_session, tenant)
    await db_session.commit()

    login_as(client, admin)
    resp = await client.post(f"/devices/{device.id}/factory-reset")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    cmd = (
        await db_session.execute(
            select(PendingCommand).where(PendingCommand.device_id == device.id)
        )
    ).scalar_one()
    assert cmd.kind == CommandKind.factory_reset.value


async def test_bulk_provision_issues_tokens(client, db_session):
    tenant = await make_tenant(db_session)
    operator = await make_user(db_session, tenant, UserRole.operator)
    await db_session.commit()

    login_as(client, operator)
    resp = await client.post("/devices/bulk", json={"names": ["a", "b", "c"]})
    assert resp.status_code == 201
    items = resp.json()["items"]
    assert len(items) == 3
    assert all(item["pairing_token"] for item in items)
    assert {i["device"]["name"] for i in items} == {"a", "b", "c"}


async def test_location_ingest_and_latest(client, db_session):
    tenant = await make_tenant(db_session)
    operator = await make_user(db_session, tenant, UserRole.operator)
    viewer = await make_user(db_session, tenant, UserRole.viewer, email="v@example.com")
    device = await _device(db_session, tenant)
    await db_session.commit()

    login_as(client, operator)
    body = {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "accuracy_m": 5.0,
        "source": "gps",
        "captured_at": datetime.now(UTC).isoformat(),
    }
    resp = await client.post(f"/devices/{device.id}/location", json=body)
    assert resp.status_code == 201
    assert resp.json()["latitude"] == 37.7749

    login_as(client, viewer)
    latest = await client.get(f"/devices/{device.id}/location")
    assert latest.status_code == 200
    assert latest.json()["longitude"] == -122.4194

    history = await client.get(f"/devices/{device.id}/location/history")
    assert history.status_code == 200
    assert history.json()["page"]["total"] == 1


async def test_update_artifact_and_rollout_flow(client, db_session):
    tenant = await make_tenant(db_session)
    operator = await make_user(db_session, tenant, UserRole.operator)
    device = await _device(db_session, tenant)
    await db_session.commit()

    login_as(client, operator)

    # register an artifact
    art = await client.post(
        "/update-artifacts",
        json={
            "version": "2.4.1",
            "target_board_rev": "rev-c",
            "storage_url": "artifacts/2.4.1.bin",
            "checksum_sha256": "ab" * 32,
        },
    )
    assert art.status_code == 201
    artifact_id = art.json()["id"]

    # create a rollout targeting just this device
    rollout = await client.post(
        "/update-rollouts",
        json={
            "artifact_id": artifact_id,
            "target": "specific_devices",
            "target_selector": {"device_ids": [str(device.id)]},
        },
    )
    assert rollout.status_code == 201
    rollout_id = rollout.json()["id"]

    # start it -- enrolls the device and queues an apply_update command
    started = await client.post(f"/update-rollouts/{rollout_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"

    detail = await client.get(f"/update-rollouts/{rollout_id}")
    assert detail.status_code == 200
    assert detail.json()["artifact"]["version"] == "2.4.1"
    assert detail.json()["devices"][0]["device_id"] == str(device.id)

    updates = await client.get(f"/devices/{device.id}/updates")
    assert updates.status_code == 200
    assert updates.json()["items"][0]["version"] == "2.4.1"

    cmd = (
        await db_session.execute(
            select(PendingCommand).where(PendingCommand.device_id == device.id)
        )
    ).scalar_one()
    assert cmd.kind == CommandKind.apply_update.value


async def test_backups_router_registered(client, db_session):
    """Regression: backups router was implemented but never mounted in main.py."""
    tenant = await make_tenant(db_session)
    viewer = await make_user(db_session, tenant, UserRole.viewer)
    device = await _device(db_session, tenant)
    await db_session.commit()

    login_as(client, viewer)
    resp = await client.get(f"/devices/{device.id}/backups")
    assert resp.status_code == 200
    assert resp.json()["page"]["total"] == 0
