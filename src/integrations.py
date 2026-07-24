# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper classes for managing the charm's integrations."""

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificateTransferRequires,
)
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.hydra.v0.hydra_token_hook import (
    AuthIn,
    HydraHookProvider,
    ProviderData,
)
from charms.hydra.v0.oauth import ClientConfig, OAuthRequirer
from charms.kratos.v0.kratos_login_webhook import (
    KratosLoginWebhookProvider,
)
from charms.kratos.v0.kratos_login_webhook import ProviderData as KratosLoginProviderData
from charms.kratos.v0.kratos_registration_webhook import (
    KratosRegistrationWebhookProvider,
)
from charms.kratos.v0.kratos_registration_webhook import (
    ProviderData as KratosRegistrationProviderData,
)
from charms.openfga_k8s.v1.openfga import OpenFGARequires
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.tenant_service.v0.tenant_service_info import (
    TenantServiceInfoProvider,
)
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from jinja2 import Template
from ops.model import Model
from pydantic import AnyHttpUrl

from constants import (
    CERTIFICATE_TRANSFER_INTEGRATION_NAME,
    HYDRA_TOKEN_HOOK_INTEGRATION_NAME,
    INTERNAL_ROUTE_INTEGRATION_NAME,
    KRATOS_LOGIN_WEBHOOK_INTEGRATION_NAME,
    KRATOS_REGISTRATION_WEBHOOK_INTEGRATION_NAME,
    OAUTH_GRANT_TYPES,
    OAUTH_SCOPES,
    OPENFGA_MODEL_ID,
    PEER_INTEGRATION_NAME,
    PORT,
    POSTGRESQL_DSN_TEMPLATE,
)
from env_vars import EnvVars

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InternalIngressData:
    """The data source from the internal-ingress integration."""

    url: AnyHttpUrl | None = None
    config: dict = field(default_factory=dict)

    @classmethod
    def _external_host(cls, requirer: TraefikRouteRequirer) -> str | None:
        if not (relation := requirer._charm.model.get_relation(INTERNAL_ROUTE_INTEGRATION_NAME)):
            return
        if not relation.app:
            return
        return relation.data[relation.app].get("external_host", "")

    @classmethod
    def _scheme(cls, requirer: TraefikRouteRequirer) -> str | None:
        if not (relation := requirer._charm.model.get_relation(INTERNAL_ROUTE_INTEGRATION_NAME)):
            return
        if not relation.app:
            return
        return relation.data[relation.app].get("scheme", "")

    @classmethod
    def load(cls, requirer: TraefikRouteRequirer) -> "InternalIngressData":
        """Load the internal ingress data from the relation."""
        model, app = requirer._charm.model.name, requirer._charm.app.name
        external_host = cls._external_host(requirer)
        scheme = cls._scheme(requirer)

        external_endpoint = f"{scheme}://{external_host}/{model}-{app}"
        with open("templates/internal-route.json.j2", "r") as file:
            template = Template(file.read())

        ingress_config = json.loads(
            template.render(
                model=model,
                app=app,
                port=PORT,
                external_host=external_host,
            )
        )

        if not external_host:
            logger.error("External hostname is not set on the ingress provider")
            return cls()

        return cls(
            url=AnyHttpUrl(external_endpoint),
            config=ingress_config,
        )

    @property
    def secured(self) -> bool:
        """Check if the ingress URL uses HTTPS."""
        return self.url is not None and self.url.scheme == "https"


@dataclass(frozen=True)
class TracingData:
    """The data source from the tracing integration."""

    is_ready: bool = False
    http_endpoint: str = ""
    grpc_endpoint: str = ""

    def to_env_vars(self) -> EnvVars:
        """Get tracing env vars."""
        return {
            "TRACING_ENABLED": self.is_ready,
            "OTEL_HTTP_ENDPOINT": self.http_endpoint,
            "OTEL_GRPC_ENDPOINT": self.grpc_endpoint,
        }

    @classmethod
    def load(cls, requirer: TracingEndpointRequirer) -> "TracingData":
        """Load the tracing data."""
        if not (is_ready := requirer.is_ready()):
            return TracingData()

        http_endpoint = urlparse(requirer.get_endpoint("otlp_http"))

        grpc_endpoint_raw = requirer.get_endpoint("otlp_grpc")
        grpc_endpoint = ""
        if grpc_endpoint_raw:
            parsed = urlparse(grpc_endpoint_raw)
            grpc_endpoint = parsed.geturl().replace(f"{parsed.scheme}://", "", 1)

        return TracingData(
            is_ready=is_ready,
            http_endpoint=http_endpoint.geturl().replace(f"{http_endpoint.scheme}://", "", 1),  # type: ignore[arg-type]  # urlparse may return empty scheme; safe here since we parse a valid URL
            grpc_endpoint=grpc_endpoint,
        )


