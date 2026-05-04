# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, create_autospec, mock_open, patch

import pytest
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.hydra.v0.hydra_token_hook import AuthIn, HydraHookProvider, ProviderData
from charms.kratos.v0.kratos_login_webhook import KratosLoginWebhookProvider
from charms.kratos.v0.kratos_registration_webhook import KratosRegistrationWebhookProvider
from charms.openfga_k8s.v1.openfga import OpenfgaProviderAppData, OpenFGARequires
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.tenant_service_operator.v0.tenant_service_info import TenantServiceInfoProvider
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from ops.model import Model
from pydantic import AnyHttpUrl
from scenario import Relation

from constants import PORT
from integrations import (
    DatabaseConfig,
    HydraHookIntegration,
    InternalIngressData,
    KratosInfoData,
    KratosLoginWebhookIntegration,
    KratosRegistrationWebhookIntegration,
    OpenFGAIntegration,
    OpenFGAIntegrationData,
    OpenFGAModelData,
    TenantServiceInfoIntegration,
    TracingData,
)


class TestInternalIngressData:
    @pytest.fixture
    def mocked_relation(self) -> MagicMock:
        mocked = MagicMock(spec=Relation)
        mocked.app = "app"
        mocked.data = {"app": {"external_host": "external.tenant-service.com", "scheme": "http"}}
        return mocked

    @pytest.fixture
    def mocked_requirer(self, mocked_relation: MagicMock) -> MagicMock:
        mocked = create_autospec(TraefikRouteRequirer)
        mocked._charm = MagicMock()
        mocked._charm.model.name = "model"
        mocked._charm.app.name = "app"
        mocked.scheme = "http"
        mocked._charm.model.get_relation = MagicMock(return_value=mocked_relation)

        return mocked

    @pytest.fixture
    def ingress_template(self) -> str:
        return (
            '{"model": "{{ model }}", '
            '"app": "{{ app }}", '
            '"port": {{ port }}, '
            '"external_host": "{{ external_host }}"}'
        )

    def test_load_with_external_host(
        self, mocked_requirer: MagicMock, ingress_template: str
    ) -> None:
        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = InternalIngressData.load(mocked_requirer)

        expected_ingress_config = {
            "model": "model",
            "app": "app",
            "port": PORT,
            "external_host": "external.tenant-service.com",
        }
        assert actual == InternalIngressData(
            url=AnyHttpUrl("http://external.tenant-service.com/model-app"),
            config=expected_ingress_config,
        )

    def test_load_without_external_host(
        self, mocked_requirer: MagicMock, mocked_relation: MagicMock, ingress_template: str
    ) -> None:
        mocked_relation.data = {"app": {"external_host": "", "scheme": "http"}}

        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = InternalIngressData.load(mocked_requirer)

        assert actual == InternalIngressData(
            url=None,
            config={},
        )


class TestDatabaseConfig:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        mocked = create_autospec(DatabaseRequires)
        mocked.database = "test_db"
        mocked.relations = [MagicMock(id=1)]
        mocked.fetch_relation_data.return_value = {
            1: {
                "endpoints": "host:5432",
                "username": "user",
                "password": "password",
            }
        }
        return mocked

    def test_load(self, mocked_requirer: MagicMock) -> None:
        config = DatabaseConfig.load(mocked_requirer)
        assert config.endpoint == "host:5432"
        assert config.database == "test_db"
        assert config.username == "user"
        assert config.password == "password"

    def test_dsn(self, mocked_requirer: MagicMock) -> None:
        config = DatabaseConfig.load(mocked_requirer)
        assert config.dsn == "postgres://user:password@host:5432/test_db"

    def test_to_env_vars(self, mocked_requirer: MagicMock) -> None:
        config = DatabaseConfig.load(mocked_requirer)
        assert config.to_env_vars() == {"DSN": "postgres://user:password@host:5432/test_db"}


class TestOpenFGAModelData:
    def test_load(self) -> None:
        source = {"openfga_model_id": "test-model-id"}
        data = OpenFGAModelData.load(source)
        assert data.model_id == "test-model-id"

    def test_load_empty(self) -> None:
        source = {}
        data = OpenFGAModelData.load(source)
        assert data.model_id == ""

    def test_to_env_vars(self) -> None:
        data = OpenFGAModelData(model_id="test-model-id")
        assert data.to_env_vars() == {"OPENFGA_AUTHORIZATION_MODEL_ID": "test-model-id"}


