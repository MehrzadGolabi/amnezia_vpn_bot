import pytest
import uuid
from src.app.db.models.server import VPNServer
from src.app.integrations.provisioning.base import VPNProvisioner, ProvisionedPeer, PeerStatus
from src.app.integrations.provisioning.mock_provisioner import MockProvisioner


@pytest.fixture
def sample_server():
    return VPNServer(
        slug="de-1",
        display_name="Germany Frankfurt",
        country_code="DE",
        country_name="Germany",
        host="de1.test.com",
    )


@pytest.mark.asyncio
async def test_mock_provisioner_create_peer(sample_server):
    provisioner = MockProvisioner()
    assert isinstance(provisioner, VPNProvisioner)

    sub_id = uuid.uuid4()
    telegram_user_id = 123456789
    device_name = "client_device"

    peer = await provisioner.create_peer(
        server=sample_server,
        subscription_id=sub_id,
        telegram_user_id=telegram_user_id,
        device_name=device_name,
    )

    assert peer.external_id is not None
    assert peer.label == f"user_{telegram_user_id}_{sample_server.slug}"
    assert peer.config_filename.endswith(".conf")
    assert isinstance(peer.config_bytes, bytes)
    
    config_text = peer.config_bytes.decode("utf-8")
    assert "[Interface]" in config_text
    assert "[Peer]" in config_text
    assert "Endpoint = de1.test.com" in config_text
    assert "Jc =" in config_text  # AmneziaWG obfuscation parameters


@pytest.mark.asyncio
async def test_mock_provisioner_lifecycle(sample_server):
    provisioner = MockProvisioner()
    sub_id = uuid.uuid4()

    peer = await provisioner.create_peer(
        server=sample_server,
        subscription_id=sub_id,
        telegram_user_id=987654321,
        device_name="phone",
    )

    # Check status
    status = await provisioner.get_peer_status(
        server=sample_server,
        peer_external_id=peer.external_id,
    )
    assert status.exists is True
    assert status.is_active is True

    # Disable peer
    await provisioner.disable_peer(
        server=sample_server,
        peer_external_id=peer.external_id,
    )
    status_disabled = await provisioner.get_peer_status(
        server=sample_server,
        peer_external_id=peer.external_id,
    )
    assert status_disabled.is_active is False

    # Redeliver config
    redelivered = await provisioner.get_peer_config(
        server=sample_server,
        peer_external_id=peer.external_id,
    )
    assert redelivered == peer.config_bytes

    # Remove peer
    await provisioner.remove_peer(
        server=sample_server,
        peer_external_id=peer.external_id,
    )
    status_removed = await provisioner.get_peer_status(
        server=sample_server,
        peer_external_id=peer.external_id,
    )
    assert status_removed.exists is False