class HydraHookIntegration:
    """Wraps the HydraHookProvider library."""

    def __init__(self, provider: HydraHookProvider) -> None:
        self._provider = provider

    def is_ready(self) -> bool:
        """Check if the hydra-token-hook integration is ready."""
        rel = self._provider._charm.model.get_relation(HYDRA_TOKEN_HOOK_INTEGRATION_NAME)
        return bool(rel and rel.active)

    def update_relation_data(self, hook_url: str, api_token: str) -> None:
        """Update the hydra-token-hook relation data."""
        self._provider.update_relations_app_data(
            ProviderData(
                url=hook_url,
                auth_config_name="Authorization",
                auth_config_value=api_token,
                auth_config_in=AuthIn.header,
            )
        )


@dataclass(frozen=True)
class KratosInfoData:
    """The data source from the kratos-info integration."""

    admin_url: str = ""

    def to_env_vars(self) -> EnvVars:
        """Get Kratos info env vars."""
        return {"KRATOS_ADMIN_URL": self.admin_url}

    @classmethod
    def load(cls, charm_model: Model, integration_name: str) -> "KratosInfoData":
        """Load Kratos info from the relation databag."""
        if not (relation := charm_model.get_relation(integration_name)):
            return cls()
        if not relation.app:
            return cls()
        return cls(admin_url=relation.data[relation.app].get("admin_endpoint", ""))


class KratosRegistrationWebhookIntegration:
    """Wraps the KratosRegistrationWebhookProvider library."""

    def __init__(self, provider: KratosRegistrationWebhookProvider) -> None:
        self._provider = provider

    def is_ready(self) -> bool:
        """Check if the kratos-registration-webhook integration is ready."""
        rel = self._provider._charm.model.get_relation(
            KRATOS_REGISTRATION_WEBHOOK_INTEGRATION_NAME
        )
        return bool(rel and rel.active)

    def update_relation_data(self, webhook_url: str, api_token: str) -> None:
        """Update the kratos-registration-webhook relation data."""
        _body = b"""function(ctx) {
  identity_id: ctx.identity.id,
  email: ctx.identity.traits.email,
  tenant_id: if std.objectHas(ctx, "flow") && std.objectHas(ctx.flow, "transient_payload") && std.objectHas(ctx.flow.transient_payload, "tenant_id") then ctx.flow.transient_payload.tenant_id else "",
}"""
        self._provider.update_relations_app_data(
            KratosRegistrationProviderData(
                url=webhook_url,
                body=f"base64://{base64.b64encode(_body).decode()}",
                method="POST",
                weight=1,
                response_ignore=True,
                response_parse=False,
                auth_config_value=api_token,
            )
        )


class KratosLoginWebhookIntegration:
    """Wraps the KratosLoginWebhookProvider library."""

    def __init__(self, provider: KratosLoginWebhookProvider) -> None:
        self._provider = provider

    def is_ready(self) -> bool:
        """Check if the kratos-login-webhook integration is ready."""
        rel = self._provider._charm.model.get_relation(KRATOS_LOGIN_WEBHOOK_INTEGRATION_NAME)
        return bool(rel and rel.active)

    def update_relation_data(self, webhook_url: str, api_token: str) -> None:
        """Update the kratos-login-webhook relation data."""
        _body = b"""function(ctx) {
  identity_id: ctx.identity.id,
  email: ctx.identity.traits.email,
  tenant_id: if std.objectHas(ctx, "flow") && std.objectHas(ctx.flow, "transient_payload") && std.objectHas(ctx.flow.transient_payload, "tenant_id") then ctx.flow.transient_payload.tenant_id else "",
}"""
        self._provider.update_relations_app_data(
            KratosLoginProviderData(
                url=webhook_url,
                body=f"base64://{base64.b64encode(_body).decode()}",
                method="POST",
                response_ignore=True,
                response_parse=False,
                auth_config_value=api_token,
            )
        )


