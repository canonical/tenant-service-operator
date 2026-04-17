# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants."""

from pathlib import Path
from string import Template

POSTGRESQL_DSN_TEMPLATE = Template("postgres://$username:$password@$endpoint/$database")
WORKLOAD_CONTAINER = "tenant-service"
WORKLOAD_SERVICE = "tenant-service"
PEBBLE_READY_CHECK_NAME = "ready"
API_TOKEN_SECRET_KEY = "api-token"
API_TOKEN_SECRET_LABEL = "apitokensecret"
LOCAL_CERTIFICATES_PATH = Path("/tmp")
LOCAL_CERTIFICATES_FILE = Path(LOCAL_CERTIFICATES_PATH / "ca-certificates.crt")
LOCAL_CHARM_CERTIFICATES_PATH = Path("/tmp/charm")
LOCAL_CHARM_CERTIFICATES_FILE = Path(LOCAL_CHARM_CERTIFICATES_PATH / "charm-certificates.crt")

SERVICE_COMMAND = "tenant-service serve"
PORT = 8080
GRPC_PORT = 50051
OAUTH_GRANT_TYPES = ["client_credentials"]
OAUTH_SCOPES = "openid"
CERTIFICATES_PATH = Path("/etc/ssl/certs/")
CERTIFICATES_FILE = Path(CERTIFICATES_PATH / "ca-certificates.crt")

INTERNAL_ROUTE_INTEGRATION_NAME = "internal-route"
PROMETHEUS_SCRAPE_INTEGRATION_NAME = "metrics-endpoint"
LOGGING_INTEGRATION_NAME = "logging"
GRAFANA_DASHBOARD_INTEGRATION_NAME = "grafana-dashboard"
TEMPO_TRACING_INTEGRATION_NAME = "tracing"
HYDRA_TOKEN_HOOK_INTEGRATION_NAME = "hydra-token-hook"
KRATOS_INFO_INTEGRATION_NAME = "kratos-info"
KRATOS_REGISTRATION_WEBHOOK_INTEGRATION_NAME = "kratos-registration-webhook"
KRATOS_LOGIN_WEBHOOK_INTEGRATION_NAME = "kratos-login-webhook"
DATABASE_INTEGRATION_NAME = "pg-database"
OPENFGA_INTEGRATION_NAME = "openfga"
OPENFGA_STORE_NAME = "tenant-service-store"
OPENFGA_MODEL_ID = "openfga_model_id"
PEER_INTEGRATION_NAME = "tenant-service"
OAUTH_INTEGRATION_NAME = "oauth"
CERTIFICATE_TRANSFER_INTEGRATION_NAME = "receive-ca-cert"
TENANT_SERVICE_INFO_INTEGRATION_NAME = "tenant-service-info"
