# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_APP = "traefik"
DB_CHARM = "postgresql-k8s"
DB_APP = "postgresql"
OPENFGA_CHARM = "openfga-k8s"
OPENFGA_APP = "openfga"
KRATOS_CHARM = "kratos"
KRATOS_APP = "kratos"
INGRESS_DOMAIN = "public"