class TenantServiceInfoIntegration:
    """Wraps the TenantServiceInfoProvider library."""

    def __init__(self, provider: TenantServiceInfoProvider) -> None:
        self._provider = provider

    def update_relations_app_data(self, service_url: str, grpc_url: str) -> None:
        """Publish the tenant-service HTTP and gRPC URLs into all active relation databags."""
        self._provider.update_relations_app_data(service_url=service_url, grpc_url=grpc_url)


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """The data source from the database integration."""

    endpoint: str = ""
    database: str = ""
    username: str = ""
    password: str = ""

    @property
    def dsn(self) -> str:
        """The PostgreSQL DSN."""
        return POSTGRESQL_DSN_TEMPLATE.substitute(
            username=self.username,
            password=self.password,
            endpoint=self.endpoint,
            database=self.database,
        )

    def to_env_vars(self) -> EnvVars:
        """Get database env vars."""
        return {
            "DSN": self.dsn,
        }

    @classmethod
    def load(cls, requirer: DatabaseRequires) -> "DatabaseConfig":
        """Load the database config from the relation."""
        if not (database_integrations := requirer.relations):
            return cls()

        integration_id = database_integrations[0].id
        integration_data: dict[str, str] = requirer.fetch_relation_data()[integration_id]

        return cls(
            endpoint=integration_data.get("endpoints", "").split(",")[0],
            database=requirer.database,
            username=integration_data.get("username", ""),
            password=integration_data.get("password", ""),
        )


@dataclass(frozen=True)
class OpenFGAModelData:
    """The data source of the OpenFGA model."""

    model_id: str = ""

    def to_env_vars(self) -> EnvVars:
        """Get OpenFGA model env vars."""
        return {
            "OPENFGA_AUTHORIZATION_MODEL_ID": self.model_id,
        }

    @classmethod
    def load(cls, source: dict) -> "OpenFGAModelData":
        """Load the OpenFGA model data from a source dict."""
        return OpenFGAModelData(
            model_id=source.get(OPENFGA_MODEL_ID, ""),
        )


@dataclass(frozen=True)
class OpenFGAIntegrationData:
    """The data source from the OpenFGA integration."""

    url: str = ""
    api_token: str = ""
    store_id: str = ""

    @property
    def api_scheme(self) -> str:
        """The OpenFGA API scheme."""
        return urlparse(self.url).scheme

    @property
    def api_host(self) -> str:
        """The OpenFGA API host."""
        return urlparse(self.url).netloc

    def to_env_vars(self) -> EnvVars:
        """Get OpenFGA env vars."""
        authz_enabled = bool(self.store_id and self.api_token and self.url)
        return {
            "OPENFGA_STORE_ID": self.store_id,
            "OPENFGA_API_TOKEN": self.api_token,
            "OPENFGA_API_SCHEME": self.api_scheme,
            "OPENFGA_API_HOST": self.api_host,
            "AUTHORIZATION_ENABLED": authz_enabled,
        }


class OpenFGAIntegration:
    """Wraps the OpenFGA integration library."""

    def __init__(self, integration_requirer: "OpenFGARequires") -> None:
        self._openfga_requirer = integration_requirer

    def is_store_ready(self) -> bool:
        """Check if the OpenFGA store is ready."""
        provider_data = self._openfga_requirer.get_store_info()
        return provider_data is not None and provider_data.store_id is not None

    @property
    def openfga_integration_data(self) -> OpenFGAIntegrationData:
        """The OpenFGA integration data."""
        if not (provider_data := self._openfga_requirer.get_store_info()):
            return OpenFGAIntegrationData()

        if not provider_data.store_id or not provider_data.token:
            return OpenFGAIntegrationData()

        return OpenFGAIntegrationData(
            url=provider_data.http_api_url,
            api_token=provider_data.token,
            store_id=provider_data.store_id,
        )