class TestOpenFGAIntegrationData:
    def test_properties(self) -> None:
        data = OpenFGAIntegrationData(
            url="http://openfga.local:8080",
            api_token="token",
            store_id="store-id",
        )
        assert data.api_scheme == "http"
        assert data.api_host == "openfga.local:8080"

    def test_to_env_vars(self) -> None:
        data = OpenFGAIntegrationData(
            url="http://openfga.local:8080",
            api_token="token",
            store_id="store-id",
        )
        expected = {
            "AUTHORIZATION_ENABLED": True,
            "OPENFGA_STORE_ID": "store-id",
            "OPENFGA_API_TOKEN": "token",
            "OPENFGA_API_SCHEME": "http",
            "OPENFGA_API_HOST": "openfga.local:8080",
        }
        assert data.to_env_vars() == expected

    def test_to_env_vars_when_empty(self) -> None:
        data = OpenFGAIntegrationData()
        expected = {
            "AUTHORIZATION_ENABLED": False,
            "OPENFGA_STORE_ID": "",
            "OPENFGA_API_TOKEN": "",
            "OPENFGA_API_SCHEME": "",
            "OPENFGA_API_HOST": "",
        }
        assert data.to_env_vars() == expected


class TestOpenFGAIntegration:
    @pytest.fixture(autouse=True)
    def mocked_openfga_integration(self) -> None:
        """Override the autouse fixture from conftest.py to do nothing."""
        pass

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(OpenFGARequires)

    def test_is_store_ready_true(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = OpenfgaProviderAppData(
            store_id="store-id",
            token="token",
            http_api_url="http://url",
            grpc_api_url="grpc://url",
        )
        integration = OpenFGAIntegration(mocked_requirer)
        assert integration.is_store_ready()

    def test_is_store_ready_false_no_info(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = None
        integration = OpenFGAIntegration(mocked_requirer)
        assert not integration.is_store_ready()

    def test_is_store_ready_false_no_id(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = OpenfgaProviderAppData(
            store_id=None,
            token="token",
            http_api_url="http://url",
            grpc_api_url="grpc://url",
        )
        integration = OpenFGAIntegration(mocked_requirer)
        assert not integration.is_store_ready()

    def test_openfga_integration_data(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = OpenfgaProviderAppData(
            store_id="store-id",
            token="token",
            http_api_url="http://url",
            grpc_api_url="grpc://url",
        )
        integration = OpenFGAIntegration(mocked_requirer)
        data = integration.openfga_integration_data

        assert data.store_id == "store-id"
        assert data.api_token == "token"
        assert data.url == "http://url"

    def test_openfga_integration_data_empty(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = None
        integration = OpenFGAIntegration(mocked_requirer)
        data = integration.openfga_integration_data

        assert data == OpenFGAIntegrationData()


class TestTracingData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        mocked = create_autospec(TracingEndpointRequirer)
        mocked.is_ready.return_value = True
        mocked.get_endpoint.side_effect = lambda protocol: {
            "otlp_http": "http://tempo:4318",
            "otlp_grpc": "http://tempo:4317",
        }.get(protocol, "")
        return mocked

    def test_to_env_vars(self) -> None:
        data = TracingData(
            is_ready=True,
            http_endpoint="tempo:4318",
            grpc_endpoint="tempo:4317",
        )
        expected = {
            "TRACING_ENABLED": True,
            "OTEL_HTTP_ENDPOINT": "tempo:4318",
            "OTEL_GRPC_ENDPOINT": "tempo:4317",
        }
        assert data.to_env_vars() == expected

    def test_load(self, mocked_requirer: MagicMock) -> None:
        data = TracingData.load(mocked_requirer)
        assert data.is_ready is True
        assert data.http_endpoint == "tempo:4318"
        assert data.grpc_endpoint == "tempo:4317"

    def test_load_not_ready(self) -> None:
        mocked = create_autospec(TracingEndpointRequirer)
        mocked.is_ready.return_value = False
        data = TracingData.load(mocked)
        assert data == TracingData()


class TestKratosInfoData:
    @pytest.fixture
    def mocked_model(self) -> MagicMock:
        mocked = create_autospec(Model)
        relation = MagicMock()
        relation.app = MagicMock()
        relation.data = {relation.app: {"admin_endpoint": "http://kratos-admin:4434"}}
        mocked.get_relation.return_value = relation
        return mocked

    def test_load(self, mocked_model: MagicMock) -> None:
        data = KratosInfoData.load(mocked_model, "kratos-info")
        assert data.admin_url == "http://kratos-admin:4434"

    def test_load_no_relation(self) -> None:
        mocked = create_autospec(Model)
        mocked.get_relation.return_value = None
        data = KratosInfoData.load(mocked, "kratos-info")
        assert data == KratosInfoData()

    def test_to_env_vars(self) -> None:
        data = KratosInfoData(admin_url="http://kratos-admin:4434")
        assert data.to_env_vars() == {"KRATOS_ADMIN_URL": "http://kratos-admin:4434"}


class TestHydraHookIntegration:
    @pytest.fixture
    def mocked_provider(self) -> MagicMock:
        mocked = create_autospec(HydraHookProvider)
        mocked._charm = MagicMock()
        return mocked

    def test_is_ready_true(self, mocked_provider: MagicMock) -> None:
        relation = MagicMock()
        relation.active = True
        mocked_provider._charm.model.get_relation.return_value = relation
        integration = HydraHookIntegration(mocked_provider)
        assert integration.is_ready()

    def test_is_ready_false_no_relation(self, mocked_provider: MagicMock) -> None:
        mocked_provider._charm.model.get_relation.return_value = None
        integration = HydraHookIntegration(mocked_provider)
        assert not integration.is_ready()

    def test_is_ready_false_inactive(self, mocked_provider: MagicMock) -> None:
        relation = MagicMock()
        relation.active = False
        mocked_provider._charm.model.get_relation.return_value = relation
        integration = HydraHookIntegration(mocked_provider)
        assert not integration.is_ready()

    def test_update_relation_data(self, mocked_provider: MagicMock) -> None:
        integration = HydraHookIntegration(mocked_provider)
        integration.update_relation_data("http://hook-url", "api-token")
        mocked_provider.update_relations_app_data.assert_called_once_with(
            ProviderData(
                url="http://hook-url",
                auth_config_name="Authorization",
                auth_config_value="api-token",
                auth_config_in=AuthIn.header,
            )
        )


class TestKratosRegistrationWebhookIntegration:
    @pytest.fixture
    def mocked_provider(self) -> MagicMock:
        mocked = create_autospec(KratosRegistrationWebhookProvider)
        mocked._charm = MagicMock()
        return mocked

    def test_is_ready_true(self, mocked_provider: MagicMock) -> None:
        relation = MagicMock()
        relation.active = True
        mocked_provider._charm.model.get_relation.return_value = relation
        integration = KratosRegistrationWebhookIntegration(mocked_provider)
        assert integration.is_ready()

    def test_is_ready_false_no_relation(self, mocked_provider: MagicMock) -> None:
        mocked_provider._charm.model.get_relation.return_value = None
        integration = KratosRegistrationWebhookIntegration(mocked_provider)
        assert not integration.is_ready()

    def test_update_relation_data(self, mocked_provider: MagicMock) -> None:
        integration = KratosRegistrationWebhookIntegration(mocked_provider)
        integration.update_relation_data("http://webhook-url", "api-token")
        mocked_provider.update_relations_app_data.assert_called_once()
        call_args = mocked_provider.update_relations_app_data.call_args[0][0]
        assert call_args.url == "http://webhook-url"
        assert call_args.auth_config_value == "api-token"
        assert call_args.method == "POST"
        assert call_args.response_ignore is True


class TestKratosLoginWebhookIntegration:
    @pytest.fixture
    def mocked_provider(self) -> MagicMock:
        mocked = create_autospec(KratosLoginWebhookProvider)
        mocked._charm = MagicMock()
        return mocked

    def test_is_ready_true(self, mocked_provider: MagicMock) -> None:
        relation = MagicMock()
        relation.active = True
        mocked_provider._charm.model.get_relation.return_value = relation
        integration = KratosLoginWebhookIntegration(mocked_provider)
        assert integration.is_ready()

    def test_is_ready_false_no_relation(self, mocked_provider: MagicMock) -> None:
        mocked_provider._charm.model.get_relation.return_value = None
        integration = KratosLoginWebhookIntegration(mocked_provider)
        assert not integration.is_ready()

    def test_update_relation_data(self, mocked_provider: MagicMock) -> None:
        integration = KratosLoginWebhookIntegration(mocked_provider)
        integration.update_relation_data("http://login-webhook-url", "login-token")
        mocked_provider.update_relations_app_data.assert_called_once()
        call_args = mocked_provider.update_relations_app_data.call_args[0][0]
        assert call_args.url == "http://login-webhook-url"
        assert call_args.auth_config_value == "login-token"
        assert call_args.method == "POST"
        assert call_args.response_ignore is True


class TestTenantServiceInfoIntegration:
    @pytest.fixture
    def mocked_provider(self) -> MagicMock:
        return create_autospec(TenantServiceInfoProvider)

    def test_update_relations_app_data(self, mocked_provider: MagicMock) -> None:
        integration = TenantServiceInfoIntegration(mocked_provider)
        integration.update_relations_app_data(
            "http://tenant-service:8080", "grpc://tenant-service:50051"
        )
        mocked_provider.update_relations_app_data.assert_called_once_with(
            service_url="http://tenant-service:8080",
            grpc_url="grpc://tenant-service:50051",
        )
