#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Juju charm for Identity Platform Tenant Service."""

import logging
import subprocess
from functools import cached_property
from os.path import join
from secrets import token_hex

import ops
import requests
from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificateTransferRequires,
)
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.hydra.v0.hydra_token_hook import HydraHookProvider
from charms.hydra.v0.oauth import OAuthRequirer
from charms.kratos.v0.kratos_login_webhook import KratosLoginWebhookProvider
from charms.kratos.v0.kratos_registration_webhook import KratosRegistrationWebhookProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.openfga_k8s.v1.openfga import (
    OpenFGARequires,
    OpenFGAStoreRemovedEvent,
)
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.tenant_service.v0.tenant_service_info import TenantServiceInfoProvider
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer

from cli import CommandLine
from clients import HTTPClient
from configs import CharmConfig
from constants import (
    API_TOKEN_SECRET_KEY,
    API_TOKEN_SECRET_LABEL,
    CERTIFICATE_TRANSFER_INTEGRATION_NAME,
    DATABASE_INTEGRATION_NAME,
    GRAFANA_DASHBOARD_INTEGRATION_NAME,
    GRPC_PORT,
    INTERNAL_ROUTE_INTEGRATION_NAME,
    KRATOS_INFO_INTEGRATION_NAME,
    LOCAL_CERTIFICATES_PATH,
    LOCAL_CHARM_CERTIFICATES_FILE,
    LOCAL_CHARM_CERTIFICATES_PATH,
    LOGGING_INTEGRATION_NAME,
    MIGRATION_COMPLETED,
    OAUTH_INTEGRATION_NAME,
    OPENFGA_INTEGRATION_NAME,
    OPENFGA_MODEL_ID,
    OPENFGA_STORE_NAME,
    PEBBLE_READY_CHECK_NAME,
    PEER_INTEGRATION_NAME,
    PORT,
    PROMETHEUS_SCRAPE_INTEGRATION_NAME,
    TEMPO_TRACING_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import (
    CharmError,
    CreateFgaModelError,
    MigrationCheckError,
    MigrationError,
    PebbleError,
)
from integrations import (
    DatabaseConfig,
    HydraHookIntegration,
    InternalIngressData,
    KratosInfoData,
    KratosLoginWebhookIntegration,
    KratosRegistrationWebhookIntegration,
    OAuthIntegration,
    OpenFGAIntegration,
    OpenFGAModelData,
    PeerData,
    TenantServiceInfoIntegration,
    TLSCertificates,
    TracingData,
)
from secret import Secrets
from services import PebbleService, WorkloadService
from utils import (
    NOOP_CONDITIONS,
    authentication_config_status,
    container_connectivity,
    database_integration_exists,
    database_resource_is_created,
    kratos_info_integration_exists,
    migration_is_ready,
    openfga_integration_exists,
    peer_integration_exists,
)

logger = logging.getLogger(__name__)


class TenantServiceOperatorCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)

        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self._cli = CommandLine(self._container)
        self.peer_data = PeerData(self.model)
        self._workload_service = WorkloadService(self.unit)
        self._pebble_service = PebbleService(self.unit)
        self._secrets = Secrets(self.model)
        self._config = CharmConfig(self.config)

        self.oauth_requirer = OAuthRequirer(self, relation_name=OAUTH_INTEGRATION_NAME)
        self.oauth_integration = OAuthIntegration(self.oauth_requirer)

        self.hydra_token_hook = HydraHookProvider(self)
        self.hydra_token_hook_integration = HydraHookIntegration(self.hydra_token_hook)

        self.kratos_registration_webhook = KratosRegistrationWebhookProvider(self)
        self.kratos_registration_webhook_integration = KratosRegistrationWebhookIntegration(
            self.kratos_registration_webhook
        )

        self.kratos_login_webhook = KratosLoginWebhookProvider(self)
        self.kratos_login_webhook_integration = KratosLoginWebhookIntegration(
            self.kratos_login_webhook
        )

        self.tenant_service_info_provider = TenantServiceInfoProvider(self)
        self.tenant_service_info_integration = TenantServiceInfoIntegration(
            self.tenant_service_info_provider
        )

        self.openfga_requirer = OpenFGARequires(
            self, store_name=OPENFGA_STORE_NAME, relation_name=OPENFGA_INTEGRATION_NAME
        )
        self.openfga_integration = OpenFGAIntegration(self.openfga_requirer)

        self.database_requirer = DatabaseRequires(
            self,
            relation_name=DATABASE_INTEGRATION_NAME,
            database_name=f"{self.model.name}_{self.app.name}",
        )

        self.internal_ingress = TraefikRouteRequirer(
            self,
            self.model.get_relation(INTERNAL_ROUTE_INTEGRATION_NAME),  # type: ignore[arg-type]  # relation may be None; TraefikRouteRequirer accepts this
            INTERNAL_ROUTE_INTEGRATION_NAME,
            raw=True,
        )

        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=PROMETHEUS_SCRAPE_INTEGRATION_NAME,
            jobs=[
                {
                    "job_name": "tenant_service_metrics",
                    "metrics_path": "/api/v0/metrics",
                    "static_configs": [
                        {
                            "targets": [f"*:{PORT}"],
                        }
                    ],
                }
            ],
        )

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        self.certificate_transfer_requirer = CertificateTransferRequires(
            self,
            relationship_name=CERTIFICATE_TRANSFER_INTEGRATION_NAME,
        )

        # Pebble events
        self.framework.observe(self.on.tenant_service_pebble_ready, self._on_pebble_ready)
        self.framework.observe(
            self.on.tenant_service_pebble_check_failed, self._on_pebble_check_failed
        )
        self.framework.observe(
            self.on.tenant_service_pebble_check_recovered, self._on_pebble_check_recovered
        )

        # Lifecycle events
        self.framework.observe(self.on.config_changed, self._on_holistic_handler)
        self.framework.observe(self.on.leader_elected, self._on_holistic_handler)
        self.framework.observe(self.on.leader_settings_changed, self._on_holistic_handler)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_status)
        self.framework.observe(self.on.secret_changed, self._on_holistic_handler)
        self.framework.observe(self.on.update_status, self._on_holistic_handler)

        # Actions
        self.framework.observe(self.on.get_access_token_action, self._on_get_access_token_action)
        self.framework.observe(self.on.create_tenant_action, self._on_create_tenant_action)
        self.framework.observe(self.on.list_tenants_action, self._on_list_tenants_action)
        self.framework.observe(self.on.delete_tenant_action, self._on_delete_tenant_action)
        self.framework.observe(self.on.activate_tenant_action, self._on_activate_tenant_action)
        self.framework.observe(self.on.deactivate_tenant_action, self._on_deactivate_tenant_action)
        self.framework.observe(self.on.update_tenant_action, self._on_update_tenant_action)
        self.framework.observe(self.on.list_tenant_users_action, self._on_list_tenant_users_action)
        self.framework.observe(self.on.invite_user_action, self._on_invite_user_action)
        self.framework.observe(self.on.provision_user_action, self._on_provision_user_action)
        self.framework.observe(self.on.update_user_role_action, self._on_update_user_role_action)

        # Hydra token hook relation
        self.framework.observe(self.hydra_token_hook.on.ready, self._on_holistic_handler)

        # Kratos registration webhook relation
        self.framework.observe(
            self.kratos_registration_webhook.on.ready, self._on_holistic_handler
        )

        # Kratos info relation
        self.framework.observe(
            self.on[KRATOS_INFO_INTEGRATION_NAME].relation_changed, self._on_holistic_handler
        )
        self.framework.observe(
            self.on[KRATOS_INFO_INTEGRATION_NAME].relation_broken, self._on_holistic_handler
        )

        # Kratos login webhook relation
        self.framework.observe(self.kratos_login_webhook.on.ready, self._on_holistic_handler)

        # OAuth relation
        self.framework.observe(
            self.oauth_requirer.on.oauth_info_changed,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self.oauth_requirer.on.oauth_info_removed,
            self._on_holistic_handler,
        )

        # Certificate transfer relation
        self.framework.observe(
            self.certificate_transfer_requirer.on.certificate_set_updated,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self.certificate_transfer_requirer.on.certificates_removed,
            self._on_holistic_handler,
        )

        # COS relations
        self._log_forwarder = LogForwarder(self, relation_name=LOGGING_INTEGRATION_NAME)

        self._grafana_dashboards = GrafanaDashboardProvider(
            self,
            relation_name=GRAFANA_DASHBOARD_INTEGRATION_NAME,
        )

        self.tracing_requirer = TracingEndpointRequirer(
            self,
            relation_name=TEMPO_TRACING_INTEGRATION_NAME,
            protocols=["otlp_http", "otlp_grpc"],
        )

        # Peer relation
        self.framework.observe(
            self.on[PEER_INTEGRATION_NAME].relation_created, self._on_holistic_handler
        )
        self.framework.observe(
            self.on[PEER_INTEGRATION_NAME].relation_changed, self._on_holistic_handler
        )

        # Resource patching
        self.framework.observe(
            self.resources_patch.on.patch_failed, self._on_resource_patch_failed
        )

        # Database
        self.framework.observe(
            self.database_requirer.on.database_created, self._on_holistic_handler
        )
        self.framework.observe(
            self.database_requirer.on.endpoints_changed, self._on_holistic_handler
        )
        self.framework.observe(
            self.on[DATABASE_INTEGRATION_NAME].relation_broken,
            self._on_database_integration_broken,
        )

        # Internal route
        self.framework.observe(
            self.on[INTERNAL_ROUTE_INTEGRATION_NAME].relation_joined,
            self._on_internal_route_changed,
        )
        self.framework.observe(
            self.on[INTERNAL_ROUTE_INTEGRATION_NAME].relation_changed,
            self._on_internal_route_changed,
        )
        self.framework.observe(
            self.on[INTERNAL_ROUTE_INTEGRATION_NAME].relation_broken,
            self._on_internal_route_changed,
        )

        # OpenFGA
        self.framework.observe(
            self.openfga_requirer.on.openfga_store_created,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self.openfga_requirer.on.openfga_store_removed,
            self._on_openfga_store_removed,
        )

    @cached_property
    def _cached_internal_ingress(self) -> InternalIngressData:
        """Internal ingress data, computed once per charm instance."""
        return InternalIngressData.load(self.internal_ingress)

    @cached_property
    def _cached_database_config(self) -> DatabaseConfig:
        """Database config, computed once per charm instance."""
        return DatabaseConfig.load(self.database_requirer)

    @property
    def _pebble_layer(self) -> ops.pebble.Layer:
        """Build the pebble layer from all env var sources."""
        oauth_config = self._config.get_oauth_config()
        oauth_provider_data = self.oauth_integration.get_oauth_provider_data(
            allowed_subjects=oauth_config.get("authn_allowed_subjects") or "",
            allowed_scope=oauth_config.get("authn_allowed_scope") or "",
            jwks_url=oauth_config.get("authn_jwks_url") or "",
            issuer=oauth_config.get("authn_issuer") or "",
        )

        return self._pebble_service.render_pebble_layer(
            TracingData.load(self.tracing_requirer),
            self._cached_database_config,
            self._secrets,
            self._config,
            OpenFGAModelData.load(self.peer_data[self._workload_service.version]),
            self.openfga_integration.openfga_integration_data,
            oauth_provider_data,
            KratosInfoData.load(self.model, KRATOS_INFO_INTEGRATION_NAME),
        )

    @property
    def _hydra_hook_url(self) -> str:
        """The URL for the Hydra token webhook."""
        if internal_url := self._cached_internal_ingress.url:
            return join(str(internal_url), "api/v0/webhooks/token")
        return (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{PORT}"
            f"/api/v0/webhooks/token"
        )

    @property
    def _kratos_login_webhook_url(self) -> str:
        """The URL for the Kratos login webhook."""
        if internal_url := self._cached_internal_ingress.url:
            return join(str(internal_url), "api/v0/webhooks/login")
        return (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{PORT}"
            f"/api/v0/webhooks/login"
        )

    @property
    def _kratos_registration_webhook_url(self) -> str:
        """The URL for the Kratos registration webhook."""
        if internal_url := self._cached_internal_ingress.url:
            return join(str(internal_url), "api/v0/webhooks/registration")
        return (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{PORT}"
            f"/api/v0/webhooks/registration"
        )

    @property
    def _service_url(self) -> str:
        """The base HTTP service URL for the tenant-service."""
        if internal_url := self._cached_internal_ingress.url:
            return str(internal_url)
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{PORT}"

    @property
    def _grpc_url(self) -> str:
        """The gRPC service URL for the tenant-service."""
        return f"{self.app.name}.{self.model.name}.svc.cluster.local:{GRPC_PORT}"

    @property
    def migration_needed(self) -> bool:
        """Check if database migration is needed."""
        if not self.database_requirer.is_resource_created():
            return False

        database_config = self._cached_database_config
        return not self._cli.migration_check(dsn=database_config.dsn)

    def _ensure_secrets(self) -> bool:
        """Ensure the charm secrets are created."""
        if self._secrets.is_ready():
            return True

        if self.unit.is_leader():
            self._secrets[API_TOKEN_SECRET_LABEL] = {API_TOKEN_SECRET_KEY: token_hex(16)}
            return True
        return False

    def _ensure_hydra_relation(self) -> bool:
        """Ensure the hydra-token-hook relation data is up to date."""
        if self.unit.is_leader() and self.hydra_token_hook_integration.is_ready():
            self.hydra_token_hook_integration.update_relation_data(
                self._hydra_hook_url,
                self._secrets.api_token,
            )
        return True

    def _ensure_kratos_registration_webhook(self) -> bool:
        """Ensure the kratos-registration-webhook relation data is up to date."""
        if self.unit.is_leader() and self.kratos_registration_webhook_integration.is_ready():
            self.kratos_registration_webhook_integration.update_relation_data(
                self._kratos_registration_webhook_url,
                self._secrets.api_token,
            )
        return True

    def _ensure_kratos_login_webhook(self) -> bool:
        """Ensure the kratos-login-webhook relation data is up to date."""
        if self.unit.is_leader() and self.kratos_login_webhook_integration.is_ready():
            self.kratos_login_webhook_integration.update_relation_data(
                self._kratos_login_webhook_url,
                self._secrets.api_token,
            )
        return True

    def _ensure_tenant_service_info(self) -> bool:
        """Ensure the tenant-service-info relation data is published."""
        if self.unit.is_leader():
            self.tenant_service_info_integration.update_relations_app_data(
                self._service_url, self._grpc_url
            )
        return True

    def _ensure_internal_ingress(self) -> bool:
        """Ensure the internal ingress configuration is submitted."""
        if (
            self.unit.is_leader()
            and self.internal_ingress.is_ready()
            and self.internal_ingress._relation.app is not None
        ):
            internal_route_config = self._cached_internal_ingress.config
            self.internal_ingress.submit_to_traefik(internal_route_config)
        return True

    def _ensure_database_migration(self) -> bool:
        """Ensure database migrations are up to date."""
        if migration_is_ready(self):
            return True

        if not self.unit.is_leader():
            logger.info(
                "Unit does not have leadership. Wait for leader unit to run the migration."
            )
            return False

        database_config = self._cached_database_config
        try:
            self._cli.migrate_up(dsn=database_config.dsn)
        except MigrationError:
            logger.error("Auto migration job failed. Please use the run-migration-up action")
            return False

        self.peer_data[MIGRATION_COMPLETED] = self._workload_service.version
        return True

    def _ensure_openfga_model(self) -> bool:
        """Ensure the OpenFGA authorization model is created."""
        if not self._config._config.get("authorization_enabled", True):
            return True

        if not self.openfga_integration.is_store_ready():
            return False

        if not peer_integration_exists(self):
            return False

        if self.peer_data[self._workload_service.version].get(OPENFGA_MODEL_ID):
            return True

        if not self.unit.is_leader():
            return False

        try:
            openfga_model_id = self._workload_service.create_openfga_model(
                self.openfga_integration.openfga_integration_data
            )
        except CreateFgaModelError:
            logger.exception("Failed to create OpenFGA model")
            return False

        self.peer_data[self._workload_service.version] = {OPENFGA_MODEL_ID: openfga_model_id}
        return True

    def _ensure_tls(self) -> bool:
        """Ensure TLS certificates are updated on both the charm and workload."""
        LOCAL_CHARM_CERTIFICATES_FILE.parent.mkdir(parents=True, exist_ok=True)

        certificates = TLSCertificates.load(self.certificate_transfer_requirer).ca_bundle
        existing = (
            LOCAL_CHARM_CERTIFICATES_FILE.read_text()
            if LOCAL_CHARM_CERTIFICATES_FILE.exists()
            else ""
        )

        if certificates == existing:
            return True

        if certificates:
            LOCAL_CHARM_CERTIFICATES_FILE.write_text(certificates)
        else:
            LOCAL_CHARM_CERTIFICATES_FILE.unlink(missing_ok=True)

        try:
            subprocess.run(
                [
                    "update-ca-certificates",
                    "--fresh",
                    "--etccertsdir",
                    str(LOCAL_CERTIFICATES_PATH),
                    "--localcertsdir",
                    str(LOCAL_CHARM_CERTIFICATES_PATH),
                ],
                check=True,
            )
        except subprocess.CalledProcessError:
            logger.exception("Failed to update CA certificates")
            # Remove the cert file so the next reconciliation retries the subprocess.
            LOCAL_CHARM_CERTIFICATES_FILE.unlink(missing_ok=True)
            return False
        self._tls_cert_changed = self._workload_service.update_ca_certs()
        return True

    def _on_holistic_handler(self, event: ops.EventBase) -> None:
        """Entry point for the centralized reconciliation handler.

        Sets the unit to MaintenanceStatus while reconciling, then delegates
        to _holistic_handler.
        """
        self.unit.status = ops.MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)

    def _holistic_handler(self, event: ops.EventBase) -> None:
        """Centralized reconciliation handler."""
        if not all(condition(self) for condition in NOOP_CONDITIONS):
            return

        self._tls_cert_changed = False
        can_plan = True
        for f in [
            self._ensure_secrets,
            self._ensure_hydra_relation,
            self._ensure_kratos_registration_webhook,
            self._ensure_kratos_login_webhook,
            self._ensure_tenant_service_info,
            self._ensure_internal_ingress,
            self._ensure_database_migration,
            self._ensure_openfga_model,
            self._ensure_tls,
        ]:
            try:
                can_plan = can_plan and f()
            except CharmError:
                logger.exception("Error in %s", f.__name__)
                can_plan = False

        if not can_plan:
            return

        try:
            # force_restart=True when the CA bundle changed: Go's crypto/x509
            # loads the system cert pool once via sync.Once on the first TLS
            # dial; pushing a new ca-certificates.crt into the container is
            # not picked up by the running process without a restart.
            self._pebble_service.plan(self._pebble_layer, force_restart=self._tls_cert_changed)
        except PebbleError:
            logger.error(
                "Failed to plan pebble layer, please check the %s container logs",
                WORKLOAD_CONTAINER,
            )

    def _get_migration_status(self) -> ops.StatusBase | None:
        """Migration status for collect-status."""
        try:
            is_migration_ready = migration_is_ready(self)
        except MigrationCheckError as e:
            return ops.BlockedStatus(f"Migration check failed: {e}")

        if not is_migration_ready:
            if self.unit.is_leader():
                return ops.WaitingStatus("Waiting for database migration")
            return ops.WaitingStatus("Waiting for leader unit to run the migration")
        return None

    # Event handlers

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:
        """Handle the pebble-ready event."""
        self._workload_service.open_port()
        self._on_holistic_handler(event)
        self._workload_service.set_version()

    def _on_pebble_check_failed(self, event: ops.PebbleCheckFailedEvent) -> None:
        """Handle the pebble-check-failed event."""
        if event.info.name == PEBBLE_READY_CHECK_NAME:
            logger.warning("The service is not running")

    def _on_pebble_check_recovered(self, event: ops.PebbleCheckRecoveredEvent) -> None:
        """Handle the pebble-check-recovered event."""
        if event.info.name == PEBBLE_READY_CHECK_NAME:
            logger.info("The service is online again")

    def _on_internal_route_changed(self, event: ops.RelationEvent) -> None:
        """Handle internal-route relation events."""
        # Needed due to how traefik_route lib handles the event
        self.internal_ingress._relation = event.relation
        self._on_holistic_handler(event)

    def _on_database_integration_broken(self, event: ops.RelationBrokenEvent) -> None:
        """Handle the database relation-broken event."""
        if self._container.can_connect():
            try:
                self._container.stop(WORKLOAD_CONTAINER)
            except ops.pebble.Error:
                logger.warning("Failed to stop workload service after database relation broken")

    def _on_openfga_store_removed(self, event: OpenFGAStoreRemovedEvent) -> None:
        """Handle the openfga-store-removed event."""
        if self.unit.is_leader():
            self.peer_data.pop(key=self._workload_service.version)

        self._on_holistic_handler(event)

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent) -> None:
        """Handle the resource-patch-failed event."""
        logger.error("Resource patching failed: %s", event.message)
        self._on_holistic_handler(event)

    # Status

    def _on_collect_status(self, event: ops.CollectStatusEvent) -> None:
        """Evaluate and report the unit status."""
        can_connect = container_connectivity(self)
        if not can_connect:
            event.add_status(ops.WaitingStatus("Container is not connected yet"))

        if configs := self._config.get_missing_config_keys():
            event.add_status(ops.BlockedStatus(f"Missing required configuration: {configs}"))

        event.add_status(authentication_config_status(self))

        if not self._secrets.is_ready():
            event.add_status(ops.WaitingStatus("Waiting for secrets creation"))

        if can_connect and self._workload_service.is_failing():
            event.add_status(
                ops.BlockedStatus(
                    f"Failed to start the service, please check the "
                    f"{WORKLOAD_CONTAINER} container logs"
                )
            )

        if can_connect and not self._workload_service.is_running():
            event.add_status(ops.WaitingStatus("Waiting for the service to start"))

        self._collect_integration_statuses(event)

        if migration_status := self._get_migration_status():
            event.add_status(migration_status)

        event.add_status(self.resources_patch.get_status())
        event.add_status(ops.ActiveStatus())

    def _collect_integration_statuses(self, event: ops.CollectStatusEvent) -> None:
        """Collect statuses for required integrations."""
        if not database_integration_exists(self):
            event.add_status(ops.BlockedStatus(f"Missing integration {DATABASE_INTEGRATION_NAME}"))

        if not database_resource_is_created(self):
            event.add_status(ops.WaitingStatus("Waiting for database creation"))

        if self._config._config.get("authorization_enabled", True):
            if not openfga_integration_exists(self):
                event.add_status(
                    ops.BlockedStatus(f"Missing integration {OPENFGA_INTEGRATION_NAME}")
                )

            if not self.openfga_integration.is_store_ready():
                event.add_status(ops.WaitingStatus("Waiting for openfga store to be created"))

            if not peer_integration_exists(self):
                event.add_status(
                    ops.WaitingStatus(f"Waiting for peer integration {PEER_INTEGRATION_NAME}")
                )

        if not kratos_info_integration_exists(self):
            event.add_status(
                ops.BlockedStatus(f"Missing integration {KRATOS_INFO_INTEGRATION_NAME}")
            )

    # Actions

    def _get_management_token(self) -> str | None:
        """OAuth access token for internal management API calls.

        Returns:
            An access token if OAuth is configured and the exchange succeeds,
            otherwise None.  Callers that pass None to the CLI proceed without
            authentication (suitable when authorization_enabled=False).
        """
        provider_info = self.oauth_requirer.get_provider_info()
        if not provider_info or not provider_info.client_id or not provider_info.client_secret:
            return None
        try:
            with HTTPClient(token_url=provider_info.token_endpoint) as client:
                return client.get_access_token(
                    client_id=provider_info.client_id,
                    client_secret=provider_info.client_secret,
                )
        except (requests.RequestException, KeyError, ValueError):
            logger.warning("Failed to obtain management token")
            return None

    def _on_get_access_token_action(self, event: ops.ActionEvent) -> None:
        """Handle the get-access-token action."""
        if (
            not (provider_info := self.oauth_requirer.get_provider_info())
            or provider_info.client_id is None
            or provider_info.client_secret is None
        ):
            event.fail("OAuth integration is not ready")
            return

        client_id = provider_info.client_id
        client_secret = provider_info.client_secret
        token_endpoint = provider_info.token_endpoint

        try:
            with HTTPClient(token_url=token_endpoint) as client:
                token = client.get_access_token(
                    client_id=client_id,
                    client_secret=client_secret,
                )
                event.set_results({"token": token})
        except Exception as e:
            event.fail(f"Failed to get access token: {e}")

    def _on_create_tenant_action(self, event: ops.ActionEvent) -> None:
        """Handle the create-tenant action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.create_tenant(
                name=event.params["name"],
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to create tenant: {e}")

    def _on_list_tenants_action(self, event: ops.ActionEvent) -> None:
        """Handle the list-tenants action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.list_tenants(
                page_size=event.params.get("page-size"),
                page_token=event.params.get("page-token"),
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to list tenants: {e}")

    def _on_delete_tenant_action(self, event: ops.ActionEvent) -> None:
        """Handle the delete-tenant action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.delete_tenant(
                tenant_id=event.params["tenant-id"],
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to delete tenant: {e}")

    def _on_activate_tenant_action(self, event: ops.ActionEvent) -> None:
        """Handle the activate-tenant action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.activate_tenant(
                tenant_id=event.params["tenant-id"],
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to activate tenant: {e}")

    def _on_deactivate_tenant_action(self, event: ops.ActionEvent) -> None:
        """Handle the deactivate-tenant action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.deactivate_tenant(
                tenant_id=event.params["tenant-id"],
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to deactivate tenant: {e}")

    def _on_update_tenant_action(self, event: ops.ActionEvent) -> None:
        """Handle the update-tenant action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.update_tenant(
                tenant_id=event.params["tenant-id"],
                name=event.params["name"],
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to update tenant: {e}")

    def _on_list_tenant_users_action(self, event: ops.ActionEvent) -> None:
        """Handle the list-tenant-users action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.list_tenant_users(
                tenant_id=event.params["tenant-id"],
                page_size=event.params.get("page-size"),
                page_token=event.params.get("page-token"),
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to list tenant users: {e}")

    def _on_invite_user_action(self, event: ops.ActionEvent) -> None:
        """Handle the invite-user action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.invite_user(
                tenant_id=event.params["tenant-id"],
                email=event.params["email"],
                role=event.params["role"],
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to invite user: {e}")

    def _on_provision_user_action(self, event: ops.ActionEvent) -> None:
        """Handle the provision-user action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.provision_user(
                tenant_id=event.params["tenant-id"],
                email=event.params["email"],
                role=event.params["role"],
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to provision user: {e}")

    def _on_update_user_role_action(self, event: ops.ActionEvent) -> None:
        """Handle the update-user-role action."""
        if not container_connectivity(self):
            event.fail("Workload container is not ready")
            return

        try:
            result = self._cli.update_user_role(
                tenant_id=event.params["tenant-id"],
                user_id=event.params["user-id"],
                role=event.params["role"],
                token=self._get_management_token(),
            )
            event.set_results({"output": result})
        except Exception as e:
            event.fail(f"Failed to update user role: {e}")

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        """Build resource requirements from charm config."""
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)


if __name__ == "__main__":
    ops.main(TenantServiceOperatorCharm)
