# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
APP_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
DB_APP = "postgresql-k8s"
KRATOS_CHARM = "kratos"
KRATOS_APP = "kratos"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_APP = "traefik"
INGRESS_DOMAIN = "public"