class PeerData:
    """Access peer relation app-level data.

    The databag is version-keyed: each entry uses the current workload version string
    (e.g. ``"1.0.0"``) as the key, and a JSON-encoded dict as the value.  The only
    field currently stored per version is the OpenFGA authorization model ID::

        { "1.0.0": '{"openfga_model_id": "<ulid>"}' }

    Only app-level data is used; unit-level data is intentionally left empty.
    The leader unit is the sole writer; all units read.
    """

    def __init__(self, model: "Model") -> None:
        self._model = model
        self._app = model.app

    def __getitem__(self, key: str) -> dict[str, Any]:
        """Get a value from the peer relation data."""
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        value = peers.data[self._app].get(key)
        return json.loads(value) if value else {}

    def __setitem__(self, key: str, value: Any) -> None:
        """Set a value in the peer relation data."""
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return

        peers.data[self._app][key] = json.dumps(value)

    def pop(self, key: str) -> dict[str, Any]:
        """Remove and return a value from the peer relation data."""
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        data = peers.data[self._app].pop(key, None)
        return json.loads(data) if data else {}


@dataclass(frozen=True)
class OAuthProviderData:
    """The data source from the oauth integration."""

    auth_enabled: bool = False
    oidc_issuer_url: str = ""
    allowed_subjects: str = ""
    allowed_scope: str = ""
    client_id: str = ""
    jwks_url: str = ""
    token_endpoint: str = ""
    client_secret: str = ""

    def to_env_vars(self) -> EnvVars:
        """Get OAuth env vars."""
        additional_subjects = [s.strip() for s in self.allowed_subjects.split(",") if s.strip()]
        if self.client_id:
            additional_subjects.append(self.client_id)

        return {
            "AUTHENTICATION_ENABLED": self.auth_enabled,
            "AUTHENTICATION_ISSUER": self.oidc_issuer_url,
            "AUTHENTICATION_ALLOWED_SUBJECTS": ",".join(additional_subjects),
            "AUTHENTICATION_REQUIRED_SCOPE": self.allowed_scope,
            "AUTHENTICATION_JWKS_URL": self.jwks_url,
        }


class OAuthIntegration:
    """Wraps the OAuth integration library."""

    def __init__(self, requirer: OAuthRequirer) -> None:
        self._requirer = requirer
        self._requirer.update_client_config(self.oauth_client_config)

    def is_ready(self) -> bool:
        """Check if the oauth integration is ready."""
        return True if self._requirer.is_client_created() else False

    def get_oauth_provider_data(
        self,
        allowed_subjects: str = "",
        allowed_scope: str = "",
        jwks_url: str = "",
        issuer: str = "",
    ) -> OAuthProviderData:
        """Get the OAuth provider data."""
        if self._requirer.is_client_created() and (info := self._requirer.get_provider_info()):
            return OAuthProviderData(
                auth_enabled=True,
                oidc_issuer_url=info.issuer_url,
                allowed_subjects=allowed_subjects,
                allowed_scope=allowed_scope,
                token_endpoint=info.token_endpoint,
                client_id=info.client_id,
                client_secret=info.client_secret,
            )

        if issuer:
            return OAuthProviderData(
                auth_enabled=True,
                oidc_issuer_url=issuer,
                jwks_url=jwks_url,
                allowed_subjects=allowed_subjects,
                allowed_scope=allowed_scope,
            )

        return OAuthProviderData()

    @property
    def oauth_client_config(self) -> ClientConfig:
        """The OAuth client config."""
        client = ClientConfig(
            redirect_uri="https://example.com",
            scope=OAUTH_SCOPES,
            grant_types=OAUTH_GRANT_TYPES,
        )

        return client


@dataclass(frozen=True)
class TLSCertificates:
    """The data source from the certificate transfer integration."""

    ca_bundle: str

    @classmethod
    def load(cls, requirer: CertificateTransferRequires) -> "TLSCertificates":
        """Fetch the CA certificates from all receive-ca-cert integrations."""
        # deal with v1 relations
        ca_certs = requirer.get_all_certificates()

        # deal with v0 relations
        cert_transfer_integrations = requirer.charm.model.relations[
            CERTIFICATE_TRANSFER_INTEGRATION_NAME
        ]

        for integration in cert_transfer_integrations:
            ca = {
                integration.data[unit]["ca"]
                for unit in integration.units
                if "ca" in integration.data.get(unit, {})
            }
            ca_certs.update(ca)

        ca_bundle = "\n".join(sorted(ca_certs))

        return cls(ca_bundle=ca_bundle)
